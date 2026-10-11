// Automatic key finding for a can't-tell take: which transpositions to try, in which order, and when to stop.
// Pure logic: the screen supplies tryKey (set the key, wait for the new analysis) so this can be tested without a back end.
import { TRANSPOSITION_RANGE } from './transposition.js';

export const MAX_KEY_TRIES = 2 * TRANSPOSITION_RANGE; // the whole -12..12 range except the current key
export const MIN_ALIGNMENT_QUALITY = 0.4; // the back end's MIN_ALIGNMENT_QUALITY (diagnosis/config.py)
export const LOW_MATCH_REASON = 'low_match';
export const MIN_OFFSET_NOTES = 4; // fewer heard notes than this say too little about the key

export const shouldAutoKey = (analysis) => analysis.cant_tell === true && analysis.cant_tell_reason === LOW_MATCH_REASON;

export const isMatch = (analysis) => !analysis.cant_tell && analysis.alignment_quality >= MIN_ALIGNMENT_QUALITY;

const median = (values) => {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
};

// The key the played notes point to: the current key plus the median of (played - expected) pitch over the notes the
// back end paired. Null when too few were paired, the median rounds to no change, or it lies outside -12..12.
export function medianOffsetKey(analysis) {
  const offsets = (analysis?.notes ?? [])
    .filter((note) => note.played_midi_float != null && note.expected_midi != null)
    .map((note) => note.played_midi_float - note.expected_midi);
  if (offsets.length < MIN_OFFSET_NOTES) return null;
  const shift = Math.round(median(offsets));
  const key = (analysis.transposition?.semitones ?? 0) + shift;
  return shift !== 0 && Math.abs(key) <= TRANSPOSITION_RANGE ? key : null;
}

// The keys to try: the current one +-1, +-2 ... within the back end's -12..12, nearest first (lower first on a tie,
// as a trumpet sounds below its written pitch), the current one skipped. That is the whole range, at most MAX_KEY_TRIES.
export function candidateSemitones(current) {
  const candidates = [];
  for (let distance = 1; distance <= 2 * TRANSPOSITION_RANGE; distance += 1) {
    [current - distance, current + distance].forEach((semitones) => {
      if (Math.abs(semitones) <= TRANSPOSITION_RANGE) candidates.push(semitones);
    });
  }
  return candidates.slice(0, MAX_KEY_TRIES);
}

// The order to try keys in on one take: `prefer` (the best key so far), then the key its notes point to, then `around`
// (when the take was not checked in it) and the keys nearest to it. `skip` is the key the take is already checked in.
export function keyOrder({ around, skip = around, analysis = null, prefer = [] }) {
  const ordered = [...prefer, medianOffsetKey(analysis), ...(around === skip ? [] : [around]), ...candidateSemitones(around)];
  return [...new Set(ordered.filter((semitones) => Number.isInteger(semitones) && semitones !== skip))];
}

// Remembers the key whose analysis matched the score best so far (alignment_quality), across every try.
export function createBestKey() {
  let best = null;
  return {
    note(semitones, analysis) {
      const quality = analysis?.alignment_quality ?? 0;
      if (!best || quality > best.quality) best = { semitones, quality };
    },
    get semitones() { return best?.semitones ?? null; },
  };
}

// tryKey(semitones) -> the take's analysis under that key, or null when it was stopped (isActive() went false).
// onProgress({ semitones, tried, total }) runs before each try. Resolves to { outcome: 'found', semitones, analysis },
// { outcome: 'none' } or { outcome: 'cancelled' }. A tryKey error propagates; the caller restores the original key.
export async function searchKeys({ keys, tryKey, onProgress, isActive }) {
  for (const [index, semitones] of keys.entries()) {
    if (!isActive()) return { outcome: 'cancelled' };
    onProgress({ semitones, tried: index + 1, total: keys.length });
    const analysis = await tryKey(semitones);
    if (!isActive() || !analysis) return { outcome: 'cancelled' };
    if (isMatch(analysis)) return { outcome: 'found', semitones, analysis };
  }
  return { outcome: 'none' };
}

const plural = (count) => (count === 1 ? 'semitone' : 'semitones');

// What the user is told when a key was found, e.g. "Detected you're playing 2 semitones lower than expected; adjusted."
export function foundMessage(original, found) {
  const shift = found - original;
  return `Detected you're playing ${Math.abs(shift)} ${plural(Math.abs(shift))} ${shift < 0 ? 'lower' : 'higher'} than expected; adjusted.`;
}

export const NONE_FOUND_MESSAGE = 'Tried other keys; none matched.';

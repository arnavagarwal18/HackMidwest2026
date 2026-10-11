// Automatic key finding for a can't-tell take: which transpositions to try, in which order, and when to stop.
// Pure logic: the screen supplies tryKey (set the key, wait for the new analysis) so this can be tested without a back end.
import { TRANSPOSITION_RANGE } from './transposition.js';

export const MAX_KEY_TRIES = 12;
export const MIN_ALIGNMENT_QUALITY = 0.4; // the back end's MIN_ALIGNMENT_QUALITY (diagnosis/config.py)
export const LOW_MATCH_REASON = 'low_match';

export const shouldAutoKey = (analysis) => analysis.cant_tell === true && analysis.cant_tell_reason === LOW_MATCH_REASON;

export const isMatch = (analysis) => !analysis.cant_tell && analysis.alignment_quality >= MIN_ALIGNMENT_QUALITY;

// The keys to try: the current one +-1, +-2 ... within the back end's -12..12, nearest first (lower first on a tie,
// as a trumpet sounds below its written pitch), the current one skipped, at most MAX_KEY_TRIES.
export function candidateSemitones(current) {
  const candidates = [];
  for (let distance = 1; distance <= 2 * TRANSPOSITION_RANGE; distance += 1) {
    [current - distance, current + distance].forEach((semitones) => {
      if (Math.abs(semitones) <= TRANSPOSITION_RANGE) candidates.push(semitones);
    });
  }
  return candidates.slice(0, MAX_KEY_TRIES);
}

// tryKey(semitones) -> the take's analysis under that key, or null when it was stopped (isActive() went false).
// onProgress({ tried, total }) runs before each try. Resolves to { outcome: 'found', semitones, analysis },
// { outcome: 'none' } or { outcome: 'cancelled' }. A tryKey error propagates; the caller restores the original key.
export async function searchKeys({ original, tryKey, onProgress, isActive }) {
  const candidates = candidateSemitones(original);
  for (const [index, semitones] of candidates.entries()) {
    if (!isActive()) return { outcome: 'cancelled' };
    onProgress({ tried: index + 1, total: candidates.length });
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

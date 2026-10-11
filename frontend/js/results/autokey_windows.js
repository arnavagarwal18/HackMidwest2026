// The bar-window fallback of the automatic key search: when no key matches the bars the take was uploaded with, the take
// may cover only part of them (a 28 s take scored against bars 1-16). The same file is uploaded again as a new take
// for the first and then the second half of the bars, and each half is tried in the best key found so far, in the key
// its own notes point to, and in the keys nearest to the best one. Pure logic: the screen supplies uploadWindow and tryKey.
import { createBestKey, isMatch, keyOrder, searchKeys } from './autokey.js';

export const MAX_TOTAL_RERUNS = 40; // key changes over the whole search, the first pass on the uploaded bars included
export const LONGEST_WHOLE_RANGE = 8; // a range of this many bars or fewer is not split
export const NO_FILE_MESSAGE = "Tried other keys; none matched. Other bars can't be tried because the recording is no longer in this page, so upload it again to try them.";

// The bar ranges to try for a take uploaded with bars from..to: its two halves, or none when the range is short.
export function barWindows(from, to) {
  const count = to - from + 1;
  if (count <= LONGEST_WHOLE_RANGE) return [];
  const firstEnd = from + Math.floor(count / 2) - 1;
  return [{ from, to: firstEnd }, { from: firstEnd + 1, to }];
}

const plural = (count) => (count === 1 ? 'semitone' : 'semitones');
const signed = (semitones) => (semitones > 0 ? `+${semitones}` : String(semitones));

// e.g. "Matched bars 1–8 at -4 semitones."
export const foundWindowMessage = ({ from, to }, semitones) => `Matched bars ${from}–${to} at ${signed(semitones)} ${plural(Math.abs(semitones))}.`;

// uploadWindow(bars) -> { take, analysis } for the new take once it was checked, or null when stopped.
// tryKey(take, semitones) -> that take's analysis under the key, or null when stopped.
// onProgress({ bars, semitones?, tried?, total? }) runs when a window starts and before each key.
// bestKey: createBestKey(), shared with the first pass. rerunsLeft: what is left of MAX_TOTAL_RERUNS.
// Resolves to { outcome: 'found', take, bars, semitones, analysis, rerun } (rerun: false when the upload already matched),
// { outcome: 'none' } or { outcome: 'cancelled' }.
export async function searchBarWindows({ windows, original, bestKey, rerunsLeft, uploadWindow, tryKey, onProgress, isActive }) {
  let left = rerunsLeft;
  for (const [index, bars] of windows.entries()) {
    if (!isActive()) return { outcome: 'cancelled' };
    onProgress({ bars });
    const uploaded = await uploadWindow(bars);
    if (!isActive() || !uploaded) return { outcome: 'cancelled' };
    const { take, analysis } = uploaded;
    const checkedIn = analysis.transposition?.semitones ?? original;
    bestKey.note(checkedIn, analysis);
    if (isMatch(analysis)) return { outcome: 'found', take, bars, semitones: checkedIn, analysis, rerun: false };

    const keys = keyOrder({ around: bestKey.semitones ?? original, skip: checkedIn, analysis, prefer: [bestKey.semitones] })
      .slice(0, Math.floor(left / (windows.length - index))); // each window gets an equal share of what is left
    const search = await searchKeys({
      keys,
      isActive,
      onProgress: (progress) => onProgress({ bars, ...progress }),
      tryKey: async (semitones) => {
        left -= 1;
        const tried = await tryKey(take, semitones);
        if (tried) bestKey.note(semitones, tried);
        return tried;
      },
    });
    if (search.outcome === 'found') return { outcome: 'found', take, bars, semitones: search.semitones, analysis: search.analysis, rerun: true };
    if (search.outcome === 'cancelled') return search;
  }
  return { outcome: 'none' };
}

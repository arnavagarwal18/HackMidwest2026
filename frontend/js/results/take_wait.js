// Waiting on the back end for one take to be checked again after the transposition changed.
import { getAnalysis } from '../api.js';
import { pollThresholds, pollUntilDone } from './polling.js';

export const KEY_POLL_MS = 300; // a rerun of one take is quick, so poll faster than the 1 s default

export const keyThresholds = () => {
  const thresholds = pollThresholds();
  return { ...thresholds, intervalMs: Math.min(thresholds.intervalMs, KEY_POLL_MS) };
};

// Waits until the take is 'done' with a diagnosis (while a rerun runs the take can be in another status, and then the
// analysis shows the session's key but no diagnosis) and accepts(analysis) is true. Resolves to the poll result ({ outcome, result }).
export function waitForAnalysis(sessionId, take, accepts, isActive) {
  return pollUntilDone({
    isActive,
    thresholds: keyThresholds(),
    onTick: () => {},
    fetchOnce: async () => {
      const analysis = await getAnalysis(sessionId, take);
      if (analysis.status === 'failed') throw new Error(analysis.error?.message ?? 'The take could not be checked.');
      const finished = analysis.status === 'done' && analysis.alignment_quality != null;
      return { done: finished && accepts(analysis), analysis };
    },
  });
}

// Waits until the rerun has really finished: the take is 'done' again with a diagnosis made under `semitones`.
// Resolves to the poll result ({ outcome, result }).
export const waitForKey = (sessionId, take, semitones, isActive) =>
  waitForAnalysis(sessionId, take, (analysis) => analysis.transposition?.semitones === semitones, isActive);

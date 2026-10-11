// Waiting on the back end for one take to be (re)checked, and uploading the same recording again for other bars.
import { getAnalysis, uploadTake } from '../api.js';
import { pollThresholds, pollUntilDone } from './polling.js';

export const KEY_POLL_MS = 300; // a rerun of one take is quick, so poll faster than the 1 s default

const keyThresholds = () => {
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

// Uploads the recording as a new take for other bars (the other fields as before) and waits for its first check.
// upload: { file, fields }. Resolves to { take, analysis }, or null when stopped.
export async function uploadWindowTake(sessionId, upload, { from, to }, isActive) {
  const { take_id: take } = await uploadTake(sessionId, upload.file, { ...upload.fields, bar_from: from, bar_to: to });
  const polled = await waitForAnalysis(sessionId, take, () => true, isActive);
  if (polled.outcome === 'stopped') return null;
  if (polled.outcome === 'timeout') throw new Error(`Checking the recording for bars ${from}–${to} took too long.`);
  return { take, analysis: polled.result.analysis };
}

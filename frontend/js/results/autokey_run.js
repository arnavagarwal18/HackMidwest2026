// Runs the automatic key search for one can't-tell take against the back end, and always puts the original key back
// unless a working one was found. Each try is one POST .../transposition (which re-diagnoses the session's takes in the
// background, with no AI call) and polling GET .../analysis until the take shows the new key. Only a found key costs an
// AI call: the feedback is written again, because a rerun does not do it.
import { ApiError, getAnalysis, requestFeedback, setTransposition } from '../api.js';
import { showError } from '../banner.js';
import { isRequestCancelled } from '../request_cancelled.js';
import { STAGES, unwrapFeedback } from './load.js';
import { foundMessage, NONE_FOUND_MESSAGE, searchKeys } from './autokey.js';
import { pollThresholds, pollUntilDone, wait } from './polling.js';
import { renderKeySearch, renderWorking } from './status.js';

export const KEY_POLL_MS = 300; // a rerun of one take is quick, so poll faster than the 1 s default
export const FEEDBACK_TRIES = 5; // POST .../feedback answers 409 while the take is still being re-checked
export const FEEDBACK_RETRY_MS = 1000;
export const KEY_TIMEOUT_TEXT = 'Checking another key took too long, so your original key was put back.';

const triedTakes = new Set(); // `${session}/${take}`: each take is searched at most once per page load

// True the first time it is asked for a take, false after that (also after the user chose a key by hand).
export function claimAutoKey(sessionId, take) {
  const key = `${sessionId}/${take}`;
  if (triedTakes.has(key)) return false;
  triedTakes.add(key);
  return true;
}

const keyThresholds = () => {
  const thresholds = pollThresholds();
  return { ...thresholds, intervalMs: Math.min(thresholds.intervalMs, KEY_POLL_MS) };
};

// Waits until the rerun has really finished: the take is 'done' again with a diagnosis made under `semitones`.
// (While it runs the take can be in another status, and then the analysis shows the session's key but no diagnosis.)
// Resolves to the poll result ({ outcome, result }).
function waitForKey(sessionId, take, semitones, isActive) {
  return pollUntilDone({
    isActive,
    thresholds: keyThresholds(),
    onTick: () => {},
    fetchOnce: async () => {
      const analysis = await getAnalysis(sessionId, take);
      if (analysis.status === 'failed') throw new Error(analysis.error?.message ?? 'The take could not be checked.');
      const rerunFinished = analysis.status === 'done' && analysis.alignment_quality != null;
      return { done: rerunFinished && analysis.transposition?.semitones === semitones, analysis };
    },
  });
}

// Sets the key and waits until the take's analysis shows it. Resolves to that analysis, or null when stopped.
async function tryKey(sessionId, take, semitones, isActive) {
  await setTransposition(sessionId, semitones);
  const polled = await waitForKey(sessionId, take, semitones, isActive);
  if (polled.outcome === 'stopped') return null;
  if (polled.outcome === 'timeout') throw new Error(KEY_TIMEOUT_TEXT);
  return polled.result.analysis;
}

// Puts the original key back and, while the screen is still there, waits for the take to show it again.
async function restoreKey(sessionId, take, original, isActive) {
  try {
    await setTransposition(sessionId, original);
    if (isActive()) await waitForKey(sessionId, take, original, isActive); // once the user left, nothing keeps polling
  } catch (err) {
    if (isRequestCancelled(err)) return;
    console.error(`Could not put transposition ${original} back for ${sessionId}/${take}:`, err);
    showError(`Could not confirm your original transposition (${original}): ${err.message} Set it by hand if it looks wrong.`);
  }
}

// The feedback for the new key (a rerun leaves the old can't-tell feedback). A 409 means the back end is not ready: try again.
async function writeFeedbackAgain(sessionId, take, analysis, isActive) {
  for (let attempt = 1; ; attempt += 1) {
    try {
      return { done: true, analysis, ...unwrapFeedback(await requestFeedback(sessionId, take)) };
    } catch (err) {
      const notReady = err instanceof ApiError && err.status === 409;
      if (!notReady || attempt >= FEEDBACK_TRIES || !isActive()) throw err;
      await wait(FEEDBACK_RETRY_MS);
    }
  }
}

// view: the results element. original: the take's key before the search. isActive(): false once the user left the screen.
// Resolves to { outcome: 'found', result, note } | { outcome: 'none', note } | { outcome: 'cancelled' } | { outcome: 'error' }.
// result is { done, analysis, feedback, plan }. On error the banner has already shown why.
export async function runAutoKey({ view, sessionId, take, original, isActive }) {
  let cancelled = false;
  const searching = () => isActive() && !cancelled;
  const outcome = await (async () => {
    try {
      const search = await searchKeys({
        original,
        isActive: searching,
        tryKey: (semitones) => tryKey(sessionId, take, semitones, searching),
        onProgress: (progress) => renderKeySearch(view, progress, () => { cancelled = true; }),
      });
      if (search.outcome !== 'found') return search;
      renderWorking(view, STAGES.feedback, false);
      const result = await writeFeedbackAgain(sessionId, take, search.analysis, isActive);
      return { outcome: 'found', result, note: foundMessage(original, search.semitones) };
    } catch (err) {
      if (!isRequestCancelled(err)) {
        console.error(`Automatic key search failed for ${sessionId}/${take}:`, err);
        showError(err.message);
      }
      return { outcome: 'error' };
    }
  })();
  if (outcome.outcome === 'found') return outcome;
  await restoreKey(sessionId, take, original, isActive);
  return outcome.outcome === 'none' ? { ...outcome, note: NONE_FOUND_MESSAGE } : outcome;
}

// Runs the automatic search for one can't-tell take against the back end, and always puts the original key back
// unless a working one was found. Each key try is one POST .../transposition (which re-diagnoses the session's takes in
// the background, with no AI call) and polling GET .../analysis until the take shows the new key. If no key fits the
// uploaded bars, the recording is uploaded again for the first and second half of them (autokey_windows.js).
// Only the take that is shown costs an AI call: its feedback is written again, because a rerun does not do it.
import { ApiError, requestFeedback, setTransposition } from '../api.js';
import { showError } from '../banner.js';
import { isRequestCancelled } from '../request_cancelled.js';
import { fetchResultsOnce, STAGES, unwrapFeedback } from './load.js';
import { createBestKey, foundMessage, keyOrder, NONE_FOUND_MESSAGE, searchKeys } from './autokey.js';
import { barWindows, foundWindowMessage, MAX_TOTAL_RERUNS, NO_FILE_MESSAGE, searchBarWindows } from './autokey_windows.js';
import { wait } from './polling.js';
import { renderKeySearch, renderWorking } from './status.js';
import { uploadWindowTake, waitForAnalysis } from './take_wait.js';

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

// Waits until the rerun has really finished: the take is 'done' again with a diagnosis made under `semitones`.
// Resolves to the poll result ({ outcome, result }).
export const waitForKey = (sessionId, take, semitones, isActive) =>
  waitForAnalysis(sessionId, take, (analysis) => analysis.transposition?.semitones === semitones, isActive);

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
export async function writeFeedbackAgain(sessionId, take, analysis, isActive) {
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

// The feedback of the take to show: one that matched on its upload already has it (the back end wrote it); one that
// matched after a key change needs it written again.
async function feedbackFor(sessionId, found, isActive) {
  if (!found.rerun) {
    const written = await fetchResultsOnce(sessionId, found.take);
    if (written.done) return written;
  }
  return writeFeedbackAgain(sessionId, found.take, found.analysis, isActive);
}

// The search proper: the keys on the uploaded bars, then (when the recording is still here) the two halves of the bars.
// Resolves to { outcome: 'found', take, semitones, analysis, rerun, note } | { outcome: 'none', note? } | { outcome: 'cancelled' }.
async function findMatch({ sessionId, take, original, analysis, upload, isActive, onProgress }) {
  const bestKey = createBestKey();
  bestKey.note(original, analysis);
  let reruns = 0;
  const first = await searchKeys({
    keys: keyOrder({ around: original, analysis }),
    isActive,
    onProgress,
    tryKey: async (semitones) => {
      reruns += 1;
      const tried = await tryKey(sessionId, take, semitones, isActive);
      if (tried) bestKey.note(semitones, tried);
      return tried;
    },
  });
  if (first.outcome === 'found') return { ...first, take, rerun: true, note: foundMessage(original, first.semitones) };
  if (first.outcome === 'cancelled') return first;
  if (!upload) return { outcome: 'none', note: NO_FILE_MESSAGE };

  const windows = barWindows(upload.fields.bar_from, upload.fields.bar_to);
  const found = await searchBarWindows({
    windows,
    original,
    bestKey,
    rerunsLeft: MAX_TOTAL_RERUNS - reruns,
    isActive,
    onProgress,
    uploadWindow: (bars) => uploadWindowTake(sessionId, upload, bars, isActive),
    tryKey: (target, semitones) => tryKey(sessionId, target, semitones, isActive),
  });
  if (found.outcome !== 'found') return found.outcome === 'none' ? { ...found, note: NONE_FOUND_MESSAGE } : found;
  return { ...found, note: foundWindowMessage(found.bars, found.semitones) };
}

// view: the results element. take, original, analysis: the can't-tell take, its key and its analysis. upload: { file, fields }
// of that take's upload while the page still holds it, else null. isActive(): false once the user left the screen.
// Resolves to { outcome: 'found', result, note, take } | { outcome: 'none', note } | { outcome: 'cancelled' } | { outcome: 'error' }.
// result is { done, analysis, feedback, plan } of the take to show, which is a new take when another bar range matched.
// On error the banner has already shown why.
export async function runAutoKey({ view, sessionId, take, original, analysis, upload = null, isActive }) {
  let cancelled = false;
  const searching = () => isActive() && !cancelled;
  const outcome = await (async () => {
    try {
      const search = await findMatch({
        sessionId, take, original, analysis, upload,
        isActive: searching,
        onProgress: (progress) => renderKeySearch(view, progress, () => { cancelled = true; }),
      });
      if (search.outcome !== 'found') return search;
      renderWorking(view, STAGES.feedback, false);
      const result = await feedbackFor(sessionId, search, isActive);
      return { outcome: 'found', result, note: search.note, take: search.take };
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
  return outcome.outcome === 'none' ? { outcome: 'none', note: outcome.note ?? NONE_FOUND_MESSAGE } : outcome;
}

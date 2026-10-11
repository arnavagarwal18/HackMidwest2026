// The demo upload's sequence: new session, score photo, the normal score check, then the video as the take.
// `view` is demo/view.js (or a test double); the steps use the same session, score and take helpers as the normal screens.
import { uploadScorePhoto } from '../api.js';
import { setupWithPrefs } from '../play/prefs.js';
import { openSession, startFreshSession, useBuiltinPiece } from '../score/session.js';
import { state } from '../state.js';
import { rememberSentTake, sendTakeFile } from '../take/send.js';
import { initialSetup, kindOfFile, validateSetup } from '../take/setup.js';

// Runs `action` until it succeeds. Each failure is logged, shown with its reason and a Retry button, and the dev decides.
async function untilItWorks(view, what, action) {
  for (;;) {
    try {
      return await action();
    } catch (err) {
      console.error(`Demo upload: ${what} failed:`, err);
      await view.ask(`${what} failed: ${err.message}`, [{ id: 'retry', label: 'Retry' }]);
    }
  }
}

// Sends the photo and waits for the dev to confirm the scan. Resolves { ok: true } or { ok: false, message }.
async function scanPhoto(photo, view) {
  view.setStatus('Sending the photo...');
  const sessionId = await openSession();
  let answer;
  try {
    answer = await uploadScorePhoto(sessionId, photo);
  } catch (err) {
    console.error('Demo upload: the photo upload failed:', err);
    return { ok: false, message: `The photo could not be sent: ${err.message}` };
  }
  state.score.status = answer.score_status;
  view.setStatus('Reading the photo. Check the score below, then confirm it.');
  return view.reviewScan(answer);
}

// The score is confirmed when this resolves: the photo's, or a built-in one when the photo failed and the dev chose that.
async function confirmedScore(photo, view) {
  for (;;) {
    const scan = await scanPhoto(photo, view);
    if (scan.ok) return;
    console.error(`Demo upload: the photo gave no usable score: ${scan.message}`);
    const choice = await view.chooseFallback(scan.message);
    if (choice.action === 'builtin') {
      view.setStatus(`Using ${choice.piece.title} instead of the photo...`);
      return untilItWorks(view, 'Choosing the built-in score', () => useBuiltinPiece(choice.piece));
    }
  }
}

// Uploads the video as the take, with the fields the Play screen would send. Resolves to the results hash.
async function sendVideo(video, view) {
  const setup = initialSetup(state.score, setupWithPrefs(state.take_setup));
  const problem = validateSetup(setup, state.score.bars);
  if (problem) throw new Error(`The confirmed score cannot be played as it is: ${problem}`);
  view.setStatus('Sending the video...');
  const answer = await untilItWorks(view, 'Uploading the video', () => {
    view.progress.reset();
    return sendTakeFile(video, setup, { kind: kindOfFile(video), source: 'uploaded', onProgress: view.progress.update });
  });
  view.progress.hide();
  return rememberSentTake(answer, setup);
}

// Resolves to the results hash to open, or null when the dev left the screen part-way (nothing more is sent).
export async function runDemo({ photo, video, view, isCurrent }) {
  view.setStatus('Opening a new practice session...');
  await untilItWorks(view, 'Opening a session', () => startFreshSession());
  await confirmedScore(photo, view);
  if (!isCurrent()) return null;
  return sendVideo(video, view);
}

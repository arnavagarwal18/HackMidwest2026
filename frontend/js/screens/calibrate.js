// Calibration (#/calibrate): record the 3 reference notes and a click, send them, show the failing notes, or skip.
// See "Calibration screen and tone page" in frontend/README.md. The pieces live in js/calibrate/.
import { getReferenceNotes, skipCalibration, submitCalibration } from '../api.js';
import { clearBanner, reportError, showError } from '../banner.js';
import { button, element } from '../dom.js';
import { findBaseAddress, toneUrl } from '../calibrate/address.js';
import { CLICK_AFTER_S, DELAY_SECONDS, NOTE_COUNT, REF_SECONDS, createClipStore } from '../calibrate/clips.js';
import { renderIntro } from '../calibrate/intro.js';
import { clipProblemFromError, failuresFromError, renderFailureList, renderSendRetry } from '../calibrate/problems.js';
import { createStepRow } from '../calibrate/steps.js';
import { openStream, recordClip, renderLevelMeter, renderMediaError, stopStream } from '../record.js';
import { loadScoreStyles } from '../score/ui.js';
import { state } from '../state.js';

const STYLE_HREF = 'css/calibrate.css';
const NEXT_HASH = '#/take';
const ANOTHER_TRY = 'Needs another try';

function loadStyles() {
  if (document.querySelector(`link[href="${STYLE_HREF}"]`)) return;
  document.head.append(element('link', '', '', { rel: 'stylesheet', href: STYLE_HREF }));
}

export async function render(root, _params, isCurrent = () => true) {
  if (!state.session_id) {
    window.location.hash = '#/start';
    return;
  }
  loadScoreStyles(); // the shared button.primary style
  loadStyles();
  const notes = await getReferenceNotes(state.instrument);
  const { base, note: addressNote } = await findBaseAddress();
  if (!isCurrent()) return; // left while the notes loaded: register no listener
  const clips = createClipStore();
  let disposed = false;
  let busy = false;
  let stream = null;
  let failures = [];
  let failureButtons = []; // the Retry buttons of the failure list
  let sendRetryButton = null; // the Try again button after a send that failed for a reason the clips did not cause
  const needAnotherTry = new Set(); // 'click' / 'inst_0'...: clips the server rejected, shown as "Needs another try"

  const mediaProblem = element('div');
  const meterBox = element('div', '', 'calibrate-meter');
  const failureBox = element('div');
  const resultBox = element('div');
  const sendRetryBox = element('div');
  const refRows = notes.map((note, i) => createStepRow({
    prompt: `Play ${note.name} on your other device now`, buttonLabel: `Record ${note.name} (${REF_SECONDS} s)`,
    onRecord: () => recordNote(i),
  }));
  const delayRow = createStepRow({
    prompt: `Delay test: a click plays from this laptop's speaker. Keep the speaker on and quiet around you.`,
    buttonLabel: `Record the delay test (${DELAY_SECONDS} s)`, onRecord: recordDelay,
  });
  const instrumentRows = notes.map((note, i) => createStepRow({
    prompt: `Play ${note.name} on your instrument`, buttonLabel: `Record ${note.name} (${REF_SECONDS} s)`,
    onRecord: () => recordInstrumentNote(i),
  }));
  const sendButton = button('Send calibration', sendCalibration, 'primary');
  const skipButton = button('Skip calibration', skip);
  const actions = element('p', '', 'calibrate-actions');
  actions.append(sendButton, skipButton);
  const everyButton = () => [...refRows, delayRow, ...instrumentRows].map((row) => row.button)
    .concat(sendButton, skipButton, failureButtons, sendRetryButton ?? []);

  function refresh() {
    refRows.forEach((row, i) => { row.button.disabled = busy; row.setStatus(clips.hasRef(i) ? 'Recorded' : failureStatus(i)); });
    delayRow.button.disabled = busy || !clips.allRefs();
    delayRow.setStatus(clips.hasClick() ? 'Recorded' : needAnotherTry.has('click') ? ANOTHER_TRY : 'Not recorded yet');
    instrumentRows.forEach((row, i) => {
      row.button.disabled = busy || !clips.hasClick();
      row.setStatus(clips.hasInstrument(i) ? 'Recorded' : needAnotherTry.has(`inst_${i}`) ? ANOTHER_TRY : 'Optional');
    });
    sendButton.disabled = busy || !clips.ready();
    skipButton.disabled = busy;
    [...failureButtons, sendRetryButton ?? []].flat().forEach((control) => { control.disabled = busy; }); // no second recording or send while one runs
  }
  const failureStatus = (i) => (failures.some((failure) => failure.index === i) ? ANOTHER_TRY : 'Not recorded yet');

  function showFailures(list) {
    failures = list;
    failureButtons = renderFailureList(failureBox, failures, recordNote);
    refresh();
  }

  // Runs one recording: mic open, level meter, the clip. Returns the clip, or null (the problem is already on screen).
  async function capture(options) {
    busy = true;
    refresh();
    mediaProblem.replaceChildren();
    clearBanner();
    let meter = null;
    try {
      if (!stream) {
        const opened = await openStream();
        if (disposed) { // the learner left while the permission prompt was open
          stopStream(opened.stream);
          return null;
        }
        stream = opened.stream;
      }
      meter = await renderLevelMeter(meterBox, stream);
      return await recordClip({ stream, ...options });
    } catch (err) {
      if (disposed) return null;
      if (err.name === 'MediaAccessError') renderMediaError(mediaProblem, err, { onTryAgain: () => capture(options) });
      else reportError(err);
      return null;
    } finally {
      if (meter) meter.stop();
      busy = false;
      if (!disposed) refresh();
    }
  }

  async function recordNote(index) {
    refRows[index].setStatus(`Recording: play ${notes[index].name} now`);
    const clip = await capture({ durationS: REF_SECONDS });
    if (!clip || disposed) return;
    clips.setRef(index, clip);
    showFailures(failures.filter((failure) => failure.index !== index));
    refresh();
  }

  async function recordDelay() {
    delayRow.setStatus('Recording: listen for the click');
    const clip = await capture({ durationS: DELAY_SECONDS, clickAfterS: CLICK_AFTER_S });
    if (clip && !disposed) { clips.setClick(clip); needAnotherTry.delete('click'); }
    refresh();
  }

  async function recordInstrumentNote(index) {
    instrumentRows[index].setStatus(`Recording: play ${notes[index].name} now`);
    const clip = await capture({ durationS: REF_SECONDS });
    if (clip && !disposed) { clips.setInstrument(index, clip); needAnotherTry.delete(`inst_${index}`); }
    refresh();
  }

  // Sends the clips in memory. Run again by Try again, which re-sends the same clips without opening the mic.
  async function sendCalibration() {
    if (busy) return;
    busy = true;
    refresh();
    clearBanner();
    try {
      const { files, clickAtS } = clips.toUpload();
      const { profile } = await submitCalibration(state.session_id, files, clickAtS);
      state.calibration = profile;
      showFailures([]);
      showSendRetry(false);
      showResult(profile);
    } catch (err) {
      if (!disposed) handleSendFailure(err);
    } finally {
      busy = false;
      if (!disposed) refresh();
    }
  }

  // A bad clip must be recorded again; notes that failed the check likewise; anything else (server down, 5xx, timeout) keeps every clip for Try again.
  function handleSendFailure(err) {
    const clipProblem = clipProblemFromError(err, notes);
    if (clipProblem) {
      console.error(`The server rejected the recording of ${clipProblem.label}:`, err);
      clips.discard(clipProblem.field);
      if (clipProblem.kind === 'ref') showFailures([{ index: clipProblem.index, asked: notes[clipProblem.index].name, text: 'recording could not be used' }]);
      else needAnotherTry.add(clipProblem.field);
      showSendRetry(false);
      showError(clipProblem.message);
      return;
    }
    reportError(err);
    showFailures(failuresFromError(err, notes));
    failures.forEach((failure) => clips.clearRef(failure.index)); // those notes must be played again before sending
    showSendRetry(failures.length === 0);
  }

  function showSendRetry(visible) {
    sendRetryButton = visible ? renderSendRetry(sendRetryBox, sendCalibration) : null;
    if (!visible) sendRetryBox.replaceChildren();
  }

  function showResult(profile) {
    resultBox.replaceChildren(
      element('p', `Calibrated: pitch offset ${profile.pitch_offset_cents} cents, delay ${profile.latency_ms} ms.`, 'calibrate-done', { role: 'status' }),
      button('Continue to the take screen', () => { window.location.hash = NEXT_HASH; }, 'primary'),
    );
  }

  async function skip() {
    busy = true;
    refresh();
    try {
      const { profile } = await skipCalibration(state.session_id);
      state.calibration = profile;
      window.location.hash = NEXT_HASH;
    } catch (err) {
      if (!disposed) reportError(err);
    } finally {
      busy = false;
      if (!disposed) refresh();
    }
  }

  function dispose() {
    disposed = true;
    if (stream) stopStream(stream);
    stream = null;
    everyButton().forEach((control) => { control.disabled = true; });
  }
  window.addEventListener('hashchange', dispose, { once: true });

  const stepList = (rows) => {
    const list = element('ol', '', 'calibrate-steps');
    list.append(...rows.map((row) => row.element));
    return list;
  };
  root.append(
    element('h1', 'Calibrate'),
    element('p', 'Calibration lets the app adjust to this room and your microphone. It takes about a minute.', 'muted'),
    renderIntro({ notes, url: toneUrl(base, state.instrument), addressNote }),
    element('h2', `1. Play each note (${NOTE_COUNT})`),
    stepList(refRows),
    mediaProblem,
    meterBox,
    failureBox,
    element('h2', '2. Delay test'),
    stepList([delayRow]),
    element('h2', '3. Your instrument (optional)'),
    element('p', 'Now play the same notes on your instrument.', 'muted'),
    stepList(instrumentRows),
    actions,
    sendRetryBox,
    resultBox,
  );
  refresh();
}

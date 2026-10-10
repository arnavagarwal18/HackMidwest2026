// Calibration (#/calibrate): record the 3 reference notes and a click, send them, show the failing notes, or skip.
// See "Calibration screen and tone page" in frontend/README.md. The pieces live in js/calibrate/.
import { getReferenceNotes, skipCalibration, submitCalibration } from '../api.js';
import { clearBanner, reportError } from '../banner.js';
import { button, element } from '../dom.js';
import { findBaseAddress, toneUrl } from '../calibrate/address.js';
import { CLICK_AFTER_S, DELAY_SECONDS, NOTE_COUNT, REF_SECONDS, createClipStore } from '../calibrate/clips.js';
import { renderIntro } from '../calibrate/intro.js';
import { failuresFromError, renderFailureList } from '../calibrate/problems.js';
import { createStepRow } from '../calibrate/steps.js';
import { openStream, recordClip, renderLevelMeter, renderMediaError, stopStream } from '../record.js';
import { loadScoreStyles } from '../score/ui.js';
import { state } from '../state.js';

const STYLE_HREF = 'css/calibrate.css';
const NEXT_HASH = '#/take';

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

  const mediaProblem = element('div');
  const meterBox = element('div', '', 'calibrate-meter');
  const failureBox = element('div');
  const resultBox = element('div');
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
  const everyButton = () => [...refRows, delayRow, ...instrumentRows].map((row) => row.button).concat(sendButton, skipButton);

  function refresh() {
    refRows.forEach((row, i) => { row.button.disabled = busy; row.setStatus(clips.hasRef(i) ? 'Recorded' : failureStatus(i)); });
    delayRow.button.disabled = busy || !clips.allRefs();
    delayRow.setStatus(clips.hasClick() ? 'Recorded' : 'Not recorded yet');
    instrumentRows.forEach((row, i) => {
      row.button.disabled = busy || !clips.hasClick();
      row.setStatus(clips.hasInstrument(i) ? 'Recorded' : 'Optional');
    });
    sendButton.disabled = busy || !clips.ready();
    skipButton.disabled = busy;
  }
  const failureStatus = (i) => (failures.some((failure) => failure.index === i) ? 'Needs another try' : 'Not recorded yet');

  function showFailures(list) {
    failures = list;
    renderFailureList(failureBox, failures, recordNote);
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
    if (clip && !disposed) clips.setClick(clip);
    refresh();
  }

  async function recordInstrumentNote(index) {
    instrumentRows[index].setStatus(`Recording: play ${notes[index].name} now`);
    const clip = await capture({ durationS: REF_SECONDS });
    if (clip && !disposed) clips.setInstrument(index, clip);
    refresh();
  }

  async function sendCalibration() {
    busy = true;
    refresh();
    try {
      const { files, clickAtS } = clips.toUpload();
      const { profile } = await submitCalibration(state.session_id, files, clickAtS);
      state.calibration = profile;
      showFailures([]);
      showResult(profile);
    } catch (err) {
      if (disposed) return;
      reportError(err); // the clips stay in memory
      showFailures(failuresFromError(err, notes));
      failures.forEach((failure) => clips.clearRef(failure.index)); // those notes must be played again before sending
    } finally {
      busy = false;
      if (!disposed) refresh();
    }
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
    resultBox,
  );
  refresh();
}

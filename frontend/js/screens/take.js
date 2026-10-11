// Play (#/take): the tempo and one big Record button; record (or upload a file), send it, open the results.
// See "Take setup" in frontend/README.md. The pieces live in js/take/.
import { checkCamera, getScore, uploadTake } from '../api.js';
import { clearBanner, reportError, showNotice } from '../banner.js';
import { rememberCamera, rememberTempo, setupWithPrefs } from '../play/prefs.js';
import { getAudioContext, openStream, recordTake, renderLevelMeter, renderMediaError, stopStream } from '../record.js';
import { state } from '../state.js';
import { button, el, loadScoreStyles } from '../score/ui.js';
import { createCameraPanel } from '../take/camera_panel.js';
import { initialSetup, kindOfFile, takeFields, validateSetup } from '../take/setup.js';
import { createTakeForm } from '../take/take_form.js';

const STYLE_HREF = 'css/take.css';
const RECORD_LIMIT_S = 180;
const NO_METER = { stop() {} };
const MIC_REASON = 'Record needs your microphone to hear your trumpet. Your browser will ask you to allow it.';
const WAITING_TEXT = "Waiting for permission\u2026 Choose Allow in your browser's prompt. If none appears, check the address bar or the site settings.";
const START_FAILED_TEXT = 'The recording could not be started, so it was stopped. Press Record to try again.';

// After a reload only the score status is known, so the bar count and tempo come from the score itself.
async function loadScoreSummary() {
  if (state.score.bars) return state.score;
  const score = await getScore(state.session_id);
  state.score = { ...state.score, bars: score.bars.length, tempo_bpm: score.tempo_bpm, time_signature: score.time_signature };
  return state.score;
}

function loadTakeStyles() {
  if (document.querySelector(`link[href="${STYLE_HREF}"]`)) return;
  document.head.append(el('link', { attrs: { rel: 'stylesheet', href: STYLE_HREF } }));
}

export async function render(root, _params, isCurrent = () => true) {
  if (!state.session_id) {
    window.location.hash = '#/start';
    return;
  }
  if (state.score.status !== 'confirmed') {
    window.location.hash = '#/score';
    return;
  }
  const score = await loadScoreSummary();
  if (!isCurrent()) return; // left while the score loaded: open no camera and register no listener
  loadScoreStyles();
  loadTakeStyles();

  let disposed = false;
  let opening = 0; // bumped on every camera/mic open, so a slow answer for an old choice is dropped
  let current = null; // { stream, hasVideo } while a stream is open
  let recording = null; // { handle, meter } while recording
  let unsent = null; // { result, kind } a finished recording whose upload failed; kept so Send again reuses the same file

  const form = createTakeForm({
    setup: initialSetup(score, setupWithPrefs(state.take_setup)), bars: score.bars, onKindChange: switchKind, onTempoChange: rememberTempo,
  });
  const camera = createCameraPanel({ instrument: state.instrument, check: (jpeg) => checkCamera(state.session_id, jpeg) });
  const problem = el('div', { className: 'take-problem' });
  const status = el('p', { className: 'muted', attrs: { role: 'status' } });
  const meterBox = el('div', { className: 'take-meter' });
  const recordButton = button('Record', startRecording, 'primary record-big');
  const stopButton = button('Stop', stopRecording, 'primary record-big');
  const sendAgainButton = button('Send this take again', sendUnsent);
  const discardButton = button('Discard and record again', discardUnsent);
  const fileInput = el('input', { attrs: { type: 'file', accept: 'audio/*,video/*' } });
  fileInput.addEventListener('change', uploadChosenFile);
  const controls = [recordButton, stopButton, sendAgainButton, discardButton, fileInput];

  // The one place that decides what is shown and enabled. Modes: idle, recording, sending (an upload or a stop is
  // running: everything disabled, buttons left as they were) and unsent (a recording the server refused or could not get).
  function setMode(mode) {
    if (mode !== 'sending') {
      recordButton.hidden = mode !== 'idle';
      stopButton.hidden = mode !== 'recording';
      sendAgainButton.hidden = discardButton.hidden = mode !== 'unsent';
    }
    controls.forEach((control) => { control.disabled = mode === 'sending' || (control === fileInput && mode !== 'idle'); });
    form.lock(mode === 'recording' || mode === 'sending');
  }

  function readSetup() {
    const setup = form.read();
    const message = validateSetup(setup, score.bars);
    if (message) reportError(new Error(message));
    return message ? null : setup;
  }

  async function openFor(kind) {
    const ticket = ++opening;
    closeStream();
    status.textContent = WAITING_TEXT;
    try {
      const opened = await openStream({ video: kind === 'video' });
      if (disposed || ticket !== opening) {
        stopStream(opened.stream);
        return false;
      }
      current = opened;
      if (opened.cameraError) showNotice(`${opened.cameraError.message} Recording audio only.`);
      if (opened.hasVideo) camera.attach(opened.stream);
      problem.replaceChildren();
      return true;
    } catch (err) {
      if (disposed || ticket !== opening) return false;
      if (err.name !== 'MediaAccessError') throw err;
      renderMediaError(problem, err, { onTryAgain: () => openFor(form.read().kind), onUpload: () => fileInput.click() });
      return false;
    } finally {
      if (ticket === opening) status.textContent = '';
    }
  }

  function closeStream() {
    camera.detach();
    if (current) stopStream(current.stream);
    current = null;
  }

  async function switchKind(kind) {
    rememberCamera(kind === 'video');
    problem.replaceChildren();
    if (kind === 'video') await openFor('video');
    else closeStream();
  }

  async function startRecording() {
    // Started inside the tap itself, before the permission prompt: Safari only lets audio run when the tap starts it.
    getAudioContext().catch((err) => console.error('Audio could not be unlocked by the Record tap:', err));
    clearBanner();
    const setup = readSetup();
    if (!setup) return;
    if (!current || current.hasVideo !== (setup.kind === 'video')) {
      if (!(await openFor(setup.kind))) return;
    }
    camera.pauseChecks();
    setMode('sending'); // Stop only works once the recorder has started
    let handle = null;
    try {
      handle = await recordTake({
        stream: current.stream, tempoBpm: setup.tempo_bpm, countInBeats: setup.count_in_beats, metronomeOn: setup.metronome_on,
        beatsPerBar: score.time_signature[0], maxSeconds: RECORD_LIMIT_S, onAutoStop: finishAutoStop,
      });
      if (disposed) { // left while the recorder started: nobody is left to press Stop
        stopHandle(handle, 'Stopping the recording that started after leaving');
        return;
      }
      recording = { handle, kind: current.hasVideo ? 'video' : 'mic', meter: NO_METER }; // set first, so leaving during the meter start stops it
      const meter = await startMeter();
      if (disposed) {
        meter.stop();
        return;
      }
      recording.meter = meter;
      status.textContent = setup.count_in_beats ? 'Counting in, then recording. Press Stop when you finish.' : 'Recording. Press Stop when you finish.';
      setMode('recording');
    } catch (err) {
      if (disposed) return console.error('Starting the recording failed after leaving the screen:', err);
      if (handle) { // the recorder and metronome are running but the screen could not go on: stop them
        stopHandle(handle, 'Stopping the recording that failed to start');
        endRecording();
        console.error('The recording failed to start:', err);
        err = new Error(START_FAILED_TEXT);
      }
      reportError(err);
      setMode('idle');
      if (current && current.hasVideo) camera.attach(current.stream);
    }
  }

  function stopHandle(handle, what) {
    handle.stop().catch((err) => console.error(`${what} failed:`, err));
  }

  // The level meter is only a help: if it fails the take goes on without it.
  async function startMeter() {
    try {
      return await renderLevelMeter(meterBox, current.stream);
    } catch (err) {
      console.error('The microphone level meter could not start:', err);
      return { stop() {} };
    }
  }

  function endRecording() {
    if (recording) recording.meter.stop();
    recording = null;
    status.textContent = '';
  }

  async function stopRecording() {
    setMode('sending');
    try {
      const kind = recording.kind;
      const result = await recording.handle.stop();
      if (!result.autoStopped) await finishRecording(result, kind); // an auto-stop is finished by finishAutoStop
    } catch (err) {
      endRecording();
      if (disposed) return console.error('Stopping the recording failed after leaving the screen:', err);
      reportError(err);
      setMode('idle');
    }
  }

  async function finishAutoStop(result, err) {
    if (disposed) return;
    if (err) {
      endRecording();
      reportError(err);
      setMode('idle');
      return;
    }
    setMode('sending');
    showNotice(result.message);
    await finishRecording(result, recording.kind);
  }

  async function finishRecording(result, kind) {
    if (disposed) return console.warn('The take was recorded after leaving the screen, so it was not sent.');
    endRecording();
    closeStream(); // the take is complete; the camera and mic are free again
    unsent = { result, kind };
    await sendUnsent();
  }

  // Sends one file or recording with the current setup. True when the server accepted it.
  async function send({ file, kind, source, downbeatS }) {
    const setup = readSetup();
    if (!setup) return false;
    setMode('sending');
    try {
      const fields = takeFields(setup, { kind, source, downbeatS });
      const answer = await uploadTake(state.session_id, file, fields);
      if (disposed) { // the learner left while it uploaded: do not pull them back to the results
        console.warn(`Take ${answer.take_id} finished uploading after leaving the take screen.`);
        return true;
      }
      state.current_take_id = answer.take_id;
      state.last_take_upload = { take_id: answer.take_id, file, fields };
      state.take_setup = { ...setup };
      window.location.hash = `#/results/${encodeURIComponent(answer.take_id)}`;
      return true;
    } catch (err) {
      if (disposed) {
        console.error('The upload failed after leaving the take screen:', err);
        return false;
      }
      reportError(err); // the inputs and the recording stay as they are
      return false;
    }
  }

  async function sendUnsent() {
    const { result, kind } = unsent;
    const sent = await send({ file: result.file, kind, source: 'recorded', downbeatS: result.downbeat_s });
    setMode(sent ? 'idle' : 'unsent');
  }

  function discardUnsent() {
    unsent = null;
    clearBanner();
    setMode('idle');
    if (form.read().kind === 'video') openFor('video');
  }

  async function uploadChosenFile() {
    const [file] = fileInput.files;
    fileInput.value = ''; // so choosing the same file again still counts as a change
    if (!file) return;
    await send({ file, kind: kindOfFile(file), source: 'uploaded' });
    setMode('idle');
  }

  function dispose() {
    disposed = true;
    opening += 1;
    if (recording) stopHandle(recording.handle, 'Stopping the recording on leaving');
    endRecording();
    closeStream();
  }
  window.addEventListener('hashchange', dispose, { once: true });

  root.append(
    el('h1', { text: 'Record a take' }),
    form.element,
    camera.element,
    problem,
    el('p', { className: 'muted', text: MIC_REASON }),
    el('p', { className: 'take-actions', children: [recordButton, stopButton, sendAgainButton, discardButton] }),
    meterBox,
    status,
    el('p', { className: 'muted', text: 'Or upload an existing audio or video file. It is sent with the tempo above.' }),
    fileInput,
    el('p', { children: [el('a', { text: 'Fine-tune for your room and microphone (optional)', attrs: { href: '#/calibrate' } })] }),
  );
  setMode('idle');
  if (form.read().kind === 'video') await openFor('video');
}

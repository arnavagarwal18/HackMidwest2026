// The loop trainer's behaviour: load the exercise, record a rep, send it, poll the score, show the result, arm the next rep.
// It takes the API and recording functions as `deps` (screens/exercise.js passes the real ones), so node tests can drive it.
import { reportError, showNotice } from '../banner.js';
import { pollUntilDone } from '../results/polling.js';
import {
  REP_MAX_SECONDS, asPolled, historyAfterRep, recordKind, repWasScored, stateAfterRep, wantsVideo,
} from './model.js';
import { renderTrainer } from './view.js';
import { element } from '../dom.js';

const BUSY_PHASES = ['loading', 'recording', 'sending', 'scoring', 'complete'];
const SPACE_PHASES = ['ready', 'result', 'not_counted', 'recording'];
const KEYS_THAT_OWN_SPACE = ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'A', 'SUMMARY'];

// options: { sessionId, ex, beatsPerBar, countInBeats, metronomeOn, onFullTake, thresholds }
// deps: { getExercise, uploadRep, getRep, openStream, recordTake, stopStream }
export function createTrainer(root, options, deps) {
  const { sessionId, ex } = options;
  const host = element('div', '', 'trainer-host');
  root.append(host);
  const model = { exercise: null, xstate: null, phase: 'loading', rep: null, slow: false, mediaError: null, history: [] };
  let alive = true;
  let starting = false;
  let stream = null;
  let take = null; // the recording in progress
  let recordedKind = 'mic';
  let pending = null; // { file, fields } kept in memory until the upload works
  let repId = null;

  const isActive = () => alive && host.isConnected;
  const paint = () => { if (alive) renderTrainer(host, model, handlers); };
  const setPhase = (phase) => { model.phase = phase; paint(); };
  const releaseStream = () => {
    if (stream) deps.stopStream(stream);
    stream = null;
  };
  const fail = (err, phase) => {
    if (!alive) { console.error('A request failed after leaving the exercise screen:', err); return; }
    reportError(err);
    setPhase(phase);
  };

  async function readExercise() {
    const loaded = await deps.getExercise(sessionId, ex);
    model.exercise = loaded.exercise;
    model.xstate = loaded.state;
  }

  async function load() {
    model.phase = 'loading';
    paint();
    try {
      await readExercise();
      setPhase(model.xstate.complete ? 'complete' : 'ready');
    } catch (err) {
      fail(err, 'load_failed');
    }
  }

  async function openRecorderStream() {
    if (stream) return;
    const opened = await deps.openStream({ video: wantsVideo(model.exercise) });
    stream = opened.stream;
    recordedKind = recordKind(model.exercise, opened.hasVideo);
    if (opened.cameraError) showNotice(`${opened.cameraError.message} Recording the sound only.`);
  }

  async function beginRep() {
    if (starting || BUSY_PHASES.includes(model.phase) || model.xstate?.complete) return;
    starting = true;
    model.slow = false;
    try {
      await readExercise(); // the back end owns the tempo: read it again before every rep
      if (!alive) return;
      if (model.xstate.complete) { setPhase('complete'); return; }
      await openRecorderStream();
      if (!alive) { releaseStream(); return; }
      take = await deps.recordTake({
        stream, tempoBpm: model.xstate.current_bpm, countInBeats: options.countInBeats, metronomeOn: options.metronomeOn,
        beatsPerBar: options.beatsPerBar, maxSeconds: REP_MAX_SECONDS, onAutoStop: handleAutoStop,
      });
      if (!alive) {
        take.stop().catch((err) => console.error('Stopping the recording after leaving failed:', err));
        releaseStream();
        return;
      }
      pending = null;
      setPhase('recording');
    } catch (err) {
      if (err.name === 'MediaAccessError') {
        model.mediaError = err;
        if (alive) setPhase('media_error');
      } else {
        fail(err, 'ready');
      }
    } finally {
      starting = false;
    }
  }

  const recordedUpload = (recorded) => ({
    file: recorded.file, fields: { kind: recordedKind, source: 'recorded', downbeat_s: recorded.downbeat_s },
  });

  async function finishRep() {
    const recording = take;
    take = null;
    setPhase('sending');
    try {
      await send(recordedUpload(await recording.stop()));
    } catch (err) {
      fail(err, 'ready');
    }
  }

  function handleAutoStop(recorded, err) {
    if (model.phase !== 'recording' || !take) return;
    take = null;
    if (err) { fail(err, 'ready'); return; }
    showNotice(recorded.message);
    setPhase('sending');
    send(recordedUpload(recorded));
  }

  // Sends the rep; the file stays in `pending` so Send again can repeat it after an error.
  async function send(upload = pending) {
    pending = upload;
    if (model.phase !== 'sending') setPhase('sending');
    let accepted;
    try {
      accepted = await deps.uploadRep(sessionId, ex, pending.file, pending.fields);
    } catch (err) {
      fail(err, 'send_failed');
      return;
    }
    pending = null;
    repId = accepted.rep_id;
    await score();
  }

  function showRep(rep) {
    model.rep = rep;
    if (!repWasScored(rep)) { setPhase('not_counted'); return; }
    model.xstate = stateAfterRep(model.xstate, rep);
    model.history = historyAfterRep(model.history, rep);
    setPhase('result');
  }

  async function score() {
    model.slow = false;
    setPhase('scoring');
    try {
      const polled = await pollUntilDone({
        fetchOnce: async () => asPolled(await deps.getRep(sessionId, ex, repId)),
        isActive,
        thresholds: options.thresholds,
        onTick: ({ slow }) => { if (slow !== model.slow) { model.slow = slow; paint(); } },
      });
      if (polled.outcome === 'done') showRep(polled.result);
      else if (polled.outcome === 'timeout') setPhase('too_long');
    } catch (err) {
      fail(err, 'check_failed');
    }
  }

  async function checkAgain() {
    try {
      const rep = asPolled(await deps.getRep(sessionId, ex, repId));
      if (!alive) return;
      if (rep.done) showRep(rep);
      else setPhase('too_long');
    } catch (err) {
      fail(err, 'check_failed');
    }
  }

  const handlers = {
    onPrimary: () => (model.phase === 'recording' ? finishRep() : beginRep()),
    onRecordAgain: beginRep,
    onTryAgain: () => (model.phase === 'load_failed' ? load() : beginRep()),
    onCheckAgain: checkAgain,
    onSendAgain: () => send(),
    onUpload: () => setPhase('upload'),
    onFile: (file) => {
      if (!file) return;
      send({ file, fields: { kind: file.type.startsWith('video/') ? 'video' : 'mic', source: 'uploaded' } });
    },
    onFullTake: options.onFullTake,
  };

  function onKeyDown(event) {
    if (!isActive()) { destroy(); return; }
    if (event.code !== 'Space' || event.repeat || KEYS_THAT_OWN_SPACE.includes(event.target?.tagName)) return;
    event.preventDefault();
    if (SPACE_PHASES.includes(model.phase)) handlers.onPrimary();
  }

  function destroy() {
    if (!alive) return;
    alive = false;
    document.removeEventListener('keydown', onKeyDown);
    window.removeEventListener('hashchange', destroy);
    if (take) take.stop().catch((err) => console.error('Stopping the recording after leaving failed:', err));
    take = null;
    releaseStream();
  }

  document.addEventListener('keydown', onKeyDown);
  window.addEventListener('hashchange', destroy);
  return { start: load, destroy, model };
}

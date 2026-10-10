// The loop trainer against a fake back end that applies the LLD-6 rules. Run: node --test frontend/tests/exercise_trainer.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { MediaAccessError } from '../js/media_error.js';
import { createTrainer } from '../js/exercise/trainer.js';
import { installFakeDom, settle, space } from './fake_dom.mjs';

const FAST = { intervalMs: 2, slowAfterMs: 1_000_000, giveUpAfterMs: 1_000_000 };
const EXERCISE = {
  id: 'ex1', title: 'Bars 3 to 4 slowly', text: 'Play it slowly, then speed up.', bar_from: 3, bar_to: 4,
  start_bpm: 60, target_bpm: 72, step_bpm: 6, reps_to_pass: 2,
  pass_mark: { max_errors: 0, max_mean_timing_ms: 60, form_rule: null },
};

// A back end for one exercise: each upload takes the next scripted outcome ('pass', 'fail' or 'not_counted').
// Rules: reps_to_pass passes in a row step the tempo up (and passing the target completes it); 2 fails in a row step it down.
function fakeBackend(outcomes, exercise = EXERCISE) {
  const xs = { plan_id: 'p', current_bpm: exercise.start_bpm, streak: 0, fails_in_row: 0, best_passed_bpm: null, complete: false, rep_ids: [], added_by: 'plan' };
  const reps = new Map();
  const calls = { uploads: [], getExercise: 0, getRep: 0 };
  const result = (outcome, tempo) => {
    if (outcome === 'not_counted') return { take_id: 't', exercise_id: exercise.id, tempo_bpm: tempo, status: 'not_counted', passed: null, reasons: ['No notes were heard'], next_bpm: xs.current_bpm, streak: xs.streak, exercise_complete: false };
    const passed = outcome === 'pass';
    const reasons = passed ? [] : ['2 errors, pass mark 0', 'mean timing 72 ms, pass mark 60 ms'];
    if (passed) {
      xs.streak += 1;
      xs.fails_in_row = 0;
      xs.best_passed_bpm = Math.max(xs.best_passed_bpm ?? 0, tempo);
      if (xs.streak >= exercise.reps_to_pass) {
        if (tempo >= exercise.target_bpm) xs.complete = true;
        else xs.current_bpm = Math.min(tempo + exercise.step_bpm, exercise.target_bpm);
        xs.streak = 0;
      }
    } else {
      xs.streak = 0;
      xs.fails_in_row += 1;
      if (xs.fails_in_row >= 2) { xs.current_bpm = Math.max(tempo - exercise.step_bpm, exercise.start_bpm); xs.fails_in_row = 0; }
    }
    return { take_id: 't', exercise_id: exercise.id, tempo_bpm: tempo, status: 'scored', passed, reasons, errors: passed ? 0 : 2, mean_abs_timing_ms: 40, form_flag_ids: [], next_bpm: xs.current_bpm, streak: xs.streak, exercise_complete: xs.complete };
  };
  return {
    calls,
    xs,
    deps: {
      async getExercise() { calls.getExercise += 1; return { exercise, state: { ...xs } }; },
      async uploadRep(_sid, _ex, file, fields) {
        calls.uploads.push({ file, fields });
        const id = `rep_${calls.uploads.length}`;
        const tempo = xs.current_bpm;
        reps.set(id, { tempo, ready: false });
        reps.get(id).result = result(outcomes.shift() ?? 'pass', tempo);
        return { rep_id: id, tempo_bpm: tempo, status: 'processing' };
      },
      async getRep(_sid, _ex, repId) {
        calls.getRep += 1;
        const rep = reps.get(repId);
        if (!rep.ready) { rep.ready = true; return { take_id: null, exercise_id: exercise.id, tempo_bpm: rep.tempo, status: 'processing', passed: null, reasons: [] }; }
        return rep.result;
      },
    },
  };
}

function fakeRecorder({ video = false, cameraError = null, openError = null } = {}) {
  const log = { opened: 0, stopped: 0, takes: [], stops: 0 };
  return {
    log,
    deps: {
      async openStream(options) {
        log.opened += 1;
        log.openOptions = options;
        if (openError) throw openError;
        return { stream: { id: 's' }, hasVideo: video && !cameraError, cameraError };
      },
      async recordTake(options) {
        log.takes.push(options);
        const file = { name: `rec${log.takes.length}.webm` };
        return { stop: async () => { log.stops += 1; return { file, downbeat_s: 0.5 + (4 * 60) / options.tempoBpm, message: null }; } };
      },
      stopStream() { log.stopped += 1; },
    },
  };
}

async function setup({ outcomes = [], exercise = EXERCISE, recorder = {}, tweak = (deps) => deps } = {}) {
  const dom = installFakeDom();
  const backend = fakeBackend(outcomes, exercise);
  const rec = fakeRecorder(recorder);
  const root = dom.document.createElement('main');
  dom.body.append(root);
  const full = { count: 0 };
  const trainer = createTrainer(root, {
    sessionId: 's1', ex: exercise.id, beatsPerBar: 4, countInBeats: 4, metronomeOn: false, thresholds: FAST,
    onFullTake: () => { full.count += 1; },
  }, tweak({ ...backend.deps, ...rec.deps }));
  await trainer.start();
  const press = async () => { dom.document.dispatch('keydown', space()); await settle(); }; // space: start or stop
  const playRep = async () => { await press(); await press(); await settle(); }; // start, then stop; wait for the score
  return { dom, backend, rec, root, trainer, full, press, playRep, text: (name) => root.texts(name), view: () => root };
}

test('shows the exercise card, streak dots and ladder', async () => {
  const t = await setup();
  assert.deepEqual(t.text('exercise-card').length, 1);
  assert.ok(t.root.all().some((n) => n.tagName === 'H1' && n.textContent === 'Bars 3 to 4 slowly'));
  assert.ok(t.text('exercise-card')[0].includes('Play it slowly, then speed up.'));
  assert.ok(t.text('pass-mark')[0].includes('No wrong or missed notes and average timing within 60 ms'));
  assert.equal(t.text('current-tempo')[0], 'Current tempo: 60 BPM');
  assert.equal(t.root.withClass('dot').length, 2);
  assert.equal(t.root.withClass('filled').length, 0);
  assert.deepEqual(t.root.withClass('step').map((n) => n.textContent), ['60', '66', '72']);
  assert.equal(t.text('next-rep')[0], 'Rep at 60 BPM - press space');
  t.trainer.destroy();
});

test('walks the ladder: PASS fills dots, tempo steps up after reps_to_pass passes, down after 2 fails, Done at the target', async () => {
  const t = await setup({ outcomes: ['pass', 'pass', 'fail', 'fail', 'pass', 'pass', 'pass', 'pass', 'pass'] });
  await t.playRep(); // pass at 60
  assert.equal(t.text('verdict')[0], 'PASS');
  assert.equal(t.root.withClass('filled').length, 1);
  assert.equal(t.text('next-rep')[0], 'Next rep at 60 BPM - press space');
  await t.playRep(); // second pass: tempo up
  assert.equal(t.text('verdict')[0], 'PASS');
  assert.equal(t.text('tempo-change')[0], 'Tempo up: 60 to 66 BPM');
  assert.equal(t.text('next-rep')[0], 'Next rep at 66 BPM - press space');
  await t.playRep(); // fail at 66
  assert.equal(t.text('verdict')[0], 'FAIL');
  assert.deepEqual(t.text('reasons').length, 1);
  assert.ok(t.root.withClass('reasons')[0].children.map((li) => li.textContent).includes('2 errors, pass mark 0'));
  assert.equal(t.root.withClass('filled').length, 0);
  assert.equal(t.text('tempo-change')[0], 'Staying at 66 BPM');
  await t.playRep(); // second fail in a row: tempo down
  assert.equal(t.text('tempo-change')[0], 'Tempo down: 66 to 60 BPM');
  assert.equal(t.text('next-rep')[0], 'Next rep at 60 BPM - press space');
  for (let i = 0; i < 4; i += 1) await t.playRep(); // 60 up to 66, 66 up to 72
  assert.equal(t.text('next-rep')[0], 'Next rep at 72 BPM - press space');
  await t.playRep(); // first pass at the target
  assert.deepEqual(t.text('verdict'), ['PASS']);
  await t.playRep(); // second pass at the target: done
  assert.deepEqual(t.text('verdict'), ['PASS', 'Done']);
  assert.ok(t.root.button('Record a full take'));
  assert.equal(t.root.button('Record rep'), undefined);
  t.root.button('Record a full take').click();
  assert.equal(t.full.count, 1);
  const tempos = t.rec.log.takes.map((take) => take.tempoBpm);
  assert.deepEqual(tempos, [60, 60, 66, 66, 60, 60, 66, 66, 72, 72].slice(0, tempos.length));
  assert.equal(t.rec.log.takes.every((take) => take.maxSeconds === 60 && take.countInBeats === 4), true);
  t.trainer.destroy();
});

test('sends the rep with kind, source and downbeat only; opens the microphone once', async () => {
  const t = await setup({ outcomes: ['pass', 'pass'] });
  await t.playRep();
  await t.playRep();
  assert.equal(t.rec.log.opened, 1);
  assert.deepEqual(t.backend.calls.uploads[0].fields, { kind: 'mic', source: 'recorded', downbeat_s: 0.5 + 4 });
  assert.equal(t.rec.log.openOptions.video, false);
  t.trainer.destroy();
});

test('reads the exercise state before every rep', async () => {
  const t = await setup({ outcomes: ['pass'] });
  assert.equal(t.backend.calls.getExercise, 1);
  await t.playRep();
  assert.equal(t.backend.calls.getExercise, 2); // the load, then the first rep
  await t.press(); // second rep starts: one more read
  assert.equal(t.backend.calls.getExercise, 3);
  t.trainer.destroy();
});

test('an exercise that is already complete shows Done and offers no rep', async () => {
  const t = await setup();
  t.trainer.destroy();
  const dom = installFakeDom();
  const backend = fakeBackend([]);
  backend.xs.complete = true;
  const root = dom.document.createElement('main');
  dom.body.append(root);
  const trainer = createTrainer(root, { sessionId: 's1', ex: 'ex1', thresholds: FAST, onFullTake() {} }, { ...backend.deps, ...fakeRecorder().deps });
  await trainer.start();
  assert.deepEqual(root.texts('verdict'), ['Done']);
  assert.equal(root.button('Record rep'), undefined);
  dom.document.dispatch('keydown', space());
  await settle();
  assert.equal(backend.calls.uploads.length, 0);
  trainer.destroy();
});

test('a rep that does not count shows the back end message and Record again, with no automatic retry', async () => {
  const t = await setup({ outcomes: ['not_counted'] });
  await t.playRep();
  assert.deepEqual(t.root.withClass('reasons')[0].children.map((li) => li.textContent), ['No notes were heard']);
  assert.ok(t.root.button('Record again'));
  assert.equal(t.root.withClass('verdict').length, 0);
  await settle();
  assert.equal(t.backend.calls.uploads.length, 1);
  assert.equal(t.rec.log.takes.length, 1);
  t.root.button('Record again').click();
  await settle();
  assert.equal(t.rec.log.takes.length, 2);
  assert.equal(t.rec.log.takes[1].tempoBpm, 60); // the same setup
  t.trainer.destroy();
});

test('a refused upload shows the message in the red banner and keeps the recording for Send again', async () => {
  let refuse = true;
  const t = await setup({
    outcomes: ['pass'],
    tweak: (deps) => ({
      ...deps,
      uploadRep: async (...args) => {
        if (refuse) { refuse = false; const err = new Error('Another rep is still being checked.'); err.name = 'ApiError'; throw err; }
        return deps.uploadRep(...args);
      },
    }),
  });
  await t.playRep();
  assert.equal(t.dom.banner.textContent, 'Another rep is still being checked.');
  assert.ok(t.dom.banner.className.includes('error'));
  assert.ok(t.root.button('Send again'));
  assert.equal(t.rec.log.takes.length, 1); // no automatic re-recording
  t.root.button('Send again').click();
  await settle();
  assert.equal(t.backend.calls.uploads.length, 1);
  assert.equal(t.backend.calls.uploads[0].file.name, 'rec1.webm'); // the same file as the first try
  assert.equal(t.text('verdict')[0], 'PASS');
  t.trainer.destroy();
});

test('a blocked microphone shows the media error with Try again and Upload; nothing retries by itself', async () => {
  const t = await setup({ recorder: { openError: new MediaAccessError('mic', 'blocked') } });
  await t.press();
  assert.ok(t.text('media-error')[0].includes('Chrome is blocking the mic'));
  assert.ok(t.root.button('Try again'));
  assert.ok(t.root.button('Upload a recording instead'));
  await settle();
  assert.equal(t.rec.log.opened, 1);
  t.root.button('Try again').click();
  await settle();
  assert.equal(t.rec.log.opened, 2);
  t.root.button('Upload a recording instead').click();
  t.trainer.destroy();
});

test('uploading a file instead sends it as an uploaded rep', async () => {
  const t = await setup({ recorder: { openError: new MediaAccessError('mic', 'missing') }, outcomes: ['pass'] });
  await t.press();
  t.root.button('Upload a recording instead').click();
  const input = t.root.all().find((n) => n.tagName === 'INPUT');
  input.files = [{ name: 'mine.wav', type: 'audio/wav' }];
  input.listeners.change[0]();
  await settle();
  await settle();
  assert.deepEqual(t.backend.calls.uploads[0].fields, { kind: 'mic', source: 'uploaded' });
  assert.equal(t.text('verdict')[0], 'PASS');
  t.trainer.destroy();
});

const VIDEO_EXERCISE = { ...EXERCISE, pass_mark: { ...EXERCISE.pass_mark, form_rule: 'elbow_height' } };

test('an exercise with a form rule records video; if the camera fails it records the sound only and says so', async () => {
  const withCamera = await setup({ exercise: VIDEO_EXERCISE, recorder: { video: true }, outcomes: ['pass'] });
  await withCamera.playRep();
  assert.equal(withCamera.rec.log.openOptions.video, true);
  assert.equal(withCamera.backend.calls.uploads[0].fields.kind, 'video');
  withCamera.trainer.destroy();

  const noCamera = await setup({ exercise: VIDEO_EXERCISE, recorder: { video: true, cameraError: new MediaAccessError('camera', 'missing') }, outcomes: ['pass'] });
  await noCamera.playRep();
  assert.equal(noCamera.backend.calls.uploads[0].fields.kind, 'mic');
  assert.ok(noCamera.dom.banner.textContent.includes('No camera was found'));
  noCamera.trainer.destroy();
});

test('polling: Still working after the slow threshold, This is taking too long at the limit, then Check again and Record again', async () => {
  const dom = installFakeDom();
  const backend = fakeBackend(['pass']);
  let getRepImpl = async () => { backend.calls.getRep += 1; return { status: 'processing', tempo_bpm: 60, reasons: [] }; };
  const root = dom.document.createElement('main');
  dom.body.append(root);
  const trainer = createTrainer(root, {
    sessionId: 's1', ex: 'ex1', beatsPerBar: 4, countInBeats: 4, metronomeOn: false,
    thresholds: { intervalMs: 5, slowAfterMs: 30, giveUpAfterMs: 120 }, onFullTake() {},
  }, { ...backend.deps, getRep: (...args) => getRepImpl(...args), ...fakeRecorder().deps });
  await trainer.start();
  dom.document.dispatch('keydown', space());
  await settle();
  dom.document.dispatch('keydown', space());
  await new Promise((resolve) => setTimeout(resolve, 70));
  assert.deepEqual(root.texts('slow-note'), ['Still working - this can take a while']);
  await new Promise((resolve) => setTimeout(resolve, 150));
  assert.deepEqual(root.texts('stage'), ['This is taking too long']);
  assert.ok(root.button('Check again'));
  assert.ok(root.button('Record again'));
  const polls = backend.calls.getRep;
  await settle();
  assert.equal(backend.calls.getRep, polls); // stopped polling
  getRepImpl = async () => ({ take_id: 't', exercise_id: 'ex1', tempo_bpm: 60, status: 'scored', passed: true, reasons: [], next_bpm: 60, streak: 1, exercise_complete: false });
  root.button('Check again').click();
  await settle();
  assert.deepEqual(root.texts('verdict'), ['PASS']);
  trainer.destroy();
});

test('leaving the screen stops the recording, the microphone and the key listener', async () => {
  const t = await setup();
  await t.press(); // recording
  assert.equal(t.dom.document.count('keydown'), 1);
  assert.equal(t.dom.window.count('hashchange'), 1);
  t.dom.window.dispatch('hashchange'); // the router is about to render another screen
  await settle();
  assert.equal(t.rec.log.stops, 1);
  assert.equal(t.rec.log.stopped, 1);
  assert.equal(t.dom.document.count('keydown'), 0);
  assert.equal(t.dom.window.count('hashchange'), 0);
  await t.press();
  assert.equal(t.backend.calls.uploads.length, 0);
});

test('a screen that was replaced without a hashchange cleans up on the next key press', async () => {
  const t = await setup();
  t.root.replaceChildren();
  t.dom.document.dispatch('keydown', space());
  assert.equal(t.dom.document.count('keydown'), 0);
});

test('space is left to a focused button, and held keys are ignored', async () => {
  const t = await setup();
  t.dom.document.dispatch('keydown', space({ target: { tagName: 'BUTTON' } }));
  t.dom.document.dispatch('keydown', space({ repeat: true }));
  await settle();
  assert.equal(t.rec.log.takes.length, 0);
  t.trainer.destroy();
});

test('when the exercise cannot be loaded the red banner shows the message and Try again loads it again', async () => {
  const dom = installFakeDom();
  const backend = fakeBackend([]);
  let failing = true;
  const getExercise = async (...args) => {
    if (failing) { failing = false; throw new Error('That exercise was not found.'); }
    return backend.deps.getExercise(...args);
  };
  const root = dom.document.createElement('main');
  dom.body.append(root);
  const trainer = createTrainer(root, { sessionId: 's1', ex: 'ex1', thresholds: FAST, onFullTake() {} }, { ...backend.deps, getExercise, ...fakeRecorder().deps });
  await trainer.start();
  assert.equal(dom.banner.textContent, 'That exercise was not found.');
  root.button('Try again').click();
  await settle();
  assert.ok(root.button('Record rep'));
  trainer.destroy();
});

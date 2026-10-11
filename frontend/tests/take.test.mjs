// Node tests for the take setup logic. Run: node --test frontend/test/
import assert from 'node:assert/strict';
import test from 'node:test';

import { FakeNode, installFakeBrowser } from './fake_env.mjs';

const env = installFakeBrowser({ search: '' }); // not mock mode, so tests below can stub fetch
env.restore(); // real timers: the setup tests below measure real intervals
const makeSvgNode = document.createElementNS;
document.createElementNS = (ns, tag) => Object.assign(makeSvgNode(ns, tag), { dataset: {} }); // the camera guide sets data-attributes

const { initialSetup, validateSetup, takeFields, kindOfFile } = await import('../js/take/setup.js');
const { describeCameraCheck, IN_FRAME_TEXT } = await import('../js/take/camera_status.js');
const { createCameraChecker, CHECK_INTERVAL_MS } = await import('../js/take/camera_checker.js');
const { uploadTake, checkCamera } = await import('../js/api.js');
const { apiViewOf } = await import('../js/take/camera_view.js');
const { UPLOAD_ACCEPT, UNSUPPORTED_FILE_TEXT, uploadTypeProblem } = await import('../js/take/upload_types.js');
const { state } = await import('../js/state.js');
const { render } = await import('../js/screens/take.js');

const SCORE = { bars: 16, tempo_bpm: 96, time_signature: [3, 4] };
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test('defaults come from the score, with one bar of count-in', () => {
  assert.deepEqual(initialSetup(SCORE, { bar_from: null, bar_to: null, tempo_bpm: null, kind: null, count_in_beats: null, metronome_on: false }),
    { bar_from: 1, bar_to: 16, tempo_bpm: 96, kind: 'mic', count_in_beats: 3, metronome_on: false });
});

test('a saved setup (Record again, loop trainer range) wins over the defaults', () => {
  const setup = initialSetup(SCORE, { bar_from: 5, bar_to: 8, tempo_bpm: 70, kind: 'video', count_in_beats: 2, metronome_on: true });
  assert.deepEqual(setup, { bar_from: 5, bar_to: 8, tempo_bpm: 70, kind: 'video', count_in_beats: 2, metronome_on: true });
  assert.equal(initialSetup(SCORE, { bar_from: 5, bar_to: 8 }).tempo_bpm, 96);
});

test('validateSetup explains what is wrong', () => {
  const good = initialSetup(SCORE);
  assert.equal(validateSetup(good, 16), null);
  assert.match(validateSetup({ ...good, bar_to: 17 }, 16), /1 to 16/);
  assert.match(validateSetup({ ...good, bar_from: 9, bar_to: 4 }, 16), /not after/);
  assert.match(validateSetup({ ...good, tempo_bpm: 20 }, 16), /between 30 and 240/);
  assert.match(validateSetup({ ...good, count_in_beats: 9 }, 16), /0 to 8/);
  assert.match(validateSetup({ ...good, bar_from: NaN }, 16), /numbers/);
});

test('camera badge text', () => {
  assert.deepEqual(describeCameraCheck({ ok: true, missing: [], too_small: false, too_dark: false }), { ok: true, text: IN_FRAME_TEXT });
  assert.equal(IN_FRAME_TEXT, 'In frame');
  assert.deepEqual(describeCameraCheck({ ok: false, missing: ['right elbow'], too_small: false, too_dark: false }),
    { ok: false, text: 'Move back: right elbow not in view' });
  assert.equal(describeCameraCheck({ ok: false, missing: ['right elbow', 'left hand'], too_small: false, too_dark: false }).text,
    'Move back: right elbow and left hand not in view');
  const both = describeCameraCheck({ ok: false, missing: [], too_small: true, too_dark: true }).text;
  assert.match(both, /Move closer/);
  assert.match(both, /more light/);
  assert.match(describeCameraCheck({ ok: false, missing: [], too_small: false, too_dark: false }).text, /Adjust your position/);
});

test('checks run at most once per interval, report answers, and stop when asked', async () => {
  assert.equal(CHECK_INTERVAL_MS, 1000);
  const times = [];
  const answers = [];
  const checker = createCameraChecker({
    intervalMs: 40,
    captureFrame: async () => 'jpeg',
    check: async () => { times.push(Date.now()); return { ok: times.length > 1, missing: ['right elbow'] }; },
    onResult: (answer) => answers.push(answer.ok),
    onFailure: assert.fail,
  });
  checker.start();
  checker.start(); // a second start must not add a second loop
  await wait(200);
  checker.stop();
  const callsAtStop = times.length;
  assert.ok(callsAtStop >= 3 && callsAtStop <= 5, `calls: ${callsAtStop}`);
  times.slice(1).forEach((t, i) => assert.ok(t - times[i] >= 38, 'checks must be spaced by the interval'));
  assert.equal(answers[0], false);
  assert.equal(answers[1], true);
  await wait(120);
  assert.equal(times.length, callsAtStop, 'no checks after stop');
});

test('an answer that arrives after stop is dropped', async () => {
  const answers = [];
  const checker = createCameraChecker({
    intervalMs: 10,
    captureFrame: async () => 'jpeg',
    check: async () => { await wait(30); return { ok: true }; },
    onResult: (answer) => answers.push(answer),
    onFailure: assert.fail,
  });
  checker.start();
  await wait(15);
  checker.stop();
  await wait(60);
  assert.deepEqual(answers, []);
});

test('a failed check stops the loop and reports the error once', async () => {
  const failures = [];
  let calls = 0;
  const originalError = console.error;
  console.error = () => {};
  const checker = createCameraChecker({
    intervalMs: 10,
    captureFrame: async () => 'jpeg',
    check: async () => { calls += 1; throw Object.assign(new Error('unavailable'), { code: 'form_unavailable' }); },
    onResult: assert.fail,
    onFailure: (err) => failures.push(err.code),
  });
  checker.start();
  await wait(80);
  console.error = originalError;
  assert.deepEqual(failures, ['form_unavailable']);
  assert.equal(calls, 1);
  assert.equal(checker.running, false);
});

test('frames with no picture yet are skipped', async () => {
  let checks = 0;
  const checker = createCameraChecker({
    intervalMs: 10,
    captureFrame: async () => null,
    check: async () => { checks += 1; },
    onResult: assert.fail,
    onFailure: assert.fail,
  });
  checker.start();
  await wait(50);
  checker.stop();
  assert.equal(checks, 0);
});

function stubFetch(status, body) {
  const sent = [];
  globalThis.fetch = async (url, options) => {
    sent.push({ url, options });
    return { ok: status < 400, status, json: async () => body };
  };
  return sent;
}

test('a recorded take posts the file and every field', async () => {
  const sent = stubFetch(202, { take_id: 'take_9', status: 'processing' });
  const setup = { ...initialSetup(SCORE), bar_from: 2, bar_to: 6, tempo_bpm: 80, count_in_beats: 4 };
  const file = new File([new Uint8Array([1, 2, 3])], 'recording.webm', { type: 'video/webm' });
  const answer = await uploadTake('sess_1', file, takeFields(setup, { kind: 'video', source: 'recorded', downbeatS: 3.5 }));
  assert.equal(answer.take_id, 'take_9');
  assert.equal(sent[0].url, '/sessions/sess_1/takes');
  assert.equal(sent[0].options.method, 'POST');
  const form = sent[0].options.body;
  assert.deepEqual(Object.fromEntries([...form.entries()].filter(([, v]) => typeof v === 'string')),
    { kind: 'video', source: 'recorded', bar_from: '2', bar_to: '6', tempo_bpm: '80', count_in_beats: '4', downbeat_s: '3.5' });
  assert.equal(form.get('file').name, 'recording.webm');
});

test('an uploaded file has no downbeat_s and its kind follows its type', async () => {
  const sent = stubFetch(202, { take_id: 'take_10', status: 'processing' });
  const audio = new File([new Uint8Array([1])], 'take.wav', { type: 'audio/wav' });
  assert.equal(kindOfFile(audio), 'mic');
  assert.equal(kindOfFile(new File([], 'a.mp4', { type: 'video/mp4' })), 'video');
  await uploadTake('sess_1', audio, takeFields(initialSetup(SCORE), { kind: kindOfFile(audio), source: 'uploaded' }));
  const form = sent[0].options.body;
  assert.equal(form.get('source'), 'uploaded');
  assert.equal(form.has('downbeat_s'), false);
});

test('a 422 bad_request throws the server message so the screen can show it', async () => {
  stubFetch(422, { error: { code: 'bad_request', message: 'The score has 16 bars. Pick bars within it.' } });
  const file = new File([new Uint8Array([1])], 'take.wav', { type: 'audio/wav' });
  await assert.rejects(
    uploadTake('sess_1', file, takeFields({ ...initialSetup(SCORE), bar_to: 40 }, { kind: 'mic', source: 'uploaded' })),
    (err) => err.name === 'ApiError' && err.code === 'bad_request' && err.status === 422 && /16 bars/.test(err.message),
  );
});

// ---- The screen: leaving it while the recorder starts, while a stop or an upload is running ----

// Counts the running setInterval (metronome) and long setTimeout (180 s cap) timers, so a test can see they were stopped.
function trackTimers() {
  const { setInterval: realSetInterval, clearInterval: realClearInterval, setTimeout: realSetTimeout, clearTimeout: realClearTimeout } = globalThis;
  const running = new Set();
  globalThis.setInterval = (...args) => { const id = realSetInterval(...args); running.add(id); return id; };
  globalThis.clearInterval = (id) => { running.delete(id); realClearInterval(id); };
  globalThis.clearTimeout = (id) => { running.delete(id); realClearTimeout(id); };
  globalThis.setTimeout = (fn, ms, ...args) => {
    const id = realSetTimeout(fn, ms, ...args);
    if (ms >= 100_000) running.add(id);
    return id;
  };
  return {
    get running() { return running.size; },
    restore() {
      running.forEach((id) => { realClearInterval(id); realClearTimeout(id); });
      Object.assign(globalThis, { setInterval: realSetInterval, clearInterval: realClearInterval, setTimeout: realSetTimeout, clearTimeout: realClearTimeout });
    },
  };
}

// Makes every MediaRecorder wait for release() before it reports that it started.
function holdRecorderStart() {
  const Real = globalThis.MediaRecorder;
  const recorders = [];
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  globalThis.MediaRecorder = class extends Real {
    constructor(...args) { super(...args); recorders.push(this); }
    start() { this.state = 'recording'; gate.then(() => this.emit('start')); }
  };
  return { recorders, release, restore: () => { globalThis.MediaRecorder = Real; } };
}

function recordFetchCalls(answer) {
  const calls = [];
  globalThis.fetch = (url, options) => new Promise((resolve) => calls.push({ url, options, answer: () => resolve({ ok: true, status: 202, json: async () => answer }) }));
  return calls;
}

async function openTakeScreen() {
  Object.assign(state, { session_id: 'sess_1', instrument: 'trumpet', score: { status: 'confirmed', title: 'Mock piece', ...SCORE }, current_take_id: null });
  window.location.hash = '#/take';
  env.banner.hidden = true;
  const root = new FakeNode('main');
  await render(root);
  root.find((node) => node.tagName === 'input' && node.attrs.type === 'number').forEach((input) => { input.valueAsNumber = Number(input.value); });
  return root;
}

async function untilTrue(condition) {
  for (let i = 0; i < 100 && !condition(); i += 1) await wait(2);
  assert.ok(condition(), 'timed out waiting');
}

// Runs a test body with fake timers tracking, silenced console.error/warn (kept in `logged`) and a clean screen afterwards.
function screenTest(name, body) {
  test(name, async () => {
    const timers = trackTimers();
    const logged = [];
    const real = { error: console.error, warn: console.warn, info: console.info };
    console.error = (...args) => logged.push(args);
    console.warn = (...args) => logged.push(args);
    console.info = (...args) => logged.push(args);
    try {
      await body({ timers, logged });
    } finally {
      env.leave();
      Object.assign(console, real);
      timers.restore();
    }
  });
}

screenTest('leaving while the recorder starts stops the recorder and the metronome', async ({ timers }) => {
  const held = holdRecorderStart();
  try {
    const root = await openTakeScreen();
    const clicked = root.button('Record').click();
    await untilTrue(() => held.recorders.length === 1);
    env.leave();
    held.release();
    await clicked;
    assert.equal(held.recorders[0].state, 'inactive', 'the recorder must be stopped');
    await untilTrue(() => timers.running === 0); // the metronome and the 180 s cap are cleared once the stop finishes
    assert.equal(env.banner.hidden, true, 'nothing is shown on the screen the learner moved to');
  } finally {
    held.restore();
  }
});

screenTest('a failing level meter stops the recorder and tells the learner to try again', async ({ timers, logged }) => {
  const analyserOf = window.AudioContext.prototype.createAnalyser;
  const quiet = console.error;
  window.AudioContext.prototype.createAnalyser = () => { throw new Error('no analyser'); };
  console.error = (...args) => { // a console that throws makes startMeter itself throw
    logged.push(args);
    if (String(args[0]).includes('level meter')) throw new Error('console unavailable');
  };
  try {
    const root = await openTakeScreen();
    const recorders = [];
    const Real = globalThis.MediaRecorder;
    globalThis.MediaRecorder = class extends Real { constructor(...a) { super(...a); recorders.push(this); } };
    await root.button('Record').click();
    globalThis.MediaRecorder = Real;
    assert.equal(recorders[0].state, 'inactive', 'the recorder must be stopped');
    await untilTrue(() => timers.running === 0); // the metronome and the 180 s cap are cleared once the stop finishes
    assert.equal(env.banner.hidden, false);
    assert.match(env.banner.textContent, /could not be started.*Press Record to try again/);
    assert.equal(root.button('Record').hidden, false, 'the learner can press Record again');
    assert.equal(root.button('Stop').hidden, true);
  } finally {
    window.AudioContext.prototype.createAnalyser = analyserOf;
    console.error = quiet;
  }
});

screenTest('an upload that finishes after leaving does not change the page', async ({ logged }) => {
  const fetches = recordFetchCalls({ take_id: 'take_9', status: 'processing' });
  const root = await openTakeScreen();
  const fileInput = root.find((node) => node.tagName === 'input' && node.attrs.type === 'file')[0];
  fileInput.files = [new File([new Uint8Array([1])], 'take.wav', { type: 'audio/wav' })];
  const uploading = fileInput.listeners.change[0]();
  await untilTrue(() => fetches.length === 1);
  window.location.hash = '#/progress'; // the learner moved on while it uploaded
  env.leave();
  fetches[0].answer();
  await uploading;
  assert.equal(window.location.hash, '#/progress');
  assert.equal(state.current_take_id, null);
  assert.ok(logged.some((args) => /after leaving/.test(String(args[0]))), 'the late finish is logged');
});

screenTest('leaving while a stop is finishing does not fail on a closed stream or send the take', async () => {
  const fetches = recordFetchCalls({ take_id: 'take_9' });
  const root = await openTakeScreen();
  await root.button('Record').click();
  const stopping = root.button('Stop').click();
  window.location.hash = '#/progress';
  env.leave(); // closes the stream, so the screen has no current stream when the recording arrives
  await stopping;
  assert.equal(env.banner.hidden, true, 'no TypeError banner on the next screen');
  assert.equal(fetches.length, 0, 'a take recorded after leaving is not sent');
  assert.equal(window.location.hash, '#/progress');
});

// ---- Camera check view field and the upload picker ----

test('the camera panel views map to the server values front, left and right', () => {
  assert.deepEqual(['front', 'side-left', 'side-right'].map(apiViewOf), ['front', 'left', 'right']);
});

test('a camera check sends the picked view, and leaves the field out when there is none', async () => {
  const sent = stubFetch(200, { ok: true, missing: [], too_small: false, too_dark: false });
  const frame = new File([new Uint8Array([1])], 'frame.jpg', { type: 'image/jpeg' });
  await checkCamera('sess_1', frame, 'left');
  await checkCamera('sess_1', frame);
  assert.equal(sent[0].url, '/sessions/sess_1/camera-check');
  assert.equal(sent[0].options.body.get('view'), 'left');
  assert.equal(sent[1].options.body.has('view'), false);
});

test('the file picker is limited to the types the server takes, and others are refused with a message', () => {
  const types = UPLOAD_ACCEPT.split(',');
  ['audio/webm', 'audio/wav', 'audio/ogg', 'video/webm', 'video/mp4', 'video/quicktime'].forEach((type) => assert.ok(types.includes(type), type));
  assert.ok(!types.includes('audio/*') && !types.includes('video/*') && !types.includes('audio/mpeg') && !types.includes('audio/mp4'));
  const fileOf = (name, type) => new File([new Uint8Array([1])], name, { type });
  assert.equal(uploadTypeProblem(fileOf('a.wav', 'audio/x-wav')), null, 'the server accepts the x-wav alias');
  assert.equal(uploadTypeProblem(fileOf('a.webm', 'audio/webm;codecs=opus')), null);
  ['audio/mpeg', 'audio/mp4', 'audio/x-m4a', ''].forEach((type) => assert.equal(uploadTypeProblem(fileOf('a.x', type)), UNSUPPORTED_FILE_TEXT, type));
});

screenTest('an unsupported file is refused before any upload, with a clear message', async () => {
  const fetches = recordFetchCalls({ take_id: 'take_9', status: 'processing' });
  const root = await openTakeScreen();
  const fileInput = root.find((node) => node.tagName === 'input' && node.attrs.type === 'file')[0];
  assert.equal(fileInput.attrs.accept, UPLOAD_ACCEPT);
  fileInput.files = [new File([new Uint8Array([1])], 'take.mp3', { type: 'audio/mpeg' })];
  await fileInput.listeners.change[0]();
  assert.equal(fetches.length, 0, 'nothing is uploaded');
  assert.equal(env.banner.hidden, false);
  assert.match(env.banner.textContent, /isn't supported.*MP3 and M4A/);
});

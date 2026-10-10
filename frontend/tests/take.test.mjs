// Node tests for the take setup logic. Run: node --test frontend/test/
import assert from 'node:assert/strict';
import test from 'node:test';

globalThis.window = { location: { search: '', hash: '' }, localStorage: { getItem: () => null, setItem() {}, removeItem() {} } };

const { initialSetup, validateSetup, takeFields, kindOfFile } = await import('../js/take/setup.js');
const { describeCameraCheck, IN_FRAME_TEXT } = await import('../js/take/camera_status.js');
const { createCameraChecker, CHECK_INTERVAL_MS } = await import('../js/take/camera_checker.js');
const { uploadTake } = await import('../js/api.js');

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

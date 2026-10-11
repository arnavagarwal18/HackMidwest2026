// Node tests for the Play screen (#/take): one Record button, tempo stepper, camera toggle, remembered choices, the mic request and its errors.
// Run: node --test frontend/tests/play.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { FakeNode, installFakeBrowser } from './fake_env.mjs';

const env = installFakeBrowser(); // mock mode: the mock server answers every call
const stored = new Map();
window.localStorage = { getItem: (key) => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value), removeItem: (key) => stored.delete(key) };
const makeSvgNode = document.createElementNS;
document.createElementNS = (ns, tag) => Object.assign(makeSvgNode(ns, tag), { dataset: {} }); // the camera guide sets data-attributes

const { render } = await import('../js/screens/take.js');
const { resetState, state } = await import('../js/state.js');
const { loadPrefs, rememberTempo, setupWithPrefs } = await import('../js/play/prefs.js');

const PREFS_KEY = 'practice_coach_play_prefs_mock';
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function freshVisit() {
  stored.clear();
  resetState();
  Object.assign(state, { session_id: 'sess_mock1', instrument: 'trumpet', score: { status: 'confirmed', bars: 16, tempo_bpm: 96, time_signature: [4, 4] } });
  env.banner.hidden = true;
  window.location.hash = '#/take';
}

async function openPlay() {
  const root = new FakeNode('main');
  await render(root);
  root.find((node) => node.tagName === 'input' && node.attrs.type === 'number').forEach((input) => { input.valueAsNumber = Number(input.value); });
  return root;
}

const input = (root, name) => root.find((node) => node.tagName === 'input' && node.attrs.name === name)[0];
const toggle = async (checkbox, checked) => {
  checkbox.checked = checked;
  await Promise.all(checkbox.listeners.change.map((handler) => handler()));
};

// Replaces getUserMedia for body: `replacement(open, constraints)` may wrap or refuse the real fake.
async function withUserMedia(replacement, body) {
  const { mediaDevices } = navigator;
  const open = mediaDevices.getUserMedia;
  mediaDevices.getUserMedia = (constraints) => replacement(open, constraints);
  const quiet = console.error;
  console.error = () => {}; // a refused device is logged by design
  try {
    await body();
  } finally {
    mediaDevices.getUserMedia = open;
    console.error = quiet;
    env.leave();
  }
}

test('Play has one primary Record button and keeps bars, count-in and metronome under Options', async () => {
  freshVisit();
  const root = await openPlay();
  assert.deepEqual(root.find((node) => node.tagName === 'button' && node.className.includes('primary')).map((node) => node.textContent), ['Record', 'Stop']);
  assert.equal(root.button('Stop').hidden, true, 'only Record shows before recording');
  const more = root.find((node) => node.tagName === 'details')[0];
  for (const name of ['bar_from', 'bar_to', 'count_in_beats', 'metronome_on']) assert.ok(more.find((node) => node.attrs.name === name).length, name);
  assert.equal(input(root, 'tempo_bpm').value, 96);
  assert.ok(root.hasText('Record needs your microphone'), 'the reason for the mic is on screen before any prompt');
  assert.ok(root.find((node) => node.tagName === 'a' && node.attrs.href === '#/calibrate').length, 'Fine-tune link to the QR calibration page');
  env.leave();
});

test('Play opens with the piece title and a Change piece chip to #/score, and still links to Calibrate', async () => {
  freshVisit();
  const root = await openPlay();
  assert.equal(root.find((node) => node.tagName === 'h1')[0].textContent, 'Mock piece', 'the title comes from the score when it is not known yet');
  const chip = root.find((node) => node.tagName === 'a' && node.textContent === 'Change piece')[0];
  assert.equal(chip.attrs.href, '#/score');
  assert.ok(root.find((node) => node.tagName === 'a' && node.attrs.href === '#/calibrate').length, 'Calibrate stays one link away');
  env.leave();
});

test('the tempo stepper moves by 2, stays inside 30..240 and is remembered for this piece', async () => {
  freshVisit();
  const root = await openPlay();
  await root.button('−').click();
  assert.equal(input(root, 'tempo_bpm').valueAsNumber, 94);
  await root.button('+').click();
  await root.button('+').click();
  assert.equal(input(root, 'tempo_bpm').valueAsNumber, 98);
  assert.deepEqual(loadPrefs().tempo, { key: 'sess_mock1', bpm: 98 });
  input(root, 'tempo_bpm').valueAsNumber = 31;
  await root.button('−').click();
  assert.equal(input(root, 'tempo_bpm').valueAsNumber, 30);
  await root.button('−').click();
  assert.equal(input(root, 'tempo_bpm').valueAsNumber, 30, 'never below the minimum');
  input(root, 'tempo_bpm').valueAsNumber = 239;
  await root.button('+').click();
  await root.button('+').click();
  assert.equal(input(root, 'tempo_bpm').valueAsNumber, 240, 'never above the maximum');
  env.leave();
});

test('a remembered tempo and camera setting come back; a tempo saved for another piece does not', () => {
  freshVisit();
  const blank = { bar_from: null, bar_to: null, tempo_bpm: null, kind: null, count_in_beats: null, metronome_on: false };
  assert.deepEqual([setupWithPrefs(blank).tempo_bpm, setupWithPrefs(blank).kind], [null, 'mic'], 'camera is off by default');
  rememberTempo(80);
  stored.set(PREFS_KEY, JSON.stringify({ ...loadPrefs(), camera: true }));
  assert.deepEqual([setupWithPrefs(blank).tempo_bpm, setupWithPrefs(blank).kind], [80, 'video']);
  assert.equal(setupWithPrefs({ ...blank, tempo_bpm: 60, kind: 'mic' }).tempo_bpm, 60, 'the tempo of the last sent take wins');
  state.session_id = 'sess_other';
  assert.equal(setupWithPrefs(blank).tempo_bpm, null);
});

test('a damaged saved-choices entry is logged and the defaults are used', () => {
  freshVisit();
  stored.set(PREFS_KEY, '{not json');
  const logged = [];
  const quiet = console.error;
  console.error = (...args) => logged.push(args.join(' '));
  try {
    assert.deepEqual(loadPrefs(), { tempo: null, camera: false });
  } finally {
    console.error = quiet;
  }
  assert.equal(logged.length, 1);
});

test('the camera is off by default; the Add camera toggle opens it with facingMode ideal and is remembered', async () => {
  freshVisit();
  const calls = [];
  await withUserMedia((open, constraints) => { calls.push(constraints); return open(constraints); }, async () => {
    const root = await openPlay();
    assert.equal(calls.length, 0, 'nothing is requested on load');
    const checkbox = input(root, 'add_camera');
    await toggle(checkbox, true);
    assert.equal(calls.length, 1);
    assert.deepEqual(calls[0].video.facingMode, { ideal: 'user' });
    assert.equal(loadPrefs().camera, true);
    await toggle(checkbox, false);
    assert.equal(loadPrefs().camera, false);
  });
});

test('a remembered camera is on again at the next visit', async () => {
  freshVisit();
  stored.set(PREFS_KEY, JSON.stringify({ camera: true }));
  const calls = [];
  await withUserMedia((open, constraints) => { calls.push(constraints); return open(constraints); }, async () => {
    const root = await openPlay();
    assert.equal(input(root, 'add_camera').checked, true);
    assert.equal(calls.length, 1);
  });
});

test('Record asks for the mic with echo cancellation, noise suppression and auto gain off', async () => {
  freshVisit();
  const calls = [];
  await withUserMedia((open, constraints) => { calls.push(constraints); return open(constraints); }, async () => {
    const root = await openPlay();
    await root.button('Record').click();
    assert.deepEqual(calls[0], { audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
  });
});

test('while the permission prompt is open a waiting hint is shown, and it goes away once answered', async () => {
  freshVisit();
  let allow;
  await withUserMedia((open, constraints) => new Promise((resolve) => { allow = () => resolve(open(constraints)); }), async () => {
    const root = await openPlay();
    const recording = root.button('Record').click();
    await wait(5);
    assert.ok(root.hasText('Waiting for permission'));
    allow();
    await recording;
    assert.ok(!root.hasText('Waiting for permission'));
  });
});

for (const [errorName, expected] of [
  ['NotAllowedError', ['not allowed to use the mic', 'Settings, then Safari, then Camera and Microphone']],
  ['NotFoundError', ['No mic was found']],
  ['NotReadableError', ['Another app may be using the mic']],
]) {
  test(`${errorName} on Record shows its own message with Try again`, async () => {
    freshVisit();
    await withUserMedia(async () => { throw Object.assign(new Error('refused'), { name: errorName }); }, async () => {
      const root = await openPlay();
      await root.button('Record').click();
      expected.forEach((text) => assert.ok(root.hasText(text), text));
      assert.ok(root.button('Try again'));
      assert.ok(!root.hasText('Waiting for permission'));
      assert.equal(root.button('Record').hidden, false, 'the learner can press Record again');
    });
  });
}

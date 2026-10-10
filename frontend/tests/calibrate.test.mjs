// Node tests for the calibration screen and its parts (no browser). Run: node --test frontend/tests/
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { FakeNode, installFakeBrowser } from './fake_env.mjs';

const env = installFakeBrowser();
const { state } = await import('../js/state.js');
const { mockRequestLog } = await import('../js/mock.js');
const { recordClip } = await import('../js/record.js');
const { render } = await import('../js/screens/calibrate.js');
const { createClipStore } = await import('../js/calibrate/clips.js');
const { failuresFromError, renderFailureList, problemText } = await import('../js/calibrate/problems.js');
const { findBaseAddress, toneUrl, LOCALHOST_NOTE } = await import('../js/calibrate/address.js');
const { renderIntro, FALLBACK_LINE } = await import('../js/calibrate/intro.js');
const { createQrSvg, qrPath } = await import('../js/calibrate/qr.js');
const { ApiError } = await import('../js/http.js');

const NOTES = [{ name: 'Bb3', hz: 233.08 }, { name: 'F4', hz: 349.23 }, { name: 'Bb4', hz: 466.16 }];
const qrLib = (() => {
  const sandbox = { module: { exports: {} } };
  vm.runInNewContext(readFileSync(new URL('../vendor/qrcode.js', import.meta.url), 'utf8'), sandbox);
  return sandbox.qrcode;
})();

function startScreen(search = '?mock=1') {
  window.location.search = search;
  window.qrcode = qrLib; // index.html loads vendor/qrcode.js as a classic script
  window.location.hash = '#/calibrate';
  state.session_id = 'sess_mock1';
  state.instrument = 'trumpet';
  state.calibration = null;
  mockRequestLog.length = 0;
  const root = new FakeNode('main');
  return render(root).then(() => root);
}

async function recordAllNotes(root) {
  for (const note of NOTES) await root.button(new RegExp(`^Record ${note.name} \\(3 s\\)$`)).click();
}

test('recordClip: click_at_s is the scheduled click time minus the recording start, on the audio clock', async () => {
  const stream = { getVideoTracks: () => [], getTracks: () => [] };
  const clip = await recordClip({ stream, durationS: 0.01, clickAfterS: 0.5 });
  assert.ok(Math.abs(clip.click_at_s - 0.5) < 1e-9);
  assert.equal(env.clickTimes.at(-1), env.audioContext.currentTime + 0.5);
  assert.equal((await recordClip({ stream, durationS: 0.01 })).click_at_s, null);
});

test('clip store: the upload has ref_0..2, click and any instrument clips, with click_at_s', () => {
  const store = createClipStore();
  const clip = (name, clickAtS = null) => ({ file: name, click_at_s: clickAtS });
  assert.throws(() => store.toUpload(), /three notes and the delay test/);
  [0, 1, 2].forEach((i) => store.setRef(i, clip(`ref${i}`)));
  assert.equal(store.ready(), false);
  store.setClick(clip('click', 0.5));
  store.setInstrument(1, clip('inst1'));
  assert.deepEqual(store.toUpload(), { files: { click: 'click', ref_0: 'ref0', ref_1: 'ref1', ref_2: 'ref2', inst_1: 'inst1' }, clickAtS: 0.5 });
  store.clearRef(2);
  assert.equal(store.ready(), false);
});

test('failure list: each failing note shows its problem and a Retry that names the note', () => {
  const err = new ApiError('calibration_failed', 'F4 was not heard', 422, {
    notes: [{ asked: 'F4', problem: 'not_heard', cents: null }, { asked: 'Bb4', problem: 'off_pitch', cents: -42 }, { asked: 'C9', problem: 'too_noisy' }],
  });
  const failures = failuresFromError(err, NOTES);
  assert.deepEqual(failures, [{ index: 1, asked: 'F4', text: 'not heard' }, { index: 2, asked: 'Bb4', text: 'off pitch' }]);
  assert.equal(problemText('too_noisy'), 'too noisy');
  assert.deepEqual(failuresFromError(new ApiError('bad_request', 'x', 422), NOTES), []);
  const box = new FakeNode('div');
  const retried = [];
  renderFailureList(box, failures, (index) => retried.push(index));
  assert.ok(box.hasText('F4: not heard') && box.hasText('Bb4: off pitch'));
  assert.equal(box.find((n) => n.tagName === 'button' && n.textContent === 'Retry').length, 2);
  box.find((n) => n.tagName === 'button')[1].listeners.click[0]();
  assert.deepEqual(retried, [2]);
});

test('address: GET /lan-address wins; otherwise this page address, with a note for localhost', async () => {
  const phone = await findBaseAddress({ fetchLan: async () => ({ url: 'http://192.168.1.20:8000/' }), location: {} });
  assert.deepEqual(phone, { base: 'http://192.168.1.20:8000', note: null });
  const failing = async () => { throw new ApiError('http_404', 'not found', 404); };
  const local = await findBaseAddress({ fetchLan: failing, location: { protocol: 'http:', host: 'localhost:8000' } });
  assert.deepEqual(local, { base: 'http://localhost:8000', note: LOCALHOST_NOTE });
  const lan = await findBaseAddress({ fetchLan: async () => ({}), location: { protocol: 'http:', host: '10.0.0.5:8000' } });
  assert.deepEqual(lan, { base: 'http://10.0.0.5:8000', note: null });
  assert.equal(toneUrl('http://10.0.0.5:8000', 'trumpet'), 'http://10.0.0.5:8000/tone.html?instrument=trumpet');
});

test('QR: the vendored library draws a square code for the tone address', () => {
  const svg = createQrSvg('http://192.168.1.20:8000/tone.html?instrument=trumpet', qrLib);
  const [, , size] = svg.attrs.viewBox.split(' ').map(Number);
  assert.ok(size >= 29 + 8, `size ${size}`); // a URL this long needs at least version 3 (29 modules) plus the quiet zone
  assert.match(svg.children[1].attrs.d, /^M\d+ \d+h1v1h-1z/);
  assert.equal(qrPath((r, c) => r === 0 && c === 1, 2), 'M5 4h1v1h-1z');
  assert.throws(() => createQrSvg('x', null), /did not load/);
});

test('intro always shows the fallback line and the exact notes, even when the QR cannot be drawn', () => {
  const block = renderIntro({ notes: NOTES, url: 'http://localhost:8000/tone.html?instrument=trumpet', addressNote: LOCALHOST_NOTE });
  assert.equal(FALLBACK_LINE, 'Or use any tuner app or keyboard that plays these notes.');
  ['http://localhost:8000/tone.html?instrument=trumpet', FALLBACK_LINE, 'Bb3 - 233.08 Hz', 'F4 - 349.23 Hz', 'Bb4 - 466.16 Hz', 'could not be drawn', LOCALHOST_NOTE]
    .forEach((text) => assert.ok(block.hasText(text), text));
});

test('3 notes then the delay test: POST returns a profile and the screen offers the take screen', async () => {
  const root = await startScreen();
  assert.ok(root.hasText('Or use any tuner app or keyboard that plays these notes.'));
  assert.ok(root.find((n) => n.tagName === 'svg').length, 'the QR code is drawn');
  assert.ok(root.hasText('http://192.168.1.20:8000/tone.html?instrument=trumpet'));
  assert.equal(root.button('Send calibration').disabled, true);
  assert.equal(root.button(/^Record the delay test/).disabled, true);
  await recordAllNotes(root);
  assert.equal(root.button('Send calibration').disabled, true);
  await root.button(/^Record the delay test/).click();
  assert.equal(root.button('Send calibration').disabled, false);
  await root.button('Send calibration').click();
  assert.equal(mockRequestLog.at(-1).path, '/sessions/sess_mock1/calibration');
  assert.equal(state.calibration.source, 'measured');
  assert.ok(root.hasText('Calibrated: pitch offset -6 cents, delay 84 ms.'));
  await root.button('Continue to the take screen').click();
  assert.equal(window.location.hash, '#/take');
  env.leave();
});

test('a 422 calibration_failed lists "not heard" with Retry; retrying the notes lets the second send succeed', async () => {
  const root = await startScreen('?mock=1&calibration=failed');
  await recordAllNotes(root);
  await root.button(/^Record the delay test/).click();
  await root.button('Send calibration').click();
  assert.equal(env.banner.hidden, false);
  assert.match(env.banner.textContent, /F4 wasn't heard/);
  assert.ok(root.hasText('F4: not heard'));
  assert.ok(root.hasText('Bb4: off pitch'));
  assert.equal(root.button('Retry F4'), undefined); // buttons carry aria-label, text is "Retry"
  assert.equal(root.find((n) => n.tagName === 'button' && n.textContent === 'Retry').length, 2);
  assert.equal(root.button('Send calibration').disabled, true, 'the failed notes must be played again first');
  assert.equal(state.calibration, null);
  const retryF4 = root.find((n) => n.tagName === 'button' && n.attrs['aria-label'] === 'Retry F4')[0];
  await retryF4.click();
  assert.ok(!root.hasText('F4: not heard'));
  assert.ok(root.hasText('Bb4: off pitch'));
  await root.button(/^Record Bb4 \(3 s\)$/).click();
  assert.ok(!root.hasText('Bb4: off pitch'));
  await root.button('Send calibration').click();
  assert.equal(state.calibration.source, 'measured');
  env.leave();
});

test('Skip calls the skip route, keeps the default profile and moves on to the take screen', async () => {
  const root = await startScreen();
  await root.button('Skip calibration').click();
  assert.equal(mockRequestLog.at(-1).path, '/sessions/sess_mock1/calibration/skip');
  assert.equal(state.calibration.source, 'default');
  assert.equal(window.location.hash, '#/take');
  env.leave();
});

test('a blocked mic shows the device message and the help line, with Try again', async () => {
  const blocked = installFakeBrowser({ micError: 'NotAllowedError' });
  const root = await startScreen();
  await root.button(/^Record Bb3/).click();
  assert.ok(root.hasText('Chrome is blocking the mic'));
  assert.ok(root.hasText('Allow it in Chrome: click the camera icon in the address bar'));
  assert.ok(root.button('Try again'));
  assert.equal(root.button(/^Record Bb3/).disabled, false, 'recorded clips and buttons stay usable');
  blocked.leave();
});

test('leaving the route releases the microphone', async () => {
  const fresh = installFakeBrowser();
  const root = await startScreen();
  await root.button(/^Record Bb3/).click();
  assert.equal(fresh.streams.length, 1);
  assert.equal(fresh.streams[0].tracks[0].stopped, false);
  fresh.leave();
  assert.equal(fresh.streams[0].tracks[0].stopped, true);
  assert.equal(root.button('Skip calibration').disabled, true);
});

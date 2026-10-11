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
const { clipProblemFromError, failuresFromError, renderFailureList, problemText } = await import('../js/calibrate/problems.js');
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

// The mock fails the first POST per session id for ?calibration=failed, so each failing test passes its own session id.
function startScreen(search = '?mock=1', sessionId = 'sess_mock1') {
  window.location.search = search;
  window.qrcode = qrLib; // index.html loads vendor/qrcode.js as a classic script
  window.location.hash = '#/calibrate';
  state.session_id = sessionId;
  state.instrument = 'trumpet';
  state.calibration = null;
  mockRequestLog.length = 0;
  const root = new FakeNode('main');
  return render(root).then(() => root);
}

// The files each POST .../calibration carried, in order (the mock log keeps no form bodies). Every upload starts with its "click" part.
const sentUploads = [];
const realAppend = FormData.prototype.append;
FormData.prototype.append = function append(name, value, ...rest) {
  if (value instanceof Blob) {
    if (name === 'click') sentUploads.push({});
    sentUploads.at(-1)[name] = value;
  }
  return realAppend.call(this, name, value, ...rest);
};
const sentFileSets = () => sentUploads;

// Makes the first POST .../calibration answer with `error` (the mock serves it for ?calibration=failed; the mock status is 422).
function failFirstSendWith(error) {
  const serveMock = globalThis.fetch;
  globalThis.fetch = async (url) => (url === 'mock/error_calibration_failed.json'
    ? { ok: true, status: 200, json: async () => ({ error }) } // the mock decides the failure from the file name
    : serveMock(url));
}

async function recordAllAndSend(root) {
  await recordAllNotes(root);
  await root.button(/^Record the delay test/).click();
  sentUploads.length = 0;
  await root.button('Send calibration').click();
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

test('leaving while the mic permission prompt is open releases the mic once it is granted', async () => {
  const pending = installFakeBrowser({ holdMic: true });
  const root = await startScreen();
  const recording = root.button(/^Record Bb3/).click(); // stays at the permission prompt
  pending.leave();
  pending.grantMic();
  await recording;
  assert.equal(pending.streams.length, 1);
  assert.equal(pending.streams[0].tracks[0].stopped, true);
  assert.equal(pending.clipsStarted, 0, 'no recording starts after leaving');
  assert.equal(pending.banner.hidden, true, 'nothing is reported on the next screen');
});

test('after a failed send, Try again re-sends the same clips without opening the mic', async () => {
  const fresh = installFakeBrowser();
  failFirstSendWith({ code: 'server_error', message: 'The app server had a problem. Please try again.' });
  const root = await startScreen('?mock=1&calibration=failed', 'sess_retry1');
  await recordAllAndSend(root);
  assert.match(fresh.banner.textContent, /had a problem/);
  assert.ok(root.hasText('Your recordings are kept'));
  assert.equal(root.button('Send calibration').disabled, false, 'every clip is still in memory');
  const streamsBefore = fresh.streams.length;
  const recordingsBefore = fresh.clipsStarted;
  await root.button('Try again').click();
  assert.equal(state.calibration.source, 'measured');
  assert.equal(root.button('Try again'), undefined, 'the retry button goes away once the send worked');
  assert.equal(fresh.streams.length, streamsBefore, 'the mic is not opened again');
  assert.equal(fresh.clipsStarted, recordingsBefore, 'nothing is recorded again');
  const [first, second] = sentFileSets();
  assert.deepEqual(Object.keys(second).sort(), ['click', 'ref_0', 'ref_1', 'ref_2']);
  Object.keys(first).forEach((field) => assert.equal(second[field], first[field], `${field} is the very same clip`));
  fresh.leave();
});

test('Try again is disabled while the retry is in flight', async () => {
  const fresh = installFakeBrowser();
  failFirstSendWith({ code: 'server_error', message: 'The app server had a problem. Please try again.' });
  const root = await startScreen('?mock=1&calibration=failed', 'sess_retry2');
  await recordAllAndSend(root);
  const tryAgain = root.button('Try again');
  assert.equal(tryAgain.disabled, false);
  const retrying = tryAgain.click();
  assert.equal(tryAgain.disabled, true, 'a second press cannot start a second send');
  assert.equal(root.button('Send calibration').disabled, true);
  await tryAgain.click(); // ignored: disabled
  await retrying;
  assert.equal(sentFileSets().length, 2, 'one failed send and one retry, nothing more');
  fresh.leave();
});

test('the Retry buttons of the failed-notes list are disabled while a note is being recorded', async () => {
  const fresh = installFakeBrowser();
  const root = await startScreen('?mock=1&calibration=failed', 'sess_retry3');
  await recordAllAndSend(root);
  const retryButtons = root.find((n) => n.tagName === 'button' && n.textContent === 'Retry');
  assert.equal(retryButtons.length, 2);
  assert.ok(retryButtons.every((retry) => !retry.disabled));
  const recording = retryButtons[0].click();
  assert.ok(retryButtons.every((retry) => retry.disabled), 'no second recording while one is running');
  await recording;
  fresh.leave();
});

test('a 422 audio_unreadable asks for that note to be recorded again, not for the same clip to be re-sent', async () => {
  const fresh = installFakeBrowser();
  failFirstSendWith({ code: 'audio_unreadable', message: "We couldn't read the recording for ref_1. Record it again." });
  const root = await startScreen('?mock=1&calibration=failed', 'sess_retry4');
  await recordAllAndSend(root);
  assert.match(fresh.banner.textContent, /couldn't use the recording of F4 on your other device\. Please record it again/);
  assert.ok(root.hasText('F4: recording could not be used'));
  assert.equal(root.button('Try again'), undefined, 'sending the same bad clip again cannot work');
  assert.equal(root.button('Send calibration').disabled, true, 'F4 must be recorded again first');
  assert.ok(root.hasText('Needs another try'));
  await root.button(/^Record F4 \(3 s\)$/).click();
  assert.equal(root.button('Send calibration').disabled, false);
  await root.button('Send calibration').click();
  assert.equal(state.calibration.source, 'measured');
  const [, second] = sentFileSets();
  assert.equal(Object.keys(second).length, 4);
  fresh.leave();
});

test('a 422 on the delay test clip asks for the delay test again', async () => {
  const fresh = installFakeBrowser();
  failFirstSendWith({ code: 'audio_unreadable', message: "We couldn't read the recording for click. Record it again." });
  const root = await startScreen('?mock=1&calibration=failed', 'sess_retry5');
  await recordAllAndSend(root);
  assert.match(fresh.banner.textContent, /recording of the delay test\. Please record it again/);
  assert.ok(root.hasText('Needs another try'));
  assert.equal(root.button('Send calibration').disabled, true);
  await root.button(/^Record the delay test/).click();
  assert.equal(root.hasText('Needs another try'), false);
  await root.button('Send calibration').click();
  assert.equal(state.calibration.source, 'measured');
  fresh.leave();
});

test('clipProblemFromError: names the clip for 422/415 answers that mention one, and nothing else', () => {
  const unreadable = new ApiError('audio_unreadable', "We couldn't read the recording for inst_2. Record it again.", 422);
  assert.deepEqual(clipProblemFromError(unreadable, NOTES), {
    field: 'inst_2', kind: 'inst', index: 2, label: 'Bb4 on your instrument',
    message: "We couldn't use the recording of Bb4 on your instrument. Please record it again.",
  });
  assert.equal(clipProblemFromError(new ApiError('bad_request', 'click_at_s must be a number of seconds.', 422), NOTES), null);
  assert.equal(clipProblemFromError(new ApiError('server_error', 'ref_1 broke', 500), NOTES), null);
  assert.equal(clipProblemFromError(new ApiError('calibration_failed', 'ref_1 not heard', 422), NOTES), null);
  assert.equal(clipProblemFromError(null, NOTES), null);
});

test('a clip recorded after a mic-error Try again is stored, and the screen goes on from there', async () => {
  const fresh = installFakeBrowser();
  const { mediaDevices } = navigator;
  const openMic = mediaDevices.getUserMedia;
  let micBlocked = true;
  mediaDevices.getUserMedia = async () => {
    if (micBlocked) throw Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    return openMic();
  };
  const root = await startScreen('?mock=1', 'sess_micretry');
  await root.button(/^Record Bb3/).click();
  assert.ok(root.hasText('Chrome is blocking the mic'));
  assert.equal(root.button(/^Record the delay test/).disabled, true);
  micBlocked = false; // the learner allows the mic in Chrome, then presses Try again
  await root.button('Try again').click();
  assert.ok(root.hasText('Recorded'), 'the clip recorded by Try again is stored');
  await root.button(/^Record F4 \(3 s\)$/).click();
  await root.button(/^Record Bb4 \(3 s\)$/).click();
  assert.equal(root.button(/^Record the delay test/).disabled, false, 'with Bb3 stored, the three notes are complete');
  await root.button(/^Record the delay test/).click();
  assert.equal(root.button('Send calibration').disabled, false);
  await root.button('Send calibration').click();
  assert.deepEqual(Object.keys(sentFileSets().at(-1)).sort(), ['click', 'ref_0', 'ref_1', 'ref_2']);
  fresh.leave();
});

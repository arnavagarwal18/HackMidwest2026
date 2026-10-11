// Node tests for the demo upload (#/demo): the sequence in js/demo/flow.js, the screen in js/screens/demo.js, the pickers' checks.
// Run: node --test frontend/tests/demo_flow.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { fetchMockFile } from './fake_env.mjs';
import { installFakeDom } from './fake_dom.mjs';

const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms, ...args) => realSetTimeout(fn, Math.min(ms, 2), ...args); // the mock's delays and the scan polls take 2 ms
const { body: pageBody, window } = installFakeDom();
window.location.search = '?mock=1';
const storage = new Map();
window.localStorage = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) };
globalThis.fetch = fetchMockFile;

const { runDemo } = await import('../js/demo/flow.js');
const { describeProgress } = await import('../js/demo/progress.js');
const { picksProblem } = await import('../js/demo/picks.js');
const { photoFailureText } = await import('../js/demo/view.js');
const { mockRequestLog } = await import('../js/mock.js');
const { matchRoute } = await import('../js/router.js');
const { resumeSession } = await import('../js/resume.js');
const { render } = await import('../js/screens/demo.js');
const { resetState, state } = await import('../js/state.js');

const PHOTO = new File(['jpeg'], 'sheet.jpg', { type: 'image/jpeg' });
const VIDEO = new File(['mp4'], 'playing.mp4', { type: 'video/mp4' });
const ODE = { piece_id: 'ode_to_joy', title: 'Ode to Joy' };

function freshPage(search = '?mock=1') {
  window.location.search = search;
  window.location.hash = '#/demo';
  storage.clear();
  resetState();
  mockRequestLog.length = 0;
  pageBody.replaceChildren(pageBody.children[0]); // keeps the banner
}

const requests = () => mockRequestLog.map((r) => `${r.method} ${r.path.split('?')[0]}`);
const takeUploads = () => mockRequestLog.filter((r) => r.method === 'POST' && r.path.endsWith('/takes'));

async function until(check, what) {
  for (let i = 0; i < 400; i += 1) {
    const found = check();
    if (found) return found;
    await new Promise((resolve) => realSetTimeout(resolve, 5));
  }
  throw new Error(`Timed out waiting for ${what}`);
}

// Collects console.error output while `fn` runs, so a test can assert a failure was logged (and the run stays quiet).
async function withLoggedErrors(fn) {
  const original = console.error;
  const logged = [];
  console.error = (...args) => logged.push(args.map(String).join(' '));
  try {
    await fn();
  } finally {
    console.error = original;
  }
  return logged;
}

// A stand-in for demo/view.js whose answers a test scripts. Records what the dev would have seen.
function stubView({ scans = [{ ok: true }], fallbacks = [], asks = ['retry'] } = {}) {
  const seen = { statuses: [], asked: [], fallbackMessages: [], progress: [] };
  return {
    seen,
    setStatus: (text) => seen.statuses.push(text),
    progress: { reset: () => seen.progress.push('reset'), update: (p) => seen.progress.push(p), hide: () => seen.progress.push('hide') },
    reviewScan: async () => { // what the scan panel does when the dev confirms
      const scan = scans.shift();
      if (scan.ok) state.score = { status: 'confirmed', bars: 16, tempo_bpm: 96, time_signature: [4, 4] };
      return scan;
    },
    chooseFallback: async (message) => { seen.fallbackMessages.push(message); return fallbacks.shift(); },
    ask: async (message) => { seen.asked.push(message); return asks.shift(); },
  };
}

test('success: new session, photo, confirmed scan, then the video as an uploaded take; lands on results', async () => {
  freshPage();
  const view = stubView();
  const hash = await runDemo({ photo: PHOTO, video: VIDEO, view, isCurrent: () => true });
  assert.deepEqual(requests(), ['POST /sessions', 'POST /sessions/sess_mock1/score/photo', 'POST /sessions/sess_mock1/takes']);
  assert.equal(mockRequestLog[1].form.file, PHOTO, 'the photo goes up as the File itself');
  const take = mockRequestLog[2].form;
  assert.equal(take.file, VIDEO, 'the video goes up as the File itself, not a copy');
  assert.deepEqual({ ...take, file: undefined }, { file: undefined, kind: 'video', source: 'uploaded', bar_from: '1', bar_to: '16', tempo_bpm: '96', count_in_beats: '4' });
  assert.equal(hash, '#/results/take_1');
  assert.equal(state.current_take_id, 'take_1');
  assert.deepEqual(view.seen.progress, ['reset', { loaded: 1, total: 1 }, 'hide']);
});

test('an audio recording is sent with kind mic', async () => {
  freshPage();
  state.score.status = 'none';
  await runDemo({ photo: PHOTO, video: new File(['wav'], 'playing.wav', { type: 'audio/wav' }), view: stubView(), isCurrent: () => true });
  assert.equal(takeUploads()[0].form.kind, 'mic');
});

test('a photo that failed or was rescanned: the built-in score is chosen and confirmed, then the same video is sent', async () => {
  freshPage();
  const view = stubView({ scans: [{ ok: false, message: 'We could not read this photo.' }], fallbacks: [{ action: 'builtin', piece: ODE }] });
  const logged = await withLoggedErrors(async () => {
    const hash = await runDemo({ photo: PHOTO, video: VIDEO, view, isCurrent: () => true });
    assert.equal(hash, '#/results/take_1');
  });
  assert.deepEqual(requests(), [
    'POST /sessions', 'POST /sessions/sess_mock1/score/photo',
    'POST /sessions/sess_mock1/score/file', 'POST /sessions/sess_mock1/score/confirm', 'POST /sessions/sess_mock1/takes',
  ]);
  assert.deepEqual(mockRequestLog[2].body, { builtin: 'ode_to_joy' });
  assert.equal(takeUploads()[0].form.file, VIDEO);
  assert.deepEqual(view.seen.fallbackMessages, ['We could not read this photo.']);
  assert.ok(logged.some((line) => line.includes('We could not read this photo.')), 'the failure is logged');
});

test('reading the photo again after a failure sends the same photo to the same session', async () => {
  freshPage();
  const view = stubView({ scans: [{ ok: false, message: 'No notes.' }, { ok: true }], fallbacks: [{ action: 'retry' }] });
  await withLoggedErrors(() => runDemo({ photo: PHOTO, video: VIDEO, view, isCurrent: () => true }));
  assert.deepEqual(requests().filter((r) => r.includes('score/photo')).length, 2);
  assert.equal(requests().filter((r) => r === 'POST /sessions').length, 1, 'one session for both reads');
  assert.equal(mockRequestLog.filter((r) => r.path.endsWith('/score/photo')).every((r) => r.form.file === PHOTO), true);
});

test('a failed video upload is logged, shown with its reason and sent again on Retry, with the same file', async () => {
  freshPage('?mock=1&upload=failed');
  const view = stubView();
  const logged = await withLoggedErrors(async () => {
    assert.equal(await runDemo({ photo: PHOTO, video: VIDEO, view, isCurrent: () => true }), '#/results/take_1');
  });
  assert.equal(takeUploads().length, 2);
  assert.ok(takeUploads().every((r) => r.form.file === VIDEO));
  assert.match(view.seen.asked[0], /Uploading the video failed: The server could not save the video/);
  assert.ok(logged.some((line) => line.includes('Uploading the video failed')));
  assert.deepEqual(view.seen.progress.filter((p) => p === 'reset').length, 2);
});

test('leaving the screen after the score is confirmed sends no video', async () => {
  freshPage();
  assert.equal(await runDemo({ photo: PHOTO, video: VIDEO, view: stubView(), isCurrent: () => false }), null);
  assert.equal(takeUploads().length, 0);
});

test('picks: both files are needed, the photo must be an image and the video an accepted type', () => {
  assert.match(picksProblem({ photo: undefined, video: VIDEO }), /photo/);
  assert.match(picksProblem({ photo: new File(['x'], 'notes.pdf', { type: 'application/pdf' }), video: VIDEO }), /not a photo/);
  assert.match(picksProblem({ photo: PHOTO, video: undefined }), /video/);
  assert.match(picksProblem({ photo: PHOTO, video: new File(['x'], 'a.mp3', { type: 'audio/mpeg' }) }), /isn't supported/);
  assert.equal(picksProblem({ photo: PHOTO, video: VIDEO }), null);
});

test('progress text and the photo failure text', () => {
  assert.equal(describeProgress({ loaded: 5 * 1024 * 1024, total: 10 * 1024 * 1024 }), 'Uploading the video: 50% (5.0 of 10.0 MB)');
  assert.equal(photoFailureText({ score_error: 'scan_failed', score_error_message: 'Reader down.' }), 'Reader down.');
  assert.match(photoFailureText({ score_error: 'no_notes' }), /no_notes/);
  assert.match(photoFailureText({ score_error: null, score_status: 'scanned', bars: 0 }), /no bars/);
});

test('#/demo is a route, and a reload on it stays there whatever the stored session is', async () => {
  assert.deepEqual(matchRoute('#/demo'), { screen: 'demo', params: {} });
  freshPage();
  storage.set('practice_coach_session_id_mock', 'sess_unconfirmed');
  assert.deepEqual(await resumeSession('#/demo'), { hash: '#/demo', notice: null, error: null });
  assert.deepEqual(requests(), [], 'no session request is made');
});

function mountScreen() {
  const root = document.createElement('div');
  pageBody.append(root);
  render(root, {}, () => true);
  const [photoInput, videoInput] = root.all().filter((node) => node.tagName === 'INPUT');
  [photoInput, videoInput].forEach((input) => { input.files = []; }); // an empty FileList, as in a browser
  return { root, photoInput, videoInput, start: root.button('Start') };
}

test('screen: Start with a missing file shows the problem and sends nothing', async () => {
  freshPage();
  const { start } = mountScreen();
  start.click();
  assert.match(document.getElementById('banner').textContent, /Choose the sheet-music photo first/);
  assert.deepEqual(requests(), []);
});

test('screen: photo and video in, confirm the score (the only manual step), and the results open', async () => {
  freshPage();
  const { root, photoInput, videoInput, start } = mountScreen();
  photoInput.files = [PHOTO];
  videoInput.files = [VIDEO];
  start.click();
  const confirm = await until(() => root.button('Confirm'), 'the score check');
  assert.match(root.textContent, /16 bars found/);
  confirm.click();
  await until(() => window.location.hash === '#/results/take_1', 'the results screen');
  assert.equal(takeUploads()[0].form.file, VIDEO);
  assert.equal(state.score.status, 'confirmed');
});

test('screen: a photo that cannot be read offers the built-in scores and carries on with the same video', async () => {
  freshPage('?mock=1&scan=failed');
  const { root, photoInput, videoInput, start } = mountScreen();
  photoInput.files = [PHOTO];
  videoInput.files = [VIDEO];
  await withLoggedErrors(async () => {
    start.click();
    await until(() => root.textContent.includes('the music reader did not answer'), 'the failure message');
    assert.ok(root.button('Read the photo again'));
    const ode = await until(() => root.all().find((n) => n.tagName === 'LI' && n.textContent.includes('Ode to Joy')), 'the built-in list');
    ode.all().find((n) => n.tagName === 'BUTTON').click();
    await until(() => window.location.hash === '#/results/take_1', 'the results screen');
  });
  assert.equal(takeUploads()[0].form.file, VIDEO);
  assert.deepEqual(mockRequestLog.find((r) => r.path.endsWith('/score/file')).body, { builtin: 'ode_to_joy' });
});

test('screen: a failed upload shows a Retry button and the retry reaches the results', async () => {
  freshPage('?mock=1&upload=failed');
  const { root, photoInput, videoInput, start } = mountScreen();
  photoInput.files = [PHOTO];
  videoInput.files = [VIDEO];
  await withLoggedErrors(async () => {
    start.click();
    (await until(() => root.button('Confirm'), 'the score check')).click();
    const retry = await until(() => root.button('Retry'), 'the Retry button');
    assert.match(root.textContent, /could not save the video/);
    retry.click();
    await until(() => window.location.hash === '#/results/take_1', 'the results screen');
  });
  assert.equal(takeUploads().length, 2);
});

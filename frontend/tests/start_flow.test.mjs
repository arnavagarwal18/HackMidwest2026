// Node tests for the short path to Play: the automatic start (js/screens/start.js) and its shared steps (js/score/session.js).
import assert from 'node:assert/strict';
import test from 'node:test';
import { FakeNode, installFakeBrowser } from './fake_env.mjs';

installFakeBrowser();
const { pickStartPiece, chooseAndConfirmBuiltin, startOnDefaultPiece } = await import('../js/score/session.js');
const { render } = await import('../js/screens/start.js');
const { loadLastPieceId, loadStoredSessionId, resetState, state } = await import('../js/state.js');
const { mockRequestLog } = await import('../js/mock.js');

const PIECES = [{ piece_id: 'twinkle' }, { piece_id: 'ode_to_joy' }];
const realFetch = globalThis.fetch;

// A fresh page: empty localStorage (a Map), clean state and request log.
function loadPage() {
  const store = new Map();
  window.localStorage = { getItem: (key) => store.get(key) ?? null, setItem: (key, value) => store.set(key, value), removeItem: (key) => store.delete(key) };
  window.location.hash = '#/start';
  resetState();
  mockRequestLog.length = 0;
  globalThis.fetch = realFetch;
  return store;
}

const paths = () => mockRequestLog.map((r) => `${r.method} ${r.path.split('?')[0]}`);

test('pickStartPiece: the last-used piece if it still exists, else the first, else a clear error', () => {
  assert.equal(pickStartPiece(PIECES, 'ode_to_joy').piece_id, 'ode_to_joy');
  assert.equal(pickStartPiece(PIECES, 'gone').piece_id, 'twinkle');
  assert.equal(pickStartPiece(PIECES, null).piece_id, 'twinkle');
  assert.throws(() => pickStartPiece([], null), /no built-in pieces/);
});

test('chooseAndConfirmBuiltin chooses, confirms, marks the score confirmed and remembers the piece', async () => {
  loadPage();
  state.session_id = 'sess_mock1';
  await chooseAndConfirmBuiltin('sess_mock1', 'ode_to_joy');
  assert.deepEqual(paths(), ['POST /sessions/sess_mock1/score/file', 'POST /sessions/sess_mock1/score/confirm']);
  assert.deepEqual(mockRequestLog[0].body, { builtin: 'ode_to_joy' });
  assert.equal(state.score.status, 'confirmed');
  assert.equal(state.score.bars, 16);
  assert.equal(loadLastPieceId(), 'ode_to_joy');
});

test('startOnDefaultPiece with nothing remembered uses the first built-in piece', async () => {
  loadPage();
  await startOnDefaultPiece();
  assert.deepEqual(paths(), ['POST /sessions', 'GET /builtins', 'POST /sessions/sess_mock1/score/file', 'POST /sessions/sess_mock1/score/confirm']);
  assert.equal(mockRequestLog[2].body.builtin, 'twinkle');
  assert.equal(state.score.status, 'confirmed');
});

test('startOnDefaultPiece reuses the remembered piece', async () => {
  const store = loadPage();
  store.set('practice_coach_last_piece_mock', 'ode_to_joy');
  await startOnDefaultPiece();
  assert.equal(mockRequestLog[2].body.builtin, 'ode_to_joy');
});

test('the start screen shows one status line, then lands on #/take', async () => {
  loadPage();
  const root = new FakeNode('main');
  const done = render(root, {}, () => true);
  assert.ok(root.hasText('Getting your piece ready'));
  await done;
  assert.equal(window.location.hash, '#/take');
  assert.ok(loadStoredSessionId());
});

test('a failure shows the message, a primary Try again and a Choose a piece link; Try again works', async () => {
  loadPage();
  globalThis.fetch = async (url) => (String(url).includes('get_builtins') ? { ok: false, status: 404 } : realFetch(url));
  const root = new FakeNode('main');
  const origError = console.error;
  console.error = () => {};
  try {
    await render(root, {}, () => true);
  } finally {
    console.error = origError;
  }
  assert.equal(window.location.hash, '#/start');
  assert.ok(root.hasText('No mock response'));
  const retry = root.button('Try again');
  assert.ok(retry.className.includes('primary'));
  assert.equal(root.find((n) => n.tagName === 'a' && n.textContent === 'Choose a piece')[0].getAttribute('href'), '#/score');
  globalThis.fetch = realFetch;
  await retry.click();
  assert.equal(window.location.hash, '#/take');
});

test('leaving the start screen while it works does not move the learner on', async () => {
  loadPage();
  window.location.hash = '#/progress';
  await render(new FakeNode('main'), {}, () => false);
  assert.equal(window.location.hash, '#/progress');
});

test('the Change piece screen lists Built-in, File, Photo with Built-in selected; a built-in pick goes straight to #/take', async () => {
  loadPage();
  state.session_id = 'sess_mock1';
  FakeNode.prototype.getContext = () => ({}); // the photo tab builds a crop canvas
  Object.defineProperties(FakeNode.prototype, { // per-node style and dataset, as in a browser
    style: { configurable: true, get() { return (this.styleValues ??= {}); } },
    dataset: { configurable: true, get() { return (this.dataValues ??= {}); } },
  });
  const { render: renderScore } = await import('../js/screens/score.js');
  const root = new FakeNode('main');
  await renderScore(root);
  await new Promise((resolve) => setTimeout(resolve, 20)); // the piece list loads after the render
  assert.equal(root.find((n) => n.tagName === 'h1')[0].textContent, 'Change piece');
  const tabs = root.find((n) => n.tagName === 'button' && n.className === 'tab');
  assert.deepEqual(tabs.map((t) => [t.textContent, t.getAttribute('aria-selected')]), [['Built-in', 'true'], ['File', 'false'], ['Photo', 'false']]);
  await root.button('Play').click();
  assert.equal(window.location.hash, '#/take');
  assert.equal(root.button('Confirm'), undefined, 'no review step for a built-in piece');
  assert.equal(state.score.status, 'confirmed');
});

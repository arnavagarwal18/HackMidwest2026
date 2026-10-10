// Node tests for the page-reload decision (js/resume.js), in mock mode. Run: node --test frontend/tests/
import assert from 'node:assert/strict';
import test from 'node:test';
import { installFakeBrowser } from './fake_env.mjs';

installFakeBrowser();
const { resumeSession } = await import('../js/resume.js');
const { resetState, state } = await import('../js/state.js');

const MOCK_KEY = 'practice_coach_session_id_mock';

// Starts a "fresh page load": the stored session id (or none) and clean state.
function loadPage(storedSessionId = null) {
  const store = new Map(storedSessionId ? [[MOCK_KEY, storedSessionId]] : []);
  window.localStorage = { getItem: (key) => store.get(key) ?? null, setItem: (key, value) => store.set(key, value), removeItem: (key) => store.delete(key) };
  resetState();
  return store;
}

test('a deep link to #/calibrate with no stored session opens the mock session instead of #/start', async () => {
  const store = loadPage();
  const { hash, error } = await resumeSession('#/calibrate');
  assert.equal(hash, '#/calibrate');
  assert.equal(error, null);
  assert.equal(state.session_id, 'sess_mock1');
  assert.equal(state.instrument, 'trumpet');
  assert.equal(store.get(MOCK_KEY), 'sess_mock1');
});

test('a confirmed stored session stays on #/calibrate on reload', async () => {
  loadPage('sess_mock1');
  assert.equal((await resumeSession('#/calibrate')).hash, '#/calibrate');
});

test('a confirmed session still goes to #/take from #/start, #/score or no hash', async () => {
  for (const hash of ['#/start', '#/score', '', '#', '#/nowhere']) {
    loadPage('sess_mock1');
    assert.equal((await resumeSession(hash)).hash, '#/take', `from "${hash}"`);
  }
});

test('with no stored session, #/start, #/score and unknown hashes go to #/start and nothing is stored', async () => {
  for (const hash of ['#/start', '#/score', '', '#/nowhere']) {
    const store = loadPage();
    assert.equal((await resumeSession(hash)).hash, '#/start', `from "${hash}"`);
    assert.equal(store.size, 0);
  }
});

test('a session whose score is not confirmed goes to #/score, even from a deep link', async () => {
  loadPage('sess_unconfirmed');
  assert.equal((await resumeSession('#/calibrate')).hash, '#/score');
});

test('a session the back end no longer knows goes to #/start with a notice', async () => {
  const store = loadPage('sess_gone');
  const { hash, notice } = await resumeSession('#/calibrate');
  assert.equal(hash, '#/start');
  assert.match(notice, /not found/);
  assert.equal(store.size, 0);
});

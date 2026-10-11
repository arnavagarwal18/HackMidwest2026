// After a hand-made transposition change the feedback is asked for once; a fresh take is never asked.
// Run: node --test frontend/tests/results_rerun_feedback.test.mjs   (mock mode on the real api.js; no browser)
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { installFakeDom } from './fake_dom.mjs';

const dom = installFakeDom();
dom.window.location.search = '?mock=1&poll_ms=1&give_up_after_s=0.3';
globalThis.fetch = async (url) => {
  const body = await readFile(new URL(`../${url}`, import.meta.url), 'utf8');
  return { ok: true, status: 200, json: async () => JSON.parse(body) };
};
const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms, ...args) => realSetTimeout(fn, Math.min(ms, 2), ...args); // the mock's 150 ms delay, the poll wait and the 1 s retry gap

const { setTransposition } = await import('../js/api.js');
const { fetchResultsOnce } = await import('../js/results/load.js');
const { pollUntilDone } = await import('../js/results/polling.js');
const { FEEDBACK_TRIES } = await import('../js/results/autokey_run.js');
const { refreshAfterKeyChange } = await import('../js/results/rerun.js');
const { mockRequestLog } = await import('../js/mock.js');

const SESSION = 'sess_mock1';
const TAKE = 'take_cant_tell';
const feedbackPosts = () => mockRequestLog.filter((r) => r.method === 'POST' && r.path.endsWith('/feedback')).length;
const refresh = (semitones, sessionId = SESSION) => refreshAfterKeyChange({ sessionId, take: TAKE, semitones, isActive: () => true });

test('after a manual key change the feedback is requested exactly once and the result is shown', async () => {
  mockRequestLog.length = 0;
  await setTransposition(SESSION, 3);
  const refreshed = await refresh(3);
  assert.equal(refreshed.outcome, 'done');
  assert.equal(feedbackPosts(), 1);
  assert.equal(refreshed.result.done, true);
  assert.equal(refreshed.result.analysis.transposition.semitones, 3);
  assert.ok(refreshed.result.feedback, 'the new feedback is in the result');
});

test('a 409 from the feedback request (back end busy) is retried and succeeds', async () => {
  mockRequestLog.length = 0;
  await setTransposition('sess_feedback_busy', 2); // the mock answers 409 to the first two feedback requests of this session
  const refreshed = await refresh(2, 'sess_feedback_busy');
  assert.equal(refreshed.outcome, 'done');
  assert.equal(feedbackPosts(), 3, 'two 409s, then the answer');
  assert.ok(feedbackPosts() <= FEEDBACK_TRIES);
});

test('a fresh take that becomes ready is never asked for feedback', async () => {
  mockRequestLog.length = 0;
  const polled = await pollUntilDone({ fetchOnce: () => fetchResultsOnce(SESSION, 'take_ok'), onTick: () => {}, isActive: () => true });
  assert.equal(polled.outcome, 'done');
  assert.ok(polled.result.feedback);
  assert.equal(feedbackPosts(), 0);
});

test('a re-check that never shows the new key stops at the limit instead of waiting for ever', async () => {
  mockRequestLog.length = 0;
  await setTransposition(SESSION, 5);
  const refreshed = await refresh(-7); // the take keeps showing +5
  assert.deepEqual(refreshed, { outcome: 'timeout' });
  assert.equal(feedbackPosts(), 0, 'no feedback is requested for a re-check that did not finish');
});

test('leaving the screen stops the wait without asking for feedback', async () => {
  mockRequestLog.length = 0;
  const refreshed = await refreshAfterKeyChange({ sessionId: SESSION, take: TAKE, semitones: 5, isActive: () => false });
  assert.deepEqual(refreshed, { outcome: 'stopped' });
  assert.equal(feedbackPosts(), 0);
});

test('leaving the screen during the feedback request gives no result to show', async () => {
  mockRequestLog.length = 0;
  await setTransposition(SESSION, 3);
  let active = true;
  const refreshing = refreshAfterKeyChange({ sessionId: SESSION, take: TAKE, semitones: 3, isActive: () => active });
  const leaveWhenFeedbackAsked = setInterval(() => { if (feedbackPosts() > 0) active = false; }, 0);
  const refreshed = await refreshing;
  clearInterval(leaveWhenFeedbackAsked);
  assert.equal(feedbackPosts(), 1);
  assert.deepEqual(refreshed, { outcome: 'stopped' });
});

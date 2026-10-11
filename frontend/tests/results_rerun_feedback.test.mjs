// After a hand-made transposition change the screen waits for the back end's new analysis and its rebuilt feedback;
// it never asks for feedback itself (POST .../feedback).
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
globalThis.setTimeout = (fn, ms, ...args) => realSetTimeout(fn, Math.min(ms, 2), ...args); // the mock's 150 ms delay and the poll waits

const { setTransposition } = await import('../js/api.js');
const { fetchResultsOnce } = await import('../js/results/load.js');
const { pollUntilDone } = await import('../js/results/polling.js');
const { refreshAfterKeyChange } = await import('../js/results/rerun.js');
const { mockRequestLog } = await import('../js/mock.js');

const SESSION = 'sess_mock1';
const TAKE = 'take_cant_tell';
const feedbackPosts = () => mockRequestLog.filter((r) => r.method === 'POST' && r.path.endsWith('/feedback')).length;
const refresh = (semitones, previousFeedbackId = 'fb_1', isActive = () => true) =>
  refreshAfterKeyChange({ sessionId: SESSION, take: TAKE, semitones, previousFeedbackId, isActive });

test('after a manual key change the rebuilt feedback is shown, and feedback is never requested by the screen', async () => {
  mockRequestLog.length = 0;
  await setTransposition(SESSION, 3);
  const refreshed = await refresh(3);
  assert.equal(refreshed.outcome, 'done');
  assert.equal(feedbackPosts(), 0);
  assert.equal(refreshed.result.done, true);
  assert.equal(refreshed.result.analysis.transposition.semitones, 3);
  assert.notEqual(refreshed.result.feedback.id, 'fb_1', 'the feedback is the rebuilt one, not the old one');
});

test('feedback that still has the old id is not shown: the wait ends at the limit', async () => {
  mockRequestLog.length = 0;
  await setTransposition(SESSION, 4);
  const { result: current } = await pollUntilDone({ fetchOnce: () => fetchResultsOnce(SESSION, TAKE), onTick: () => {}, isActive: () => true });
  const refreshed = await refresh(4, current.feedback.id); // the back end has not rebuilt anything newer than this
  assert.deepEqual(refreshed, { outcome: 'timeout' });
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
});

test('leaving the screen stops the wait', async () => {
  mockRequestLog.length = 0;
  const refreshed = await refresh(5, 'fb_1', () => false);
  assert.deepEqual(refreshed, { outcome: 'stopped' });
});

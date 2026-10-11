// The automatic key search for a can't-tell take: the candidates, the cap, the early stop, restoring, no retrigger.
// Run: node --test frontend/tests/results_autokey.test.mjs   (mock mode on the real api.js; no browser)
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { installFakeDom, settle } from './fake_dom.mjs';

const dom = installFakeDom();
dom.window.location.search = '?mock=1';
globalThis.fetch = async (url) => {
  const body = await readFile(new URL(`../${url}`, import.meta.url), 'utf8');
  return { ok: true, status: 200, json: async () => JSON.parse(body) };
};
const realSetTimeout = globalThis.setTimeout;
globalThis.setTimeout = (fn, ms, ...args) => realSetTimeout(fn, Math.min(ms, 2), ...args); // the mock's 150 ms delay and the poll wait

const { candidateSemitones, foundMessage, isMatch, MAX_KEY_TRIES, NONE_FOUND_MESSAGE, searchKeys, shouldAutoKey } = await import('../js/results/autokey.js');
const { claimAutoKey, runAutoKey } = await import('../js/results/autokey_run.js');
const { mockRequestLog } = await import('../js/mock.js');
const { AUTOKEY_RIGHT_SEMITONES, AUTOKEY_TAKE, NOKEY_TAKE } = await import('../js/mock_transposition.js');

const SESSION = 'sess_mock1';
const good = { cant_tell: false, alignment_quality: 0.8 };
const bad = { cant_tell: true, cant_tell_reason: 'low_match', alignment_quality: 0.2 };

test('the candidates go outward from the current key, lower first, and skip the current key', () => {
  assert.deepEqual(candidateSemitones(0), [-1, 1, -2, 2, -3, 3, -4, 4, -5, 5, -6, 6]);
  assert.deepEqual(candidateSemitones(-2), [-3, -1, -4, 0, -5, 1, -6, 2, -7, 3, -8, 4]);
});

test('the candidates stay within -12..12 and are capped at 12', () => {
  assert.equal(MAX_KEY_TRIES, 12);
  assert.deepEqual(candidateSemitones(12), [11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0]);
  assert.deepEqual(candidateSemitones(-11), [-12, -10, -9, -8, -7, -6, -5, -4, -3, -2, -1, 0]);
  [-12, -5, 0, 7, 12].forEach((current) => {
    const candidates = candidateSemitones(current);
    assert.ok(candidates.length <= 12 && !candidates.includes(current));
    assert.ok(candidates.every((semitones) => Math.abs(semitones) <= 12));
  });
});

test('only a low_match cant-tell starts the search, and a match needs quality 0.4 and a clear result', () => {
  assert.equal(shouldAutoKey(bad), true);
  assert.equal(shouldAutoKey({ ...bad, cant_tell_reason: 'few_pairs' }), false);
  assert.equal(shouldAutoKey({ ...bad, cant_tell_reason: 'too_short' }), false);
  assert.equal(shouldAutoKey(good), false);
  assert.equal(isMatch({ cant_tell: false, alignment_quality: 0.4 }), true);
  assert.equal(isMatch({ cant_tell: false, alignment_quality: 0.39 }), false);
  assert.equal(isMatch({ cant_tell: true, alignment_quality: 0.9 }), false);
});

test('the search stops at the first key that matches and reports its progress', async () => {
  const tried = [];
  const progress = [];
  const found = await searchKeys({
    original: 0,
    isActive: () => true,
    onProgress: (p) => progress.push(p),
    tryKey: async (semitones) => { tried.push(semitones); return semitones === -2 ? good : bad; },
  });
  assert.deepEqual(tried, [-1, 1, -2]);
  assert.deepEqual(found, { outcome: 'found', semitones: -2, analysis: good });
  assert.deepEqual(progress, [{ tried: 1, total: 12 }, { tried: 2, total: 12 }, { tried: 3, total: 12 }]);
});

test('with no match the search tries exactly 12 keys', async () => {
  const tried = [];
  const result = await searchKeys({ original: -2, isActive: () => true, onProgress() {}, tryKey: async (s) => { tried.push(s); return bad; } });
  assert.deepEqual(result, { outcome: 'none' });
  assert.equal(tried.length, 12);
});

test('the search stops when it is cancelled, and a failed try propagates', async () => {
  let active = true;
  const tried = [];
  const cancelled = await searchKeys({ original: 0, isActive: () => active, onProgress() {}, tryKey: async (s) => { tried.push(s); active = false; return bad; } });
  assert.deepEqual(cancelled, { outcome: 'cancelled' });
  assert.deepEqual(tried, [-1]);
  await assert.rejects(searchKeys({ original: 0, isActive: () => true, onProgress() {}, tryKey: async () => { throw new Error('boom'); } }), /boom/);
});

test('the message says how far and which way the key moved', () => {
  assert.equal(foundMessage(-2, -6), "Detected you're playing 4 semitones lower than expected; adjusted.");
  assert.equal(foundMessage(0, 1), "Detected you're playing 1 semitone higher than expected; adjusted.");
});

test('each take is claimed once per page load', () => {
  assert.equal(claimAutoKey(SESSION, 'take_once'), true);
  assert.equal(claimAutoKey(SESSION, 'take_once'), false);
  assert.equal(claimAutoKey(SESSION, 'take_other'), true);
  assert.equal(claimAutoKey('sess_other', 'take_once'), true);
});

function openView() {
  const view = dom.document.createElement('section');
  dom.body.append(view);
  mockRequestLog.length = 0;
  dom.banner.hidden = true;
  return view;
}
const transpositionPosts = () => mockRequestLog.filter((r) => r.method === 'POST' && r.path.endsWith('/transposition')).map((r) => r.body.semitones);
const feedbackPosts = () => mockRequestLog.filter((r) => r.method === 'POST' && r.path.endsWith('/feedback')).length;
const search = (view, take, original = 0, isActive = () => view.isConnected) => runAutoKey({ view, sessionId: SESSION, take, original, isActive });

test('a take that matches in another key keeps it, writes the feedback once and says so', async () => {
  const view = openView();
  const outcome = await search(view, AUTOKEY_TAKE, 0);
  assert.equal(outcome.outcome, 'found');
  assert.equal(outcome.note, "Detected you're playing 4 semitones lower than expected; adjusted.");
  assert.equal(outcome.result.analysis.transposition.semitones, AUTOKEY_RIGHT_SEMITONES);
  assert.equal(outcome.result.analysis.cant_tell, false);
  assert.equal(outcome.result.feedback.cant_tell, false);
  assert.deepEqual(transpositionPosts(), [-1, 1, -2, 2, -3, 3, -4], 'no restore after a find');
  assert.equal(feedbackPosts(), 1);
});

test('when no key matches, the original key is put back and the note says so', async () => {
  const view = openView();
  const outcome = await search(view, NOKEY_TAKE, 3);
  assert.deepEqual(outcome, { outcome: 'none', note: NONE_FOUND_MESSAGE });
  const posts = transpositionPosts();
  assert.equal(posts.length, 13);
  assert.equal(posts.at(-1), 3, 'the last request restores the original key');
  assert.equal(feedbackPosts(), 0, 'no AI feedback is written for the tries');
});

test('Cancel stops the search and puts the original key back', async () => {
  const view = openView();
  const running = search(view, NOKEY_TAKE, 0);
  await settle();
  assert.match(view.all().find((n) => n.className === 'stage').textContent, /^Checking other keys… \d+\/12$/);
  view.button('Cancel').click();
  const outcome = await running;
  assert.deepEqual(outcome, { outcome: 'cancelled' });
  assert.ok(transpositionPosts().length < 13);
  assert.equal(transpositionPosts().at(-1), 0);
});

test('leaving the screen stops the polling and still puts the original key back', async () => {
  const view = openView();
  const running = search(view, NOKEY_TAKE, 0);
  await settle();
  view.remove();
  await running;
  assert.equal(transpositionPosts().at(-1), 0);
  const requests = mockRequestLog.length;
  await settle();
  await settle();
  assert.equal(mockRequestLog.length, requests, 'nothing runs after the screen is gone');
});

test('a 409 wrong_state stops the search, shows the back end message and restores the key', async () => {
  const view = openView();
  const outcome = await runAutoKey({ view, sessionId: 'sess_unconfirmed', take: AUTOKEY_TAKE, original: 0, isActive: () => view.isConnected });
  assert.deepEqual(outcome, { outcome: 'error' });
  assert.equal(dom.banner.hidden, false);
  assert.match(dom.banner.textContent, /Confirm your sheet music/);
  assert.deepEqual(transpositionPosts(), [-1, 0], 'one failed try, then the restore (which also fails and is reported)');
});

test('a 409 from the feedback request is retried until the back end is ready', async () => {
  const view = openView();
  const outcome = await runAutoKey({ view, sessionId: 'sess_feedback_busy', take: AUTOKEY_TAKE, original: 0, isActive: () => view.isConnected });
  assert.equal(outcome.outcome, 'found');
  assert.equal(outcome.result.feedback.cant_tell, false);
  assert.equal(feedbackPosts(), 3, 'two 409s, then the feedback');
});

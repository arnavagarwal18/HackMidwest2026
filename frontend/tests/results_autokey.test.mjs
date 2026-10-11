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

const { candidateSemitones, createBestKey, foundMessage, isMatch, keyOrder, MAX_KEY_TRIES, medianOffsetKey, NONE_FOUND_MESSAGE, searchKeys, shouldAutoKey } = await import('../js/results/autokey.js');
const { barWindows, foundWindowMessage, MAX_TOTAL_RERUNS, NO_FILE_MESSAGE, searchBarWindows } = await import('../js/results/autokey_windows.js');
const { claimAutoKey, runAutoKey } = await import('../js/results/autokey_run.js');
const { mockRequestLog } = await import('../js/mock.js');
const { AUTOKEY_RIGHT_SEMITONES, AUTOKEY_TAKE, NOKEY_TAKE } = await import('../js/mock_transposition.js');

const SESSION = 'sess_mock1';
const good = { cant_tell: false, alignment_quality: 0.8 };
const bad = { cant_tell: true, cant_tell_reason: 'low_match', alignment_quality: 0.2 };

const range = (from, to) => Array.from({ length: to - from + 1 }, (_, i) => from + i);
const ascending = (list) => [...list].sort((a, b) => a - b);

test('the candidates go outward from the current key, lower first, and skip the current key', () => {
  assert.deepEqual(candidateSemitones(0).slice(0, 12), [-1, 1, -2, 2, -3, 3, -4, 4, -5, 5, -6, 6]);
  assert.deepEqual(candidateSemitones(-2).slice(0, 12), [-3, -1, -4, 0, -5, 1, -6, 2, -7, 3, -8, 4]);
  assert.deepEqual(candidateSemitones(12).slice(0, 4), [11, 10, 9, 8]);
});

test('the candidates cover the whole -12..12 range except the current key, within the cap of 24', () => {
  assert.equal(MAX_KEY_TRIES, 24);
  [-12, -5, 0, 7, 12].forEach((current) => {
    const candidates = candidateSemitones(current);
    assert.equal(candidates.length, 24);
    assert.deepEqual(ascending(candidates), range(-12, 12).filter((semitones) => semitones !== current));
  });
});

const paired = (offsets, semitones = -2) => ({
  transposition: { semitones },
  notes: offsets.map((offset, i) => ({ expected_midi: 60 + i, played_midi_float: offset === null ? null : 60 + i + offset })),
});

test('the median pitch offset of the heard notes points to a key', () => {
  assert.equal(medianOffsetKey(paired([7, 6.9, 7.1, 5, 9, 7.02])), 5, 'current -2 plus a median of 7');
  assert.equal(medianOffsetKey(paired([-4, -4, -3.9, 12, null, null])), -6);
  assert.equal(medianOffsetKey(paired([7, 7, 7])), null, 'too few heard notes');
  assert.equal(medianOffsetKey(paired([null, null, null, null, 7])), null, 'unheard notes do not count');
  assert.equal(medianOffsetKey(paired([0, 0.2, -0.3, 0.1])), null, 'no shift');
  assert.equal(medianOffsetKey(paired([12, 12, 12, 12], 5)), null, 'outside -12..12');
  assert.equal(medianOffsetKey({ notes: [] }), null);
  assert.equal(medianOffsetKey(null), null);
});

test('the key order is the preferred keys, the one the notes point to, then the nearest, each once', () => {
  const order = keyOrder({ around: -2, analysis: paired([7, 7, 7, 7]) });
  assert.deepEqual(order.slice(0, 4), [5, -3, -1, -4]);
  assert.deepEqual(ascending(order), range(-12, 12).filter((semitones) => semitones !== -2));
  assert.deepEqual(keyOrder({ around: 0, analysis: paired([7, 7, 7, 7], 0), prefer: [-4, null] }).slice(0, 3), [-4, 7, -1]);
  assert.deepEqual(keyOrder({ around: 0, skip: 3, prefer: [3, -4] }).slice(0, 3), [-4, 0, -1], 'the skipped key is left out and the original comes back in');
});

test('the best key is the one with the highest alignment quality', () => {
  const best = createBestKey();
  assert.equal(best.semitones, null);
  best.note(0, { alignment_quality: 0.1 });
  best.note(-4, { alignment_quality: 0.15 });
  best.note(3, { alignment_quality: 0.05 });
  best.note(2, { alignment_quality: null });
  assert.equal(best.semitones, -4);
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
    keys: candidateSemitones(0),
    isActive: () => true,
    onProgress: (p) => progress.push(p),
    tryKey: async (semitones) => { tried.push(semitones); return semitones === -2 ? good : bad; },
  });
  assert.deepEqual(tried, [-1, 1, -2]);
  assert.deepEqual(found, { outcome: 'found', semitones: -2, analysis: good });
  assert.deepEqual(progress, [{ semitones: -1, tried: 1, total: 24 }, { semitones: 1, tried: 2, total: 24 }, { semitones: -2, tried: 3, total: 24 }]);
});

test('with no match the search tries every key of the range once', async () => {
  const tried = [];
  const result = await searchKeys({ keys: candidateSemitones(-2), isActive: () => true, onProgress() {}, tryKey: async (s) => { tried.push(s); return bad; } });
  assert.deepEqual(result, { outcome: 'none' });
  assert.deepEqual(ascending(tried), range(-12, 12).filter((semitones) => semitones !== -2));
});

test('the search stops when it is cancelled, and a failed try propagates', async () => {
  let active = true;
  const tried = [];
  const cancelled = await searchKeys({ keys: candidateSemitones(0), isActive: () => active, onProgress() {}, tryKey: async (s) => { tried.push(s); active = false; return bad; } });
  assert.deepEqual(cancelled, { outcome: 'cancelled' });
  assert.deepEqual(tried, [-1]);
  await assert.rejects(searchKeys({ keys: candidateSemitones(0), isActive: () => true, onProgress() {}, tryKey: async () => { throw new Error('boom'); } }), /boom/);
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
const search = (view, take, original = 0, upload = null, isActive = () => view.isConnected) => runAutoKey({ view, sessionId: SESSION, take, original, analysis: bad, upload, isActive });

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
  assert.deepEqual(outcome, { outcome: 'none', note: NO_FILE_MESSAGE }, 'no recording to send again, and the user is told');
  const posts = transpositionPosts();
  assert.equal(posts.length, 25, 'all 24 other keys, then the restore');
  assert.deepEqual(ascending(posts.slice(0, 24)), range(-12, 12).filter((semitones) => semitones !== 3));
  assert.equal(posts.at(-1), 3, 'the last request restores the original key');
  assert.equal(feedbackPosts(), 0, 'no AI feedback is written for the tries');
});

test('Cancel stops the search and puts the original key back', async () => {
  const view = openView();
  const running = search(view, NOKEY_TAKE, 0);
  await settle();
  assert.match(view.all().find((n) => n.className.includes('key-stage')).textContent, /^Trying key [+-]?\d+ \(\d+ of 24\)$/);
  view.button('Cancel').click();
  const outcome = await running;
  assert.deepEqual(outcome, { outcome: 'cancelled' });
  assert.ok(transpositionPosts().length < 25);
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
  const outcome = await runAutoKey({ view, sessionId: 'sess_unconfirmed', take: AUTOKEY_TAKE, original: 0, analysis: bad, isActive: () => view.isConnected });
  assert.deepEqual(outcome, { outcome: 'error' });
  assert.equal(dom.banner.hidden, false);
  assert.match(dom.banner.textContent, /Confirm your sheet music/);
  assert.deepEqual(transpositionPosts(), [-1, 0], 'one failed try, then the restore (which also fails and is reported)');
});

test('a 409 from the feedback request is retried until the back end is ready', async () => {
  const view = openView();
  const outcome = await runAutoKey({ view, sessionId: 'sess_feedback_busy', take: AUTOKEY_TAKE, original: 0, analysis: bad, isActive: () => view.isConnected });
  assert.equal(outcome.outcome, 'found');
  assert.equal(outcome.result.feedback.cant_tell, false);
  assert.equal(feedbackPosts(), 3, 'two 409s, then the feedback');
});

test('a long range is split into its two halves and a short one is not', () => {
  assert.deepEqual(barWindows(1, 16), [{ from: 1, to: 8 }, { from: 9, to: 16 }]);
  assert.deepEqual(barWindows(1, 12), [{ from: 1, to: 6 }, { from: 7, to: 12 }]);
  assert.deepEqual(barWindows(3, 11), [{ from: 3, to: 6 }, { from: 7, to: 11 }]);
  assert.deepEqual(barWindows(1, 8), []);
  assert.deepEqual(barWindows(5, 5), []);
});

test('the window message names the bars and the key', () => {
  assert.equal(foundWindowMessage({ from: 1, to: 8 }, -4), 'Matched bars 1–8 at -4 semitones.');
  assert.equal(foundWindowMessage({ from: 9, to: 16 }, 5), 'Matched bars 9–16 at +5 semitones.');
  assert.equal(foundWindowMessage({ from: 1, to: 8 }, 1), 'Matched bars 1–8 at +1 semitone.');
});

// A fake back end for the window search: uploading bars gives take `take_<from>`; its analysis passes in `passes(bars, key)`.
function windowSearch({ passes, bestKey = createBestKey(), original = 0, rerunsLeft = 16, active = () => true }) {
  const log = { uploads: [], tries: [], progress: [] };
  const analysisAt = (take, semitones, bars) => ({ ...(passes(bars, semitones) ? good : bad), transposition: { semitones }, alignment_quality: passes(bars, semitones) ? 0.8 : 0.1 });
  const barsOf = (take) => log.uploads.find((u) => `take_${u.from}` === take);
  const running = searchBarWindows({
    windows: barWindows(1, 16),
    original,
    bestKey,
    rerunsLeft,
    isActive: active,
    onProgress: (p) => log.progress.push(p),
    uploadWindow: async (bars) => { log.uploads.push(bars); return { take: `take_${bars.from}`, analysis: analysisAt(`take_${bars.from}`, original, bars) }; },
    tryKey: async (take, semitones) => { log.tries.push([take, semitones]); return analysisAt(take, semitones, barsOf(take)); },
  });
  return { running, log };
}

test('bars 1-8 are tried first, in the best key so far, and the first window that matches is kept', async () => {
  const bestKey = createBestKey();
  bestKey.note(-4, { alignment_quality: 0.15 });
  const { running, log } = windowSearch({ bestKey, passes: (bars, key) => bars.from === 1 && key === -4 });
  const outcome = await running;
  assert.equal(outcome.outcome, 'found');
  assert.deepEqual([outcome.take, outcome.bars, outcome.semitones, outcome.rerun], ['take_1', { from: 1, to: 8 }, -4, true]);
  assert.deepEqual(log.uploads, [{ from: 1, to: 8 }], 'bars 9-16 are never uploaded');
  assert.deepEqual(log.tries, [['take_1', -4]], 'the best key goes first');
  assert.equal(log.progress[0].bars.from, 1);
  assert.deepEqual(log.progress.at(-1), { bars: { from: 1, to: 8 }, semitones: -4, tried: 1, total: 8 });
});

test('after the best key, a window tries the keys nearest to the best key', async () => {
  const bestKey = createBestKey();
  bestKey.note(-4, { alignment_quality: 0.15 });
  const { running, log } = windowSearch({ bestKey, passes: () => false, rerunsLeft: 6 });
  await running;
  assert.deepEqual(log.tries.filter(([take]) => take === 'take_1').map(([, key]) => key), [-4, -5, -3]);
});

test('a window that matches as uploaded needs no key change, and bars 9-16 are tried when 1-8 fail', async () => {
  const first = await windowSearch({ passes: (bars, key) => bars.from === 1 && key === 0 }).running;
  assert.deepEqual([first.take, first.rerun, first.semitones], ['take_1', false, 0]);
  const { running, log } = windowSearch({ passes: (bars, key) => bars.from === 9 && key === -3 });
  const second = await running;
  assert.deepEqual([second.take, second.bars, second.semitones], ['take_9', { from: 9, to: 16 }, -3]);
  assert.deepEqual(log.uploads, [{ from: 1, to: 8 }, { from: 9, to: 16 }]);
  assert.equal(log.tries.filter(([take]) => take === 'take_1').length, 8, 'each window gets half of the 16 key changes left');
});

test('the window search never changes the key more often than it was given', async () => {
  const { running, log } = windowSearch({ passes: () => false, rerunsLeft: 16 });
  assert.deepEqual(await running, { outcome: 'none' });
  assert.equal(log.tries.length, 16);
  assert.equal(MAX_TOTAL_RERUNS, 40);
  const none = windowSearch({ passes: () => false, rerunsLeft: 0 });
  assert.deepEqual(await none.running, { outcome: 'none' });
  assert.deepEqual(none.log.tries, [], 'no budget: the windows are uploaded and checked once, no key is tried');
  assert.equal(none.log.uploads.length, 2);
});

test('the window search stops when it is cancelled, even while a window is being sent', async () => {
  let active = true;
  const { running, log } = windowSearch({ passes: () => { active = false; return false; }, active: () => active });
  assert.deepEqual(await running, { outcome: 'cancelled' });
  assert.deepEqual(log.uploads, [{ from: 1, to: 8 }], 'bars 9-16 are not sent');
  assert.deepEqual(log.tries, []);
});

const upload = (barFrom = 1, barTo = 16) => ({ file: { name: 'take.mp4' }, fields: { kind: 'video', source: 'uploaded', bar_from: barFrom, bar_to: barTo, tempo_bpm: 96, count_in_beats: 0 } });

test('with the recording still here and no matching key, bars 1-8 are sent again and shown', async () => {
  const view = openView();
  const outcome = await search(view, NOKEY_TAKE, 0, upload());
  assert.equal(outcome.outcome, 'found');
  assert.match(outcome.note, /^Matched bars 1–8 at [+-]?\d+ semitones?\.$/);
  assert.equal(outcome.take, 'take_1', 'the new take, not the can\'t-tell one');
  const uploads = mockRequestLog.filter((r) => r.method === 'POST' && r.path.endsWith('/takes'));
  assert.equal(uploads.length, 1, 'the mock back end likes bars 1-8 as uploaded');
  assert.equal(transpositionPosts().length, 24, 'the keys of the uploaded bars, no restore after a find');
  assert.equal(outcome.result.feedback.cant_tell, false);
});

test('a range of eight bars or fewer is not sent again', async () => {
  const view = openView();
  const outcome = await search(view, NOKEY_TAKE, 0, upload(1, 8));
  assert.deepEqual(outcome, { outcome: 'none', note: NONE_FOUND_MESSAGE });
  assert.equal(mockRequestLog.filter((r) => r.method === 'POST' && r.path.endsWith('/takes')).length, 0);
  assert.equal(transpositionPosts().at(-1), 0);
});

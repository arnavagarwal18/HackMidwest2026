// The progress timeline: events oldest first, change against the first take, popover words, summary and empty states.
// Run: node --test frontend/tests/progress_timeline.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { FakeNode, installFakeBrowser } from './fake_env.mjs';

const env = installFakeBrowser({ search: '' });
env.restore();
const { renderProgress } = await import('../js/screens/progress.js');
const { changeAgainstFirst, eventDetails, eventLabel } = await import('../js/screens/progress_events.js');

const played = { bar_from: 3, bar_to: 4, form_flags: 0, form_checked: false, clean_bpm: null, error_rate: 0.5 };
const take = (extra) => ({ ...played, kind: 'take', source: 'take', take_id: 't1', time: null, errors: 12, played_bpm: 84, tempo_bpm: 84, ...extra });
const rep = (extra) => ({ ...played, kind: 'rep', source: 'rep', take_id: 'r1', time: null, errors: 1, played_bpm: 70, tempo_bpm: 70,
  exercise_id: 'ex1', exercise_title: 'Long tones', passed: true, reasons: [], ...extra });
const exercise = (extra) => ({ id: 'ex1', title: 'Long tones', start_bpm: 60, target_bpm: 96, best_passed_bpm: 70, complete: false, reps: 2, passes: 1, ...extra });
const done = { kind: 'exercise_done', take_id: 'r2', time: null, exercise_id: 'ex1', exercise_title: 'Long tones' };

const EVENTS = [take(), rep({ passed: false, reasons: ['2 wrong notes'] }), take({ take_id: 't2', errors: 3, played_bpm: 90, clean_bpm: 88 }), done];
const classes = (node) => node.className.split(' ');
const byClass = (root, name) => root.find((node) => classes(node).includes(name));
const render = (progress) => { const root = new FakeNode('main'); renderProgress(root, progress); return root; };
const items = (root) => byClass(root, 'timeline-item');
const popoverText = (item) => byClass(item, 'timeline-popover')[0].textContent;

test('events become timeline items in the order given, each with a short label', () => {
  const root = render({ before: null, after: null, exercises: [exercise()], events: EVENTS });
  const labels = items(root).map((item) => byClass(item, 'timeline-label')[0].textContent);
  assert.deepEqual(labels, ['Take 1: 12 errors, 84 bpm', 'Rep: Long tones at 70 bpm, not passed', 'Take 2: 3 errors, 90 bpm', 'Completed: Long tones']);
});

test('the colour classes tell takes, passed reps, failed reps and completions apart', () => {
  const root = render({ before: null, after: null, exercises: [], events: [take(), rep(), rep({ passed: false }), done] });
  assert.deepEqual(items(root).map((item) => classes(item)[1]), ['timeline-take', 'timeline-rep-pass', 'timeline-rep-fail', 'timeline-done']);
});

test('a later event shows its change against the first take, only for the same bars', () => {
  const first = take();
  assert.deepEqual(changeAgainstFirst(take({ errors: 3 }), first), { text: '−9 errors', tone: 'ok' });
  assert.deepEqual(changeAgainstFirst(take({ errors: 13 }), first), { text: '+1 error', tone: 'error' });
  assert.deepEqual(changeAgainstFirst(take({ errors: 12 }), first), { text: 'same errors', tone: 'neutral' });
  assert.equal(changeAgainstFirst(first, first), null);
  assert.equal(changeAgainstFirst(rep({ bar_from: 1 }), first), null);
  const root = render({ before: null, after: null, exercises: [], events: EVENTS });
  assert.equal(byClass(items(root)[0], 'timeline-change').length, 0);
  assert.equal(byClass(items(root)[2], 'timeline-change')[0].textContent, '−9 errors');
});

test('each card is a button wired to its popover with aria-describedby, and the popover explains the event in words', () => {
  const root = render({ before: null, after: null, exercises: [], events: EVENTS });
  const [firstItem, repItem] = items(root);
  const card = byClass(firstItem, 'timeline-card')[0];
  const tip = byClass(firstItem, 'timeline-popover')[0];
  assert.equal(card.tagName, 'button');
  assert.equal(card.attrs['aria-describedby'], tip.attrs.id);
  assert.equal(tip.attrs.role, 'tooltip');
  assert.match(popoverText(firstItem), /A take of bars 3 to 4, your first one/);
  assert.match(popoverText(firstItem), /12 notes were wrong, missed or extra \(50% of the notes\)/);
  assert.match(popoverText(firstItem), /Your form was not checked \(no camera\)/);
  assert.match(popoverText(repItem), /A practice rep of "Long tones" at 70 bpm.*did not pass/);
  assert.match(popoverText(repItem), /Why: 2 wrong notes/);
  assert.match(popoverText(items(root)[2]), /Your clean tempo, the fastest you played without mistakes, was 88 bpm/);
  assert.match(popoverText(items(root)[2]), /Compared with your first take: −9 errors/);
  assert.match(popoverText(items(root)[3]), /you passed it at its target tempo/);
});

test('popover words handle no errors and camera flags', () => {
  const first = take();
  assert.match(eventDetails(take({ errors: 0, form_checked: true, form_flags: 0 }), first).join(' '), /No notes were wrong.*no form problems/);
  assert.match(eventDetails(take({ errors: 1, form_checked: true, form_flags: 2 }), first).join(' '), /1 note was wrong.*2 form problems/);
  assert.equal(eventLabel(take({ played_bpm: null }), 1), 'Take 1: 12 errors');
});

test('tapping a card opens its popover, tapping again or pressing Escape closes it, and only one is open at a time', async () => {
  const root = render({ before: null, after: null, exercises: [], events: EVENTS });
  const [first, second] = items(root);
  const cardOf = (item) => byClass(item, 'timeline-card')[0];
  await cardOf(first).click();
  assert.equal(cardOf(first).attrs['aria-expanded'], 'true');
  assert.ok(first.classList.contains('is-open'));
  await cardOf(second).click();
  assert.ok(!first.classList.contains('is-open') && second.classList.contains('is-open'));
  cardOf(second).listeners.keydown[0]({ key: 'Escape' });
  assert.equal(cardOf(second).attrs['aria-expanded'], 'false');
  await cardOf(first).click();
  await cardOf(first).click();
  assert.ok(!first.classList.contains('is-open'));
});

test('the summary compares the first take with the latest and counts completed exercises', () => {
  const root = render({ before: null, after: null, events: EVENTS, exercises: [exercise({ complete: true }), exercise({ id: 'ex2', complete: false })] });
  const [summary] = byClass(root, 'timeline-summary');
  assert.match(summary.textContent, /12 → 3Errors, first take → latest/);
  assert.match(summary.textContent, /none yet → 88 bpmClean tempo/);
  assert.match(summary.textContent, /1 of 2Exercises completed/);
});

test('a single take shows only its own numbers in the summary', () => {
  const root = render({ before: null, after: null, events: [take()], exercises: [] });
  assert.match(byClass(root, 'timeline-summary')[0].textContent, /12Errors, first take/);
});

test('the exercise list stays under the timeline and links to the trainer', () => {
  const root = render({ before: null, after: null, events: EVENTS, exercises: [exercise()] });
  assert.equal(byClass(root, 'exercise-link')[0].attrs.href, '#/exercise/ex1');
  assert.equal(byClass(root, 'progress-compare').length, 0);
});

test('without any events, take or exercise the empty state shows; without events the old exercise list still works', () => {
  const empty = render({ before: null, after: null, exercises: [], events: [] });
  assert.ok(empty.hasText('Nothing to compare yet'));
  assert.equal(byClass(empty, 'timeline').length, 0);
  const noEvents = render({ before: null, after: null, exercises: [exercise()] });
  assert.equal(byClass(noEvents, 'exercise-item').length, 1);
  assert.equal(byClass(noEvents, 'timeline').length, 0);
});

test('events without exercises explain that no exercises exist yet', () => {
  const root = render({ before: null, after: null, events: [take()], exercises: [] });
  assert.ok(root.hasText('No exercises yet'));
  assert.equal(items(root).length, 1);
});

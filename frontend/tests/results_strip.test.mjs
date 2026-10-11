// The bar strip's verdicts and the "Loop this bar" choices, without a browser. Run: node --test frontend/tests/results_strip.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { installFakeDom } from './fake_dom.mjs';

const dom = installFakeDom();
dom.window.location.search = '?mock=1';

const { barVerdict, GLYPHS } = await import('../js/results/bar_verdict.js');
const { closestExercise, loopHintText, loopStartBpm, renderBarActions, takeLoopRequest } = await import('../js/results/loop.js');
const { state } = await import('../js/state.js');
const { createBarStrip } = await import('../js/results/strip.js');
const { createJumper } = await import('../js/results/jumper.js');

const bar = (number, extra = {}) => ({ id: `b:t1:${number}`, bar: number, expected: 4, ok: 4, wrong: 0, missed: 0, extra: 0, uncertain: 0, mean_timing_ms: 0, ...extra });
const note = (barNumber, status, cents) => ({ bar: barNumber, status, cents_off: cents });

test('a clean bar is a tick; wrong notes above the pitch are sharp, below are flat', () => {
  assert.deepEqual(barVerdict(bar(1), [], false), { tone: 'ok', kinds: ['ok'], glyph: '✓', words: 'clean' });
  assert.equal(barVerdict(bar(2), [note(2, 'wrong', 110)], true).glyph, '↑');
  assert.equal(barVerdict(bar(2), [note(2, 'wrong', -90)], true).tone, 'flat');
  assert.equal(barVerdict(bar(2), [note(3, 'wrong', 110)], true).tone, 'unclear', 'notes of other bars do not count');
  assert.equal(barVerdict(bar(2), [note(2, 'ok', 30)], false).tone, 'ok', 'only wrong notes give a pitch direction');
});

test('timing past 80 ms is late (+) or early (-), and both glyphs show when pitch is off too', () => {
  assert.equal(barVerdict(bar(1, { mean_timing_ms: 82 }), [], true).glyph, '→');
  assert.equal(barVerdict(bar(1, { mean_timing_ms: -95 }), [], true).tone, 'early');
  assert.equal(barVerdict(bar(1, { mean_timing_ms: 80 }), [], false).tone, 'ok');
  const both = barVerdict(bar(1, { mean_timing_ms: -95 }), [note(1, 'wrong', 100)], true);
  assert.deepEqual([both.tone, both.glyph, both.words], ['sharp', '↑ ←', 'sharp, early']);
});

test('a flagged bar with no direction (a missed note) is "needs work", not clean', () => {
  const verdict = barVerdict(bar(1, { missed: 1, ok: 3 }), [note(1, 'missed', null)], true);
  assert.deepEqual([verdict.tone, verdict.glyph], ['unclear', GLYPHS.unclear]);
});

const plan = { exercises: [{ id: 'wide', bar_from: 1, bar_to: 8 }, { id: 'near', bar_from: 3, bar_to: 4 }, { id: 'far', bar_from: 10, bar_to: 12 }] };

test('the loop opens the narrowest plan exercise covering the bar, else the nearest, else none', () => {
  assert.equal(closestExercise(plan, 4).id, 'near');
  assert.equal(closestExercise(plan, 7).id, 'wide');
  assert.equal(closestExercise({ exercises: [plan.exercises[2]] }, 8).id, 'far');
  assert.equal(closestExercise({ exercises: [] }, 4), null);
  assert.equal(closestExercise(null, 4), null);
});

test('the loop starts at 75% of the tempo played, or says nothing without a tempo', () => {
  assert.equal(loopStartBpm({ tempo: { played_bpm: 88 } }), 66);
  assert.equal(loopStartBpm({ tempo: {} }), null);
  assert.equal(loopStartBpm({}), null);
  const near = plan.exercises[1];
  assert.match(loopHintText({ bar: 4, bpm: 66 }, near), /Looping bar 4.*start near 66 BPM.*75%/);
  assert.doesNotMatch(loopHintText({ bar: 4, bpm: 66 }, near), /closest/);
  assert.match(loopHintText({ bar: 9, bpm: null }, near), /no exercise for bar 9.*closest/);
});

test('Loop this bar links to the exercise and leaves a request the trainer reads once; Play again goes to the take screen', () => {
  const actions = renderBarActions(bar(4), { plan, analysis: { tempo: { played_bpm: 88 } } });
  const loop = actions.withClass('loop-bar')[0];
  assert.equal(loop.textContent, 'Loop this bar');
  assert.equal(loop.attributes.href, '#/exercise/near');
  loop.click();
  assert.deepEqual(state.loop_request, { exercise_id: 'near', bar: 4, bpm: 66 });
  assert.equal(takeLoopRequest('other'), null, 'a request for another exercise is dropped');
  assert.equal(state.loop_request, null);
  actions.button('Play again').click();
  assert.equal(dom.window.location.hash, '#/take');
  assert.ok(actions.button('Play again').className.includes('secondary'));
  assert.ok(!actions.button('Play again').className.includes('primary'));
});

test('a plan with no exercise leaves a note instead of a Loop button', () => {
  const actions = renderBarActions(bar(4), { plan: { exercises: [] }, analysis: {} });
  assert.equal(actions.withClass('loop-bar').length, 0);
  assert.match(actions.texts('loop-missing')[0], /No loop exercise/);
});

test('the strip has one cell per bar in order, each with a glyph and an aria-label; tapping shows the detail and seeks without highlighting', () => {
  const analysis = {
    bars: [bar(2, { mean_timing_ms: 90, mean: 0 }), bar(1)],
    notes: [],
    problems: [{ bars: [2, 2], score: 1 }],
  };
  const seeks = [];
  const jumper = createJumper({ player: { seekTo: (s) => seeks.push(s) }, barList: { highlight: () => assert.fail('the strip must not scroll to the list') } });
  const index = { places: new Map([['b:t1:2', { bar: 2, time_s: 6, lead_s: 1 }]]), firstTimeInBar: new Map() };
  const strip = createBarStrip(analysis, { index, jumper, renderActions: () => dom.document.createElement('p') });
  const cells = strip.section.all().filter((n) => n.tagName === 'BUTTON');
  assert.deepEqual(cells.map((c) => c.attributes['data-bar']), ['1', '2']);
  assert.deepEqual(cells.map((c) => c.texts('bar-cell-glyph')[0]), ['✓', '→']);
  assert.match(cells[1].attributes['aria-label'], /Bar 2: late/);
  assert.ok(cells[0].className.includes('tone-ok') && cells[1].className.includes('tone-late'));
  cells[1].click();
  assert.deepEqual(seeks, [5]);
  assert.match(strip.section.texts('bar-detail')[0], /late.*Bar 2/);
  assert.equal(cells[1].attributes['aria-pressed'], 'true');
  assert.equal(createBarStrip({ bars: [] }, { index, jumper, renderActions: () => null }), null);
});

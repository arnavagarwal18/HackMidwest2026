// The bar verdicts and levels, the Bar by bar boxes and the "Loop this bar" choices, without a browser. Run: node --test frontend/tests/results_strip.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { installFakeDom } from './fake_dom.mjs';

const dom = installFakeDom();
dom.window.location.search = '?mock=1';

const { barVerdict, GLYPHS } = await import('../js/results/bar_verdict.js');
const { closestExercise, loopHintText, loopStartBpm, renderBarActions, takeLoopRequest } = await import('../js/results/loop.js');
const { state } = await import('../js/state.js');
const { createBarStrip } = await import('../js/results/strip.js');
const { barLevel, LEVEL_WORDS, worstBarIndex } = await import('../js/results/bar_level.js');
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

// Bars 1 to 4: 1 clean, 2 late (okay), 3 missing two of four notes (needs work), 4 one wrong note sharp (okay). Bar 3 is the worst.
const gridAnalysis = {
  bars: [bar(4, { ok: 3, wrong: 1 }), bar(3, { ok: 2, missed: 2 }), bar(2, { mean_timing_ms: 90 }), bar(1)],
  notes: [note(4, 'wrong', 60)],
  problems: [{ bars: [2, 2], score: 0.9 }, { bars: [3, 3], score: 0.5 }],
};
const gridIndex = { places: new Map([['b:t1:2', { bar: 2, time_s: 6, lead_s: 1 }], ['b:t1:3', { bar: 3, time_s: 9, lead_s: 1 }]]), firstTimeInBar: new Map() };

// The grid wired to a jumper that records seeks, the way results/view.js wires them.
function grid(analysis = gridAnalysis, sentences = []) {
  const seeks = [];
  let strip = null;
  const jumper = createJumper({ player: { seekTo: (s) => seeks.push(s) }, barBoxes: { select: (n, options) => strip.select(n, options) } });
  const renderActions = (b) => Object.assign(dom.document.createElement('p'), { className: `loop-for-${b.bar}` });
  strip = createBarStrip(analysis, { jumpContext: { index: gridIndex, jumper }, sentences, renderActions });
  const boxes = strip.section.all().filter((n) => n.tagName === 'BUTTON' && n.className.includes('bar-box'));
  boxes.forEach((box) => { box.scrollIntoView = () => { box.scrolled = true; }; });
  return { strip, boxes, seeks, jumper, detail: () => strip.section.withClass('bar-detail')[0] };
}
const pressed = (boxes) => boxes.filter((box) => box.attributes['aria-pressed'] === 'true').map((box) => box.attributes['data-bar']);
// Sends a keydown from boxes[from] to the grid; returns whether the grid took the key (preventDefault).
function key(boxes, from, name) {
  let taken = false;
  boxes[0].parent.listeners.keydown.forEach((fn) => fn({ key: name, target: boxes[from], preventDefault: () => { taken = true; } }));
  return taken;
}

test('one box per bar in order, each with its number, no visible status word, and the word in its aria-label and title', () => {
  const { boxes } = grid();
  assert.deepEqual(boxes.map((b) => b.attributes['data-bar']), ['1', '2', '3', '4']);
  assert.deepEqual(boxes.map((b) => b.texts('bar-box-num')[0]), ['1', '2', '3', '4']);
  assert.deepEqual(boxes.map((b) => b.textContent), ['1', '2', '3', '4'], 'a tile shows only its bar number');
  assert.deepEqual(boxes.map((b) => b.attributes['aria-label']), ['Bar 1: Good', 'Bar 2: Okay', 'Bar 3: Needs work', 'Bar 4: Okay']);
  assert.deepEqual(boxes.map((b) => b.attributes.title), ['Bar 1: Good', 'Bar 2: Okay', 'Bar 3: Needs work', 'Bar 4: Okay']);
  assert.deepEqual(boxes.map((b) => b.className.split(' ')[1]), ['level-good', 'level-okay', 'level-needs-work', 'level-okay'], 'the colour class is kept');
  assert.deepEqual(boxes.map((b) => b.attributes.type), ['button', 'button', 'button', 'button']);
  assert.equal(createBarStrip({ bars: [] }, { jumpContext: { index: gridIndex, jumper: null }, sentences: [], renderActions: () => null }), null);
});

test('a clean bar is Good, a late or slightly off bar Okay, a bar under 75% right or off two ways Needs work', () => {
  const level = (b, notes, flagged) => barLevel(b, barVerdict(b, notes, flagged));
  assert.equal(level(bar(1), [], false), 'good');
  assert.equal(level(bar(1, { mean_timing_ms: 90 }), [], true), 'okay');
  assert.equal(level(bar(1, { ok: 3, wrong: 1 }), [note(1, 'wrong', 50)], true), 'okay');
  assert.equal(level(bar(1, { ok: 2, wrong: 2 }), [note(1, 'wrong', 50)], true), 'needs-work');
  assert.equal(level(bar(1, { ok: 3, wrong: 1, mean_timing_ms: 90 }), [note(1, 'wrong', 50)], true), 'needs-work');
  assert.deepEqual(Object.values(LEVEL_WORDS), ['Good', 'Okay', 'Needs work']);
});

test('the worst bar is selected at first without playing anything, and the legend explains the three words', () => {
  const { boxes, seeks, detail, strip } = grid();
  assert.deepEqual(pressed(boxes), ['3']);
  assert.ok(boxes[2].className.includes('selected'));
  assert.deepEqual(seeks, [], 'nothing plays on its own');
  assert.equal(detail().texts('bar-detail-title')[0], 'Bar 3 · Needs work');
  assert.deepEqual(strip.section.withClass('bar-legend')[0].children.map((item) => item.textContent), [
    'Good right notes, on the beat', 'Okay a small slip in notes, timing or form', 'Needs work several notes off, or notes and timing both off',
  ]);
  assert.equal(worstBarIndex([bar(1), bar(2)], ['okay', 'okay'], [2]), 1, 'on a tie the worse-ranked problem bar wins');
  assert.equal(worstBarIndex([bar(1), bar(2)], ['good', 'good'], []), 0, 'with nothing flagged the first bar');
});

test("clicking a box selects it and shows that bar's details: counts, why it was flagged, its sentences, Play this bar and the loop actions", () => {
  const sentences = [{ text: 'Bar 2 came in late.', jump: { bar: 2 } }, { text: 'Bar 3 lost two notes.', jump: { bar: 3 } }];
  const { boxes, detail, seeks } = grid(gridAnalysis, sentences);
  boxes[1].click();
  assert.deepEqual(pressed(boxes), ['2']);
  assert.deepEqual(boxes.map((b) => b.attributes.tabindex), ['-1', '0', '-1', '-1'], 'the selected box is the one tab stop');
  const shown = detail();
  assert.equal(shown.texts('bar-detail-title')[0], 'Bar 2 · Okay');
  assert.match(shown.texts('bar-detail-verdict')[0], /late/);
  assert.match(shown.texts('bar-counts')[0], /4 of 4 right/);
  assert.equal(shown.withClass('bar-reason').length, 1, 'a flagged bar says why');
  assert.deepEqual(shown.texts('sentence-text'), ['Bar 2 came in late.'], "only this bar's sentences");
  assert.equal(shown.withClass('loop-for-2').length, 1, 'the loop actions of a flagged bar');
  assert.deepEqual(seeks, [], 'a click selects; it does not play');
  shown.button('Play this bar').click();
  assert.deepEqual(seeks, [5]);
  assert.deepEqual(pressed(boxes), ['2']);
  boxes[0].click();
  assert.equal(detail().withClass('loop-for-1').length, 0, 'a clean bar has no loop actions');
  assert.equal(detail().button('Play this bar'), undefined, 'no Play this bar without a time for the bar');
});

test('arrow keys, Home and End move between the boxes and select the one in focus; other keys are left alone', () => {
  const { boxes } = grid();
  assert.ok(key(boxes, 2, 'ArrowRight'));
  assert.equal(dom.document.activeElement, boxes[3]);
  assert.deepEqual(pressed(boxes), ['4']);
  key(boxes, 3, 'ArrowRight');
  assert.equal(dom.document.activeElement, boxes[3], 'the last box stays put');
  key(boxes, 3, 'ArrowLeft');
  assert.deepEqual(pressed(boxes), ['3']);
  key(boxes, 2, 'ArrowUp');
  assert.deepEqual(pressed(boxes), ['2']);
  key(boxes, 1, 'ArrowDown');
  assert.deepEqual(pressed(boxes), ['3']);
  key(boxes, 2, 'Home');
  assert.equal(dom.document.activeElement, boxes[0]);
  key(boxes, 0, 'End');
  assert.deepEqual(pressed(boxes), ['4']);
  assert.equal(key(boxes, 3, 'Tab'), false);
  assert.deepEqual(pressed(boxes), ['4']);
});

test('a jump to a bar (a coach link or a sentence) seeks, selects its box and brings it into view', () => {
  const { boxes, seeks, jumper } = grid();
  jumper.jumpTo({ bar: 2, time_s: 6, lead_s: 1 });
  assert.deepEqual(seeks, [5]);
  assert.deepEqual(pressed(boxes), ['2']);
  assert.ok(boxes[1].scrolled);
});

test('a bar with 0 expected notes (past the end of the take) gets no box, even with an extra note', () => {
  const past = bar(5, { expected: 0, ok: 0, extra: 2 });
  const { boxes, strip } = grid({ ...gridAnalysis, bars: [...gridAnalysis.bars, past] });
  assert.deepEqual(boxes.map((box) => box.attributes['data-bar']), ['1', '2', '3', '4']);
  assert.equal(strip.hasBar(5), false);
});

// Why each flagged bar is flagged, and that "Bars to work on" counts exactly the listed bars. Run: node --test frontend/tests/results_bar_reasons.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { installFakeDom } from './fake_dom.mjs';

const dom = installFakeDom();
dom.window.location.search = '?mock=1';

const { problemBars } = await import('../js/results/bars.js');
const { renderBarDetail } = await import('../js/results/bar_detail.js');
const { buildMeasurementIndex } = await import('../js/results/measurements.js');
const { problemBarCounts } = await import('../js/results/bar_kinds.js');
const { reasonsForBar } = await import('../js/results/problem_reasons.js');
const { renderStatStrip } = await import('../js/results/stats.js');

const bar = (number, extra = {}) => ({ id: `b:t1:${number}`, bar: number, expected: 4, ok: 4, wrong: 0, missed: 0, extra: 0, uncertain: 0, ...extra });
const posture = (bars, score) => ({ kind: 'form', bars, score, numbers: { label: 'slouching' } });

// Shaped like a real take: one extra note in bar 4, and posture flags over bars 1, 2-3 and 7-8.
const analysis = {
  bars: [1, 2, 3, 4, 5, 6, 7, 8].map((n) => (n === 4 ? bar(4, { expected: 3, ok: 3, extra: 1 }) : bar(n))),
  notes: [],
  problems: [{ kind: 'notes', bars: [4], score: 0.23, numbers: { wrong: 0, missed: 0, extra: 1 } }, posture([7, 8], 0.028), posture([2, 3], 0.023), posture([1], 0.006)],
};

test('a bar flagged only by a posture flag says so, and a bar with note mistakes leaves the notes reason to its counts', () => {
  assert.deepEqual(reasonsForBar(analysis, analysis.bars[0]), ['Posture: slouching']);
  assert.deepEqual(reasonsForBar(analysis, analysis.bars[3]), []);
  assert.deepEqual(reasonsForBar(analysis, analysis.bars[4]), []);
});

test('timing, tempo and unknown kinds each get a reason; a covered bar with clean notes still names the notes problem', () => {
  const clean = bar(3);
  const problems = [
    { kind: 'late', bars: [3], score: 0.7, numbers: { mean_ms: 88.4, count: 2 } },
    { kind: 'dragging', bars: [2, 3], score: 0.5, numbers: {} },
    { kind: 'notes', bars: [3], score: 0.4, numbers: {} },
    { kind: 'mystery', bars: [3], score: 0.1 },
  ];
  const warnings = [];
  const original = console.warn;
  console.warn = (message) => warnings.push(message);
  try {
    assert.deepEqual(reasonsForBar({ problems }, clean), ['Playing late (88 ms)', 'Dragging the tempo', 'Note problems', 'mystery']);
  } finally {
    console.warn = original;
  }
  assert.equal(warnings.length, 1);
});

// The Bar by bar detail of one bar, as one node.
function barDetail(barToShow) {
  const node = dom.document.createElement('div');
  const look = { verdict: { glyph: '!', words: 'needs work' }, level: 'okay', flagged: true };
  const jumpContext = { index: buildMeasurementIndex(analysis), jumper: { jumpTo() {} } };
  node.append(...renderBarDetail(barToShow, look, { analysis, jumpContext, sentences: [], renderActions: () => dom.document.createElement('p') }));
  return node;
}

test('the detail of every flagged bar says why, and the Bars to work on count equals the flagged bars', () => {
  const listed = problemBars(analysis).map((b) => b.bar);
  assert.deepEqual(listed, [4, 7, 8, 2, 3, 1]);
  problemBars(analysis).forEach((flagged) => {
    const detail = barDetail(flagged);
    const text = detail.texts('bar-counts')[0] + (detail.texts('bar-reason')[0] ?? '');
    assert.ok(/extra|Flagged: Posture: slouching/.test(text), `bar ${flagged.bar} gives no reason: ${text}`);
  });
  const count = renderStatStrip({ ...analysis, bars: analysis.bars.map((b) => ({ ...b })) }).all().find((n) => n.texts('lbl')[0] === 'Bars to work on');
  assert.equal(count.texts('num')[0], String(listed.length));
});

const statBox = (summary, label) => summary.all().find((n) => n.texts('lbl')[0] === label);
// The reported take: posture flags over bars 1, 3, 7 and 8 and one extra note in bar 4, so five bars in all.
const odeAnalysis = { ...analysis, problems: [analysis.problems[0], posture([7, 8], 0.028), posture([3], 0.023), posture([1], 0.006)], notes: [{ timing_ms: 5 }, { timing_ms: -20 }] };
const odeSummary = () => renderStatStrip(odeAnalysis);

test('an Ode-to-Joy take (all notes right, four posture bars, one extra note) says 5 bars to work on, split by kind, with a qualified headline', () => {
  assert.deepEqual(problemBarCounts(odeAnalysis), { note: 1, timing: 0, form: 4, other: 0, total: 5 });
  const summary = odeSummary();
  const box = statBox(summary, 'Bars to work on');
  assert.equal(box.texts('num')[0], '5');
  assert.equal(box.texts('detail')[0], '1 note, 4 form');
  assert.ok(!box.className.includes('bad'), 'strong pitch with only form and extra-note flags is not red');
  assert.equal(summary.texts('headline')[0], 'Solid take: the notes and the timing both held up - check the flagged bars below.');
});

test('a take flagged only by form says to check the form flags; a clean take is still plain Solid take with 0 bars', () => {
  const formOnly = { ...odeAnalysis, bars: analysis.bars.map((b) => ({ ...b, extra: 0, expected: 4, ok: 4 })), problems: odeAnalysis.problems.slice(1) };
  assert.equal(renderStatStrip(formOnly).texts('headline')[0], 'Solid take: the notes and the timing both held up - check the form flags below.');
  const clean = renderStatStrip({ bars: [bar(1), bar(2)], notes: [{ timing_ms: 5 }], problems: [] });
  assert.equal(clean.texts('headline')[0], 'Solid take: the notes and the timing both held up.');
  assert.equal(statBox(clean, 'Bars to work on').texts('num')[0], '0');
  assert.ok(statBox(clean, 'Bars to work on').className.includes('good'));
});

test('weak pitch keeps the bars to work on red, and the detail pluralises and names timing bars', () => {
  const weak = { bars: [bar(1, { ok: 2, wrong: 2 }), bar(2, { ok: 3, missed: 1 }), bar(3)], notes: [{ timing_ms: 5 }], problems: [{ kind: 'late', bars: [3], score: 0.4, numbers: {} }] };
  const box = statBox(renderStatStrip(weak), 'Bars to work on');
  assert.equal(box.texts('detail')[0], '2 notes, 1 timing');
  assert.ok(box.className.includes('bad'));
});

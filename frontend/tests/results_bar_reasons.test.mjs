// Why each flagged bar is flagged, and that "Bars to fix" counts exactly the listed bars. Run: node --test frontend/tests/results_bar_reasons.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { installFakeDom } from './fake_dom.mjs';

const dom = installFakeDom();
dom.window.location.search = '?mock=1';

const { createBarList, problemBars } = await import('../js/results/bars.js');
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

test('every row of the list says why, and the Bars to fix count equals the rows', () => {
  const listed = problemBars(analysis).map((b) => b.bar);
  assert.deepEqual(listed, [4, 7, 8, 2, 3, 1]);
  const rows = createBarList(analysis).section.all().filter((n) => n.tagName === 'LI');
  assert.equal(rows.length, listed.length);
  rows.forEach((row) => {
    const text = row.texts('bar-counts')[0] + (row.texts('bar-reason')[0] ?? '');
    assert.ok(/extra|Flagged: Posture: slouching/.test(text), `row ${row.attributes['data-bar']} gives no reason: ${text}`);
  });
  const count = renderStatStrip({ ...analysis, bars: analysis.bars.map((b) => ({ ...b })) }).all().find((n) => n.texts('lbl')[0] === 'Bars to fix');
  assert.equal(count.texts('num')[0], String(listed.length));
});

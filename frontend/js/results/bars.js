// The bars with a problem, worst first, and the counts, drift and meter of one bar (the Bar by bar detail shows them).
import { element } from '../dom.js';
import { hasMistakes } from './problem_reasons.js';

function barScores(problems) {
  const scores = new Map();
  problems.forEach((problem) => {
    const [from, to = from] = problem.bars ?? [];
    for (let bar = from; bar <= to; bar += 1) scores.set(bar, Math.max(scores.get(bar) ?? 0, problem.score ?? 0));
  });
  return scores;
}

// Bars that any problem covers or that have a mistake, ordered by their worst problem score (then by bar number).
export function problemBars(analysis) {
  const scores = barScores(analysis.problems ?? []);
  return (analysis.bars ?? [])
    .filter((bar) => scores.has(bar.bar) || hasMistakes(bar))
    .sort((a, b) => (scores.get(b.bar) ?? 0) - (scores.get(a.bar) ?? 0) || a.bar - b.bar);
}

function countsText(bar) {
  const parts = [`${bar.ok} of ${bar.expected} right`];
  [['wrong', 'wrong'], ['missed', 'missed'], ['extra', 'extra'], ['uncertain', 'unsure']].forEach(([field, label]) => {
    if (bar[field] > 0) parts.push(`${bar[field]} ${label}`);
  });
  return parts.join(', ');
}

export function driftText(bar) {
  if (!bar.drift) return '';
  const pct = bar.drift_pct === null || bar.drift_pct === undefined ? '' : ` (${bar.drift_pct > 0 ? '+' : ''}${bar.drift_pct}%)`;
  return `${bar.drift}${pct}`;
}

// How much of the bar was played right, as a whole percentage (0 to 100).
function rightPercent(bar) {
  return bar.expected ? Math.round((100 * bar.ok) / bar.expected) : 0;
}

// A thin bar under the counts that fills with the share of notes played right; the counts say the same in words.
function renderMeter(bar) {
  const meter = element('div', '', 'meter', { 'aria-hidden': 'true' });
  meter.append(element('i', '', '', { style: `width: ${rightPercent(bar)}%` }));
  return meter;
}

// The detail of one bar (its number, counts, drift and meter), added to `container`.
export function addBarDetail(container, bar) {
  container.append(element('strong', `Bar ${bar.bar}`), element('span', countsText(bar), 'bar-counts'));
  const drift = driftText(bar);
  if (drift) container.append(element('span', drift, `bar-drift drift-${bar.drift}`));
  container.append(renderMeter(bar));
  return container;
}

// The strip of key numbers at the top of the results: notes right, bars to fix and average timing. Everything comes from analysis.bars.
import { element } from '../dom.js';
import { problemBars } from './bars.js';

function sum(bars, field) {
  return bars.reduce((total, bar) => total + (bar[field] ?? 0), 0);
}

function averageTimingMs(bars) {
  const timings = bars.map((bar) => bar.mean_timing_ms).filter((ms) => typeof ms === 'number');
  if (!timings.length) return null;
  return Math.round(timings.reduce((total, ms) => total + ms, 0) / timings.length);
}

function stat(value, label, tone = '') {
  const box = element('div', '', `stat ${tone}`.trim());
  box.append(element('div', value, 'num'), element('div', label, 'lbl'));
  return box;
}

// Returns the strip, or null when the analysis has no bars to count.
export function renderStatStrip(analysis) {
  const bars = analysis.bars ?? [];
  const expected = sum(bars, 'expected');
  if (!expected) return null;
  const right = sum(bars, 'ok');
  const toFix = problemBars(analysis).length;
  const timing = averageTimingMs(bars);
  const strip = element('div', '', 'score-strip', { role: 'group', 'aria-label': 'Summary of this take' });
  strip.append(stat(`${right} / ${expected}`, 'Notes right', right === expected ? 'good' : ''), stat(String(toFix), 'Bars to fix', toFix ? 'bad' : 'good'));
  if (timing !== null) strip.append(stat(`${timing > 0 ? '+' : ''}${timing} ms`, 'Avg timing'));
  return strip;
}

// Bar by bar: one box per bar, showing its number on its level's colour. The level word (Good / Okay / Needs work) is the box's
// accessible name and hover text, and the legend under the grid explains the colours.
// The boxes are buttons in one tab stop: arrow keys, Home and End move between them, and the box in focus is selected.
// The selected box (the worst bar at first) shows its detail below the grid (bar_detail.js). A jump to a bar selects its box.
import { element } from '../dom.js';
import { playedBars, problemBars } from './bars.js';
import { barLevel, LEVEL_MEANINGS, LEVEL_WORDS, LEVELS, worstBarIndex } from './bar_level.js';
import { renderBarDetail } from './bar_detail.js';
import { barVerdict } from './bar_verdict.js';

const MAX_COLUMNS = 12; // a wide row holds up to this many boxes, then wraps
const MOVES = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 };
const boxClass = (level, selected) => `bar-box level-${level}${selected ? ' selected' : ''}`;

function boxFor(bar, level) {
  const boxName = `Bar ${bar.bar}: ${LEVEL_WORDS[level]}`;
  const box = element('button', '', boxClass(level, false), {
    type: 'button',
    'data-bar': String(bar.bar),
    'data-level': level,
    'aria-pressed': 'false',
    'aria-controls': 'bar-detail',
    'aria-label': boxName,
    title: boxName,
    tabindex: '-1',
  });
  box.append(element('span', String(bar.bar), 'bar-box-num'));
  return box;
}

function legend() {
  const list = element('ul', '', 'bar-legend', { 'aria-label': 'What the words mean' });
  LEVELS.forEach((level) => {
    const item = element('li', '', `level-${level}`);
    item.append(element('strong', LEVEL_WORDS[level]), ` ${LEVEL_MEANINGS[level]}`);
    list.append(item);
  });
  return list;
}

// The index to move to from `at` for a key, or null for any other key.
function targetIndex(key, at, count) {
  if (key === 'Home') return 0;
  if (key === 'End') return count - 1;
  if (!(key in MOVES)) return null;
  return Math.min(count - 1, Math.max(0, at + MOVES[key]));
}

// context: { jumpContext, sentences, renderActions } (see bar_detail.js).
// Returns { section, select(barNumber, { reveal }), hasBar(barNumber) }, or null when the take has no bars.
export function createBarStrip(analysis, context) {
  const bars = playedBars(analysis).sort((a, b) => a.bar - b.bar);
  if (!bars.length) return null;
  const detailContext = { ...context, analysis };
  const problemOrder = problemBars(analysis).map((bar) => bar.bar);
  const looks = bars.map((bar) => {
    const flagged = problemOrder.includes(bar.bar);
    const verdict = barVerdict(bar, analysis.notes ?? [], flagged);
    return { verdict, flagged, level: barLevel(bar, verdict) };
  });
  const section = element('section', '', 'bar-strip-section', { 'aria-labelledby': 'bars-title' });
  const grid = element('div', '', 'bar-strip', { role: 'group', 'aria-label': 'Every bar of this take', style: `--bar-columns: ${Math.min(bars.length, MAX_COLUMNS)}` });
  const boxes = bars.map((bar, i) => boxFor(bar, looks[i].level));
  grid.append(...boxes);
  const detail = element('div', '', 'bar-detail', { id: 'bar-detail', 'aria-live': 'polite' });
  section.append(
    element('h2', 'Bar by bar', 'bars-title', { id: 'bars-title' }),
    element('p', 'Pick a bar to see what happened in it.', 'muted bars-lead'),
    grid,
    legend(),
    detail,
  );

  function selectAt(at, { reveal = false } = {}) {
    boxes.forEach((box, i) => {
      box.className = boxClass(looks[i].level, i === at);
      box.setAttribute('aria-pressed', String(i === at));
      box.setAttribute('tabindex', i === at ? '0' : '-1');
    });
    detail.replaceChildren(...renderBarDetail(bars[at], looks[at], detailContext));
    if (reveal) boxes[at].scrollIntoView({ block: 'center' });
  }

  function select(barNumber, options) {
    const at = bars.findIndex((bar) => bar.bar === barNumber);
    if (at >= 0) selectAt(at, options);
  }

  boxes.forEach((box, i) => box.addEventListener('click', () => selectAt(i)));
  grid.addEventListener('keydown', (event) => {
    const at = targetIndex(event.key, boxes.indexOf(event.target), boxes.length);
    if (at === null) return;
    event.preventDefault();
    boxes[at].focus();
    selectAt(at);
  });
  selectAt(worstBarIndex(bars, looks.map((look) => look.level), problemOrder));
  return { section, select, hasBar: (barNumber) => bars.some((bar) => bar.bar === barNumber) };
}

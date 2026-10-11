// The bar strip under the summary: one cell per bar, tinted by its result and carrying a glyph (colour is never the only cue).
// Tapping a cell shows that bar's detail below the strip and seeks the recording. That is the only second level.
import { element } from '../dom.js';
import { addBarDetail, problemBars } from './bars.js';
import { barVerdict, GLYPHS, WORDS } from './bar_verdict.js';
import { resolveId } from './measurements.js';

const SELECTED_CLASS = 'selected';

const cellClass = (verdict, selected) => `bar-cell tone-${verdict.tone}${selected ? ` ${SELECTED_CLASS}` : ''}`;

function cellFor(bar, verdict) {
  const cell = element('button', '', cellClass(verdict, false), {
    type: 'button',
    'data-bar': String(bar.bar),
    'aria-pressed': 'false',
    'aria-controls': 'bar-detail',
    'aria-label': `Bar ${bar.bar}: ${verdict.words}. Show details`,
  });
  cell.append(element('span', String(bar.bar), 'bar-cell-num'), element('span', verdict.glyph, 'bar-cell-glyph', { 'aria-hidden': 'true' }));
  return cell;
}

function legend(verdicts) {
  const kinds = [...new Set(verdicts.flatMap((verdict) => verdict.kinds))];
  const list = element('p', '', 'bar-legend muted');
  list.textContent = kinds.map((kind) => `${GLYPHS[kind]} ${WORDS[kind]}`).join('   ');
  return list;
}

// context: { index, jumper, renderActions }. renderActions(bar) gives the buttons for a flagged bar.
// Returns { section, select(barNumber) }, or null when the take has no bars.
export function createBarStrip(analysis, { index, jumper, renderActions }) {
  const bars = [...(analysis.bars ?? [])].sort((a, b) => a.bar - b.bar);
  if (!bars.length) return null;
  const flagged = new Set(problemBars(analysis).map((bar) => bar.bar));
  const verdicts = bars.map((bar) => barVerdict(bar, analysis.notes ?? [], flagged.has(bar.bar)));
  const section = element('section', '', 'bar-strip-section card');
  const strip = element('div', '', 'bar-strip', { role: 'group', 'aria-label': 'Every bar of this take' });
  const cells = bars.map((bar, i) => cellFor(bar, verdicts[i]));
  strip.append(...cells);
  const detail = element('div', '', 'bar-detail', { id: 'bar-detail', 'aria-live': 'polite' });
  const header = element('div', '', 'card-header');
  const body = element('div', '', 'card-body');
  header.append(element('h2', 'Bar by bar'));
  body.append(strip, legend(verdicts), detail);
  section.append(header, body);

  function select(barNumber) {
    const at = bars.findIndex((bar) => bar.bar === barNumber);
    if (at < 0) return;
    const bar = bars[at];
    cells.forEach((cell, i) => {
      cell.className = cellClass(verdicts[i], i === at);
      cell.setAttribute('aria-pressed', String(i === at));
    });
    const heading = element('p', `${verdicts[at].glyph} ${verdicts[at].words}`, 'bar-detail-verdict');
    const body = element('div', '', 'bar-detail-body');
    addBarDetail(body, bar);
    detail.replaceChildren(heading, body);
    if (flagged.has(bar.bar)) detail.append(renderActions(bar));
    jumper.jumpTo(resolveId(bar.id, index), { highlight: false });
  }

  cells.forEach((cell, i) => cell.addEventListener('click', () => select(bars[i].bar)));
  return { section, select };
}

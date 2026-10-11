// The detection chip above the results: what the app heard ("Heard: 4 semitones down · bars 1-8"), with Change, which opens
// the existing transposition control. The key comes from analysis.transposition; the bars from analysis.bars, else the take setup.
import { button, element } from '../dom.js';
import { state } from '../state.js';
import { renderTranspositionControl } from './transposition.js';

export function keyText(semitones) {
  if (!semitones) return 'in the written key';
  return `${Math.abs(semitones)} semitone${Math.abs(semitones) === 1 ? '' : 's'} ${semitones > 0 ? 'up' : 'down'}`;
}

// { from, to } of the bars checked, or null when neither the analysis nor the take setup says.
export function barRange(analysis, setup = state.take_setup) {
  const numbers = (analysis.bars ?? []).map((bar) => bar.bar);
  if (numbers.length) return { from: Math.min(...numbers), to: Math.max(...numbers) };
  return setup?.bar_from && setup?.bar_to ? { from: setup.bar_from, to: setup.bar_to } : null;
}

export function barsText(range) {
  return range.from === range.to ? `bar ${range.from}` : `bars ${range.from}–${range.to}`;
}

export function detectionText(analysis, setup) {
  const range = barRange(analysis, setup);
  return ['Heard:', [keyText(analysis.transposition?.semitones ?? 0), range && barsText(range)].filter(Boolean).join(' · ')].join(' ');
}

// onChanged(semitones) runs after the back end accepted a new key (the screen then checks the take again).
export function renderDetectionChip(analysis, { sessionId, onChanged }) {
  const wrapper = element('section', '', 'detection');
  const chip = element('div', '', 'detect-chip');
  const panel = element('div', '', 'detect-panel', { id: 'detect-panel' });
  panel.hidden = true;
  panel.append(renderTranspositionControl({ sessionId, current: analysis.transposition?.semitones ?? 0, onChanged }));
  const change = button('Change', () => {
    panel.hidden = !panel.hidden;
    change.setAttribute('aria-expanded', String(!panel.hidden));
  }, 'detect-change');
  change.setAttribute('aria-expanded', 'false');
  change.setAttribute('aria-controls', 'detect-panel');
  chip.append(element('span', detectionText(analysis, state.take_setup), 'detect-text'), change);
  wrapper.append(chip, panel);
  return wrapper;
}

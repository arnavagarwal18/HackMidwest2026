// The screen's non-result states: working, slow, gave up, failed, can't tell.
import { button, element } from '../dom.js';
import { renderStepList } from './wait_steps.js';

export const SLOW_TEXT = 'Still working - this can take a while for long takes';
export const TOO_LONG_TEXT = 'This is taking too long';

export function recordAgainButton(primary = false) {
  return button('Record again', () => { window.location.hash = '#/take'; }, primary ? 'record-again primary' : 'record-again');
}

export const cancelWaiting = () => { window.location.hash = '#/take'; }; // leaving stops the polling; the recording screen is the way back

// Shows the step list for `stage` and a Cancel button (default: back to the recording screen).
export function renderWorking(view, stage, slow, onCancel = cancelWaiting) {
  const panel = element('div', '', 'results-status', { role: 'status' });
  panel.append(element('p', `${stage}...`, 'stage'), renderStepList(stage));
  if (slow) panel.append(element('p', SLOW_TEXT, 'muted slow-note'));
  panel.append(button('Cancel', onCancel, 'cancel-wait'));
  view.replaceChildren(element('h1', 'Results'), panel);
}

// The automatic search: 'Trying bars 1–8' (only while other bars are tried) and 'Trying key -4 (3 of 24)', with a
// Cancel button that puts the original key back. progress: { bars?: { from, to }, semitones?, tried?, total? }.
export function renderKeySearch(view, { bars, semitones, tried, total }, onCancel) {
  const panel = element('div', '', 'results-status key-search', { role: 'status' });
  const cancel = button('Cancel', () => { cancel.disabled = true; onCancel(); }, 'cancel-key-search');
  if (bars) panel.append(element('p', `Trying bars ${bars.from}–${bars.to}`, 'stage bars-stage'));
  if (semitones !== undefined) panel.append(element('p', `Trying key ${semitones > 0 ? '+' : ''}${semitones} (${tried} of ${total})`, 'stage key-stage'));
  panel.append(cancel);
  view.replaceChildren(element('h1', 'Results'), panel);
}

export function renderTooLong(view, stage, onCheckAgain) {
  const panel = element('div', '', 'results-status too-long', { role: 'status' });
  const actions = element('p', '', 'actions');
  actions.append(button('Try again', onCheckAgain, 'check-again primary'), recordAgainButton());
  panel.append(element('p', TOO_LONG_TEXT, 'stage'), element('p', `Last step: ${stage}.`, 'muted'), actions);
  view.replaceChildren(element('h1', 'Results'), panel);
}

// message: the back end's text. extra: optional element shown under it (the transposition control).
export function renderStopped(view, { heading, message, extra, primaryRecord = false }) {
  const panel = element('div', '', 'results-status stopped', { role: 'status' });
  panel.append(element('p', message, 'stopped-message'));
  if (extra) panel.append(extra);
  panel.append(recordAgainButton(primaryRecord));
  view.replaceChildren(element('h1', heading), panel);
}

// A request failed (the shell already showed the red banner): offer another try.
export function renderRequestFailed(view, onCheckAgain) {
  const panel = element('div', '', 'results-status');
  panel.append(element('p', 'The results could not be loaded.'), button('Try again', onCheckAgain, 'check-again primary'));
  view.replaceChildren(element('h1', 'Results'), panel);
}

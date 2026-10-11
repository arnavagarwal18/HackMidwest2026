// The screen's non-result states: working, slow, gave up, failed, can't tell.
import { button, element } from '../dom.js';

export const SLOW_TEXT = 'Still working - this can take a while for long takes';
export const TOO_LONG_TEXT = 'This is taking too long';

export function recordAgainButton() {
  return button('Record again', () => { window.location.hash = '#/take'; }, 'record-again');
}

export function renderWorking(view, stage, slow) {
  const panel = element('div', '', 'results-status', { role: 'status' });
  panel.append(element('p', `${stage}...`, 'stage'));
  if (slow) panel.append(element('p', SLOW_TEXT, 'muted slow-note'));
  view.replaceChildren(element('h1', 'Results'), panel);
}

// The automatic key search: 'Checking other keys… 3/12' with a Cancel button that puts the original key back.
export function renderKeySearch(view, { tried, total }, onCancel) {
  const panel = element('div', '', 'results-status key-search', { role: 'status' });
  const cancel = button('Cancel', () => { cancel.disabled = true; onCancel(); }, 'cancel-key-search');
  panel.append(element('p', `Checking other keys… ${tried}/${total}`, 'stage'), cancel);
  view.replaceChildren(element('h1', 'Results'), panel);
}

export function renderTooLong(view, stage, onCheckAgain) {
  const panel = element('div', '', 'results-status too-long', { role: 'status' });
  const actions = element('p', '', 'actions');
  actions.append(button('Check again', onCheckAgain, 'check-again'), recordAgainButton());
  panel.append(element('p', TOO_LONG_TEXT, 'stage'), element('p', `Last step: ${stage}.`, 'muted'), actions);
  view.replaceChildren(element('h1', 'Results'), panel);
}

// message: the back end's text. extra: optional element shown under it (the transposition control).
export function renderStopped(view, { heading, message, extra }) {
  const panel = element('div', '', 'results-status stopped', { role: 'status' });
  panel.append(element('p', message, 'stopped-message'));
  if (extra) panel.append(extra);
  panel.append(recordAgainButton());
  view.replaceChildren(element('h1', heading), panel);
}

// A request failed (the shell already showed the red banner): offer another try.
export function renderRequestFailed(view, onCheckAgain) {
  const panel = element('div', '', 'results-status');
  panel.append(element('p', 'The results could not be loaded.'), button('Check again', onCheckAgain, 'check-again'));
  view.replaceChildren(element('h1', 'Results'), panel);
}

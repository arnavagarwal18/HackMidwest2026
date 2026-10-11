// One row of the calibration screen: the prompt, a Record button and a status badge.
import { button, element } from '../dom.js';

export const ANOTHER_TRY = 'Needs another try';

// "Recorded" is good, a clip the server rejected needs attention; everything else (not yet, optional, recording now) is neutral.
export const statusBadgeClass = (text) => `badge badge-${text === 'Recorded' ? 'ok' : text === ANOTHER_TRY ? 'warn' : 'neutral'} calibrate-status`;

// Returns { element, button, setStatus(text) }.
export function createStepRow({ prompt, buttonLabel, onRecord }) {
  const status = element('span', '', '', { role: 'status' });
  const setStatus = (text) => { status.textContent = text; status.className = statusBadgeClass(text); };
  setStatus('Not recorded yet');
  const record = button(buttonLabel, onRecord, 'btn btn-secondary');
  const item = element('li', '', 'calibrate-step');
  item.append(element('span', prompt, 'calibrate-prompt'), record, status);
  return { element: item, button: record, setStatus };
}

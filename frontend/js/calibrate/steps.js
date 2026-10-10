// One row of the calibration screen: the prompt, a status line and a Record button.
import { button, element } from '../dom.js';

// Returns { element, button, setStatus(text) }.
export function createStepRow({ prompt, buttonLabel, onRecord }) {
  const status = element('span', 'Not recorded yet', 'muted calibrate-status', { role: 'status' });
  const record = button(buttonLabel, onRecord);
  const item = element('li', '', 'calibrate-step');
  item.append(element('span', prompt, 'calibrate-prompt'), record, status);
  return { element: item, button: record, setStatus: (text) => { status.textContent = text; } };
}

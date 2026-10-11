// One step of the calibration screen: the prompt, a Record button and a quiet status line.
import { button, element } from '../dom.js';

export const ANOTHER_TRY = 'Needs another try';
const PRIMARY_BUTTON = 'btn btn-primary primary';
const SECONDARY_BUTTON = 'btn btn-secondary';

// Only what needs the learner's eye is shown: a clip that is recorded, or one the server rejected, or a recording in progress.
const isQuiet = (text) => text === 'Not recorded yet' || text === 'Optional';

// The required steps carry the screen's one primary button; the optional instrument steps are secondary.
// Returns { element, button, setStatus(text) }.
export function createStepRow({ prompt, buttonLabel, onRecord, optional = false }) {
  const status = element('span', '', 'calibrate-status muted', { role: 'status' });
  const setStatus = (text) => {
    status.textContent = text;
    status.hidden = isQuiet(text);
    status.className = `calibrate-status ${text === ANOTHER_TRY ? 'is-warn' : 'muted'}`;
  };
  setStatus('Not recorded yet');
  const record = button(buttonLabel, onRecord, optional ? SECONDARY_BUTTON : PRIMARY_BUTTON);
  const item = element('li', '', 'calibrate-step');
  item.append(element('span', prompt, 'calibrate-prompt'), record, status);
  return { element: item, button: record, setStatus };
}

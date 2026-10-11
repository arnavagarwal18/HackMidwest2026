// The transposition control: a -12..12 select and 'Change transposition', which posts to
// POST /sessions/{id}/transposition and then asks the screen to check the take again.
import { reportError } from '../banner.js';
import { setTransposition } from '../api.js';
import { button, element } from '../dom.js';

export const TRANSPOSITION_RANGE = 12;

const optionLabel = (semitones) => (semitones > 0 ? `+${semitones}` : String(semitones));

// onChanged(semitones) runs after the back end accepted the change. primary: draw the button as the screen's main action.
export function renderTranspositionControl({ sessionId, current = 0, onChanged, primary = false }) {
  const wrapper = element('div', '', 'transposition');
  const select = element('select', '', '', { id: 'transposition-select', 'aria-label': 'Transposition in semitones' });
  for (let semitones = -TRANSPOSITION_RANGE; semitones <= TRANSPOSITION_RANGE; semitones += 1) {
    const option = element('option', optionLabel(semitones), '', { value: String(semitones) });
    option.selected = semitones === current;
    select.append(option);
  }
  const change = button('Change transposition', async () => {
    const semitones = Number(select.value);
    change.disabled = true;
    try {
      await setTransposition(sessionId, semitones);
    } catch (err) {
      reportError(err);
      change.disabled = false;
      return;
    }
    onChanged(semitones);
  }, primary ? 'primary' : '');
  wrapper.append(element('label', 'Transposition (semitones) ', '', { for: 'transposition-select' }), select, change);
  return wrapper;
}

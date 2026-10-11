// The Play screen's "What are you practicing?" picker: the session's persona preselected; a change is saved (PATCH) and presets
// the tempo field. deps: { personas, sessionId, writtenTempoBpm, savePersona, onTempo(bpm), reportError }.
// A failed save puts the control back on the stored persona, shows the error, and leaves the tempo alone.
import { element } from '../dom.js';
import { state } from '../state.js';
import { createSegmented } from './segmented.js';
import { PICKER_LABEL, findPersona, presetTempo } from './model.js';

export function createPersonaPicker(deps) {
  const { personas, sessionId, writtenTempoBpm, savePersona, onTempo, reportError } = deps;
  const heading = element('h2', PICKER_LABEL, 'persona-picker-label');
  const hint = element('p', '', 'muted persona-hint');
  const control = createSegmented({ label: PICKER_LABEL, options: personas, value: state.persona, onChange: choose });
  const root = element('div', '', 'persona-picker');
  let locked = false; // the Play screen locks its controls while a take is recorded or sent
  root.append(heading, control.element, hint);

  const showHint = () => { hint.textContent = findPersona(personas, state.persona)?.hint ?? ''; };

  async function choose(id) {
    const previous = state.persona;
    control.setDisabled(true);
    try {
      await savePersona(sessionId, id);
    } catch (err) {
      control.setValue(previous);
      reportError(err);
      return;
    } finally {
      control.setDisabled(locked);
      showHint();
    }
    const bpm = presetTempo(findPersona(personas, id), writtenTempoBpm);
    if (bpm !== null) onTempo(bpm);
  }

  showHint();
  return {
    element: root,
    lock(flag) {
      locked = flag;
      control.setDisabled(flag);
    },
  };
}

// The "Coach style" switch at the bottom of the Instructor chat panel. Choosing a style saves it (PATCH), builds the take's feedback
// again, and keeps the switch disabled until the new feedback record arrives.
// deps: { personas, sessionId, take, savePersona, rerunFeedback, onFeedback(body), onCoachChanged(label), reportError }.
// Returns { element, showMode(mode), enable(), setValue(id) }.
import { element } from '../dom.js';
import { state } from '../state.js';
import { createSegmented } from './segmented.js';
import { FALLBACK_COACH_TEXT, FEEDBACK_PENDING_TEXT, SWITCH_LABEL, personaLabel } from './model.js';

const isStillRunning = (err) => err?.status === 409;

export function createCoachSwitch(deps) {
  const { personas, sessionId, take, savePersona, rerunFeedback, onFeedback, onCoachChanged, reportError } = deps;
  const notice = element('p', FALLBACK_COACH_TEXT, 'notice fallback-notice coach-fallback', { role: 'status' });
  const message = element('p', FEEDBACK_PENDING_TEXT, 'coach-pending muted', { role: 'status' });
  notice.hidden = true;
  message.hidden = true;
  const heading = element('span', SWITCH_LABEL, 'coach-switch-label');
  const control = createSegmented({ label: SWITCH_LABEL, options: personas, value: state.persona, onChange: choose });
  const root = element('div', '', 'coach-switch');
  root.append(notice, message, heading, control.element);

  async function choose(id) {
    const previous = state.persona;
    control.setDisabled(true);
    message.hidden = true;
    try {
      await savePersona(sessionId, id);
    } catch (err) {
      control.setValue(previous); // nothing was saved, so nothing is re-run
      control.setDisabled(false);
      return reportError(err);
    }
    onCoachChanged(personaLabel(personas, id));
    try {
      onFeedback(await rerunFeedback(sessionId, take)); // the screen draws it and calls enable()
    } catch (err) {
      if (isStillRunning(err)) {
        message.hidden = false; // the switch stays disabled until a feedback record arrives
        return console.error('Feedback is still being made for this take; the coach style switch stays disabled.', err);
      }
      control.setDisabled(false);
      reportError(err);
    }
  }

  return {
    element: root,
    // The notice shows while the latest feedback or instructor turn came from the built-in fallback (no AI coach).
    showMode(mode) { notice.hidden = mode !== 'fallback'; },
    // A feedback record arrived (the screen drew it): the switch can be used again.
    enable() {
      message.hidden = true;
      control.setDisabled(false);
    },
    setValue: (id) => control.setValue(id),
  };
}

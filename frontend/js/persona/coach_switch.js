// The 'Coach: Standard ▾' menu in the header of the coach sheet. Choosing a style saves it (PATCH), builds the take's feedback
// again, and keeps the menu disabled until the new feedback record arrives.
// A 409 on the re-run (a run is already going) shows 'Feedback is still being made' and waits for the new record with waitForFeedback.
// deps: { personas, sessionId, take, savePersona, rerunFeedback, waitForFeedback(previousId), currentFeedbackId(), onFeedback(body),
//   onCoachChanged(label), reportError }.
// Returns { element (the menu), status (the notices, for the body of the sheet), showMode(mode), enable(), setValue(id) }.
import { element } from '../dom.js';
import { state } from '../state.js';
import { createMenu } from './menu.js';
import { SLOW_FEEDBACK_TEXT } from './pending_feedback.js';
import { FALLBACK_COACH_TEXT, FEEDBACK_PENDING_TEXT, STYLE_MENU_LABEL, SWITCH_LABEL, personaLabel } from './model.js';

const isStillRunning = (err) => err?.status === 409;

export function createCoachSwitch(deps) {
  const { personas, sessionId, take, savePersona, rerunFeedback, waitForFeedback, currentFeedbackId, onFeedback, onCoachChanged, reportError } = deps;
  const notice = element('p', FALLBACK_COACH_TEXT, 'notice coach-fallback', { role: 'status' });
  const message = element('p', FEEDBACK_PENDING_TEXT, 'coach-pending muted', { role: 'status' });
  notice.hidden = true;
  message.hidden = true;
  const control = createMenu({ label: SWITCH_LABEL, menuLabel: STYLE_MENU_LABEL, options: personas, value: state.persona, onChange: choose });
  const status = element('div', '', 'coach-switch-status');
  status.append(notice, message);
  const root = control.element;

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
    const shownId = currentFeedbackId();
    try {
      onFeedback(await rerunFeedback(sessionId, take)); // the screen draws it and calls enable()
    } catch (err) {
      if (!isStillRunning(err)) return giveBack(err);
      console.error('Feedback is still being made for this take; waiting for it.', err);
      await waitForNew(shownId);
    }
  }

  // The switch stays disabled while the running feedback is awaited; a record other than the one shown is drawn.
  async function waitForNew(shownId) {
    message.hidden = false;
    try {
      const body = await waitForFeedback(shownId);
      if (body) return onFeedback(body);
      giveBack(new Error(SLOW_FEEDBACK_TEXT));
    } catch (err) {
      giveBack(err);
    }
  }

  function giveBack(err) {
    message.hidden = true;
    control.setDisabled(false);
    reportError(err);
  }

  return {
    element: root,
    status,
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

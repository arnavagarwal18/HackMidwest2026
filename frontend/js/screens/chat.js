import { getChat, getFeedback, rerunFeedback, sendChat } from '../api.js';
import { reportError } from '../banner.js';
import { createChatPanel } from '../chat/panel.js';
import { savePersona } from '../persona/change.js';
import { createCoachSwitch } from '../persona/coach_switch.js';
import { waitForNewFeedback } from '../persona/pending_feedback.js';
import { loadPersonas } from '../persona/load.js';
import { state } from '../state.js';

// The Coach style switch for the panel, or nothing when the persona list is not available (the app then works as before).
function mountCoachSwitch(take, onFeedback) {
  return async (slot, { onCoachChanged }) => {
    const personas = await loadPersonas();
    if (!personas) return null;
    const sessionId = state.session_id ?? 'no-session';
    const coach = createCoachSwitch({
      personas,
      sessionId,
      take,
      savePersona,
      rerunFeedback,
      waitForFeedback: (previousId) => waitForNewFeedback({ getFeedback: () => getFeedback(sessionId, take), previousId }),
      currentFeedbackId: () => state.current_feedback_id,
      onFeedback,
      onCoachChanged,
      reportError,
    });
    slot.append(coach.element);
    return coach;
  };
}

// The Instructor chat panel. Not a route: results.js renders it beside the results by calling
// render(panelElement, { take, onFeedback }), and later calls setResults({ jumpContext, feedback }) on what render returns.
// onFeedback(body) gets the feedback (and plan) that a change of coach style built again; the results screen draws it.
export function render(root, { take, onFeedback }) {
  return createChatPanel(root, {
    sessionId: state.session_id ?? 'no-session',
    take,
    getChat,
    sendChat,
    reportError,
    mountCoachSwitch: mountCoachSwitch(take, onFeedback),
  });
}

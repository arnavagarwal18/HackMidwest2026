import { getChat, getFeedback, rerunFeedback, sendChat } from '../api.js';
import { reportError } from '../banner.js';
import { createChatPanel } from '../chat/panel.js';
import { savePersona } from '../persona/change.js';
import { createCoachSwitch } from '../persona/coach_switch.js';
import { waitForNewFeedback } from '../persona/pending_feedback.js';
import { loadPersonas } from '../persona/load.js';
import { state } from '../state.js';

// The Coach style menu for the sheet, or nothing when the persona list is not available (the app then works as before).
function mountCoachSwitch(take, onFeedback) {
  return async ({ menu, status }, { onCoachChanged }) => {
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
    menu.append(coach.element);
    status.append(coach.status);
    return coach;
  };
}

// The coach sheet. Not a route: results.js mounts it into its #coach-root by calling render(rootElement, { take, onFeedback }),
// and later calls setResults({ jumpContext, feedback }) on what render returns. The sheet opens on the document event 'coach:open'.
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

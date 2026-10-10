import { getChat, sendChat } from '../api.js';
import { reportError } from '../banner.js';
import { createChatPanel } from '../chat/panel.js';
import { state } from '../state.js';

// The Instructor chat panel. Not a route: results.js renders it beside the results by calling
// render(panelElement, { take }), and later calls setResults({ jumpContext, feedback }) on what render returns.
export function render(root, { take }) {
  return createChatPanel(root, {
    sessionId: state.session_id ?? 'no-session',
    take,
    getChat,
    sendChat,
    reportError,
  });
}

import { getAnalysis, getFeedback, getTracks } from '../api.js';
import { state } from '../state.js';
import { render as renderChat } from './chat.js';
import { renderPlaceholder } from './placeholder.js';

// Placeholder: the real screen replaces this body. render(root, params) is called by router.js.
// The Instructor chat panel sits beside the results; chat.js owns its own panel element.
export async function render(root, { take }) {
  const sid = state.session_id ?? 'no-session';
  const results = document.createElement('section');
  const chatPanel = document.createElement('aside');
  chatPanel.className = 'chat-panel';
  root.className = 'with-chat';
  root.append(results, chatPanel);
  await renderPlaceholder(results, {
    title: 'Results',
    description: 'What the app heard in this take.',
    calls: [
      { label: 'GET analysis', run: () => getAnalysis(sid, take) },
      { label: 'GET tracks', run: () => getTracks(sid, take) },
      { label: 'GET feedback', run: () => getFeedback(sid, take) },
    ],
  });
  await renderChat(chatPanel, { take });
}

import { getChat } from '../api.js';
import { state } from '../state.js';
import { renderPlaceholder } from './placeholder.js';

// Placeholder for the Instructor chat panel. Not a route: results.js renders it beside the results
// by calling render(panelElement, { take }).
export function render(root) {
  const sid = state.session_id ?? 'no-session';
  return renderPlaceholder(root, {
    title: 'Instructor',
    description: 'Ask the Instructor about this take.',
    calls: [{ label: 'GET chat', run: () => getChat(sid) }],
  });
}

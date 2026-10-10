import { state } from '../state.js';
import { renderPlaceholder } from './placeholder.js';

export function render(root) {
  const sid = encodeURIComponent(state.session_id ?? 'no-session');
  return renderPlaceholder(root, {
    title: 'Progress',
    description: 'How your takes are improving.',
    calls: [['GET', `/sessions/${sid}/progress`]],
  });
}

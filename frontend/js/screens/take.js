import { state } from '../state.js';
import { renderPlaceholder } from './placeholder.js';

export function render(root) {
  const sid = encodeURIComponent(state.session_id ?? 'no-session');
  return renderPlaceholder(root, {
    title: 'Take',
    description: 'Choose the bars and tempo, then record a take.',
    calls: [['GET', `/sessions/${sid}`]],
  });
}

import { state } from '../state.js';
import { renderPlaceholder } from './placeholder.js';

export function render(root, params) {
  const sid = encodeURIComponent(state.session_id ?? 'no-session');
  return renderPlaceholder(root, {
    title: 'Trace',
    description: 'How a feedback sentence was checked against the measurements.',
    calls: [['GET', `/sessions/${sid}/feedback/${params.fb}/trace`]],
  });
}

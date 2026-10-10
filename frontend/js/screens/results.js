import { state } from '../state.js';
import { renderPlaceholder } from './placeholder.js';

export function render(root, params) {
  const sid = encodeURIComponent(state.session_id ?? 'no-session');
  return renderPlaceholder(root, {
    title: 'Results',
    description: 'What the app heard in this take.',
    calls: [['GET', `/sessions/${sid}/takes/${params.take}/analysis`], ['GET', `/sessions/${sid}/takes/${params.take}/media`], ['GET', `/sessions/${sid}/takes/${params.take}/tracks`], ['GET', `/sessions/${sid}/takes/${params.take}/feedback`]],
  });
}

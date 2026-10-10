import { state } from '../state.js';
import { renderPlaceholder } from './placeholder.js';

export function render(root, params) {
  const sid = encodeURIComponent(state.session_id ?? 'no-session');
  return renderPlaceholder(root, {
    title: 'Exercise',
    description: 'A short drill for the weak spot.',
    calls: [['GET', `/sessions/${sid}/exercises/${params.ex}`], ['GET', `/sessions/${sid}/reps/rep_1`]],
  });
}

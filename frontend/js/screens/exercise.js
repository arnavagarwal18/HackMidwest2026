import { getExercise } from '../api.js';
import { state } from '../state.js';
import { renderPlaceholder } from './placeholder.js';

// Placeholder: the real screen replaces this body. render(root, params) is called by router.js.
export function render(root, { ex }) {
  const sid = state.session_id ?? 'no-session';
  return renderPlaceholder(root, {
    title: 'Exercise',
    description: 'Practise one exercise from your plan.',
    calls: [
      { label: 'GET exercise', run: () => getExercise(sid, ex) },
    ],
  });
}

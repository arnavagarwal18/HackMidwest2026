import { getTrace } from '../api.js';
import { state } from '../state.js';
import { renderPlaceholder } from './placeholder.js';

// Placeholder: the real screen replaces this body. render(root, params) is called by router.js.
export function render(root, { fb }) {
  const sid = state.session_id ?? 'no-session';
  return renderPlaceholder(root, {
    title: 'Trace',
    description: 'What the Instructor looked at and checked.',
    calls: [
      { label: 'GET trace', run: () => getTrace(sid, fb) },
    ],
  });
}

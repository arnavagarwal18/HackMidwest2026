import { getBuiltins, getScoreStatus } from '../api.js';
import { state } from '../state.js';
import { renderPlaceholder } from './placeholder.js';

// Placeholder: the real screen replaces this body. render(root, params) is called by router.js.
export function render(root) {
  const sid = state.session_id ?? 'no-session';
  return renderPlaceholder(root, {
    title: 'Score',
    description: 'Photograph or choose the piece, check the scan, then confirm it.',
    calls: [
      { label: 'GET score/status', run: () => getScoreStatus(sid) },
      { label: 'GET /builtins', run: () => getBuiltins('violin') },
    ],
  });
}

import { state } from '../state.js';
import { renderPlaceholder } from './placeholder.js';

export function render(root) {
  const sid = encodeURIComponent(state.session_id ?? 'no-session');
  return renderPlaceholder(root, {
    title: 'Score',
    description: 'Photograph or choose the piece, check the scan, then confirm it.',
    calls: [['GET', `/sessions/${sid}/score/status`], ['GET', '/builtins?instrument=violin']],
  });
}

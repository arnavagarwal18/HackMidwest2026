import { state } from '../state.js';
import { renderPlaceholder } from './placeholder.js';

export function render(root) {
  const sid = encodeURIComponent(state.session_id ?? 'no-session');
  return renderPlaceholder(root, {
    title: 'Start',
    description: 'Pick an instrument and begin a session.',
    calls: [['GET', '/builtins?instrument=violin'], ['GET', '/lan-address']],
  });
}

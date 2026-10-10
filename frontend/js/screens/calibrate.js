import { state } from '../state.js';
import { renderPlaceholder } from './placeholder.js';

export function render(root) {
  const sid = encodeURIComponent(state.session_id ?? 'no-session');
  return renderPlaceholder(root, {
    title: 'Calibrate',
    description: 'Play three reference notes and a click so the app can learn your room and your instrument.',
    calls: [['GET', '/reference-notes?instrument=violin'], ['GET', `/sessions/${sid}/calibration`]],
  });
}

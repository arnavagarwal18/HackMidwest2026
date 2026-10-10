import { getCalibration, getReferenceNotes } from '../api.js';
import { state } from '../state.js';
import { renderPlaceholder } from './placeholder.js';

// Placeholder: the real screen replaces this body. render(root, params) is called by router.js.
export function render(root) {
  const sid = state.session_id ?? 'no-session';
  return renderPlaceholder(root, {
    title: 'Calibrate',
    description: 'Play three reference notes and a click so the app can adjust to this room.',
    calls: [
      { label: 'GET /reference-notes', run: () => getReferenceNotes('violin') },
      { label: 'GET calibration', run: () => getCalibration(sid) },
    ],
  });
}

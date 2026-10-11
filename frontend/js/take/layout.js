// The look of the Play screen: the piece title, the Record area, and one closed "Options" disclosure for everything else.
// Only builds elements around the ones take.js already owns; no behaviour lives here.
import { pageHeader } from '../ui/components.js';
import { el } from '../score/ui.js';

// The piece title with a plain "Change piece" link under it.
export function playHeader(title) {
  const header = pageHeader({ title });
  header.classList.add('take-header');
  header.append(el('a', { text: 'Change piece', className: 'take-link', attrs: { href: '#/score' } }));
  return header;
}

// The Record button row, then what the take is doing (problem, level meter, status).
export function recordArea({ problem, micReason, actions, meterBox, status }) {
  return el('section', { className: 'take-record', children: [problem, actions, micReason, meterBox, status] });
}

// Closed by default: coach style, tempo, camera, bars, upload and Calibrate all live in here.
export function optionsDisclosure(children) {
  return el('details', { className: 'take-more', children: [el('summary', { text: 'Options' }), ...children] });
}

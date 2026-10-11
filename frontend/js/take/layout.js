// The look of the Play screen: a page header, a setup card, the record area and an upload card.
// Only builds elements around the ones take.js already owns; no behaviour lives here.
import { pageHeader } from '../ui/components.js';
import { el } from '../score/ui.js';

// card('Set up', [children]) -> <section class="card"> with a header and a body.
function card(title, children, className = '') {
  return el('section', { className: `card ${className}`.trim(), children: [
    el('div', { className: 'card-header', children: [el('h2', { text: title })] }),
    el('div', { className: 'card-body take-card-body', children }),
  ] });
}

// The piece title with the Change piece chip beside it.
export function playHeader(title) {
  const header = pageHeader({ title });
  header.append(el('div', { className: 'page-header-actions', children: [
    el('a', { text: 'Change piece', className: 'chip', attrs: { href: '#/score' } }),
  ] }));
  return header;
}

export function setupCard(children) {
  return card('Set up your take', children);
}

// The Record button row, then what the take is doing (problem, level meter, status).
export function recordArea({ problem, micReason, actions, meterBox, status }) {
  return el('section', { className: 'take-record', children: [problem, micReason, actions, meterBox, status] });
}

export function uploadCard(children) {
  return card('Other ways to add a take', children, 'take-upload');
}

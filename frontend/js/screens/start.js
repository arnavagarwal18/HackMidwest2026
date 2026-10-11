// Start: not a gate. With no session it opens one on the last-used built-in piece and goes straight to Play (#/take).
import { isRequestCancelled } from '../request_cancelled.js';
import { startOnDefaultPiece } from '../score/session.js';
import { button, el, loadScoreStyles } from '../score/ui.js';
import { card } from '../ui/card.js';
import { badge } from '../ui/components.js';
import { flowHeader } from '../ui/flow_header.js';

const WORKING_TEXT = 'Getting your piece ready...';

export function render(root, params, isCurrent = () => true) {
  loadScoreStyles();
  const status = el('div', { className: 'start-status muted', attrs: { role: 'status' } });
  const header = flowHeader({ title: 'Getting started', subtitle: 'Opening your last piece so you can play right away.', currentStep: 0 });
  root.append(el('section', { className: 'start', children: [header, card({ body: [status] })] }));

  async function begin() {
    status.className = 'start-status muted';
    status.replaceChildren(el('span', { className: 'spinner' }), WORKING_TEXT);
    try {
      await startOnDefaultPiece();
    } catch (err) {
      if (isRequestCancelled(err) || !isCurrent()) return console.info('Start cancelled by navigation.');
      console.error('Starting a session failed:', err);
      return showFailure(err);
    }
    if (isCurrent()) window.location.hash = '#/take';
  }

  function showFailure(err) {
    const message = err && err.message ? err.message : 'Something went wrong while getting your piece ready.';
    const retry = button('Try again', begin, 'btn btn-primary primary');
    const choose = el('a', { text: 'Choose a piece', className: 'btn btn-secondary', attrs: { href: '#/score' } });
    status.className = 'start-status';
    status.replaceChildren(
      badge("Couldn't start", 'error'),
      el('span', { text: message, className: 'scan-error' }),
      el('span', { className: 'start-actions', children: [retry, choose] }),
    );
  }

  return begin();
}

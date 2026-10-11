// Start: not a gate. With no session it opens one on the last-used built-in piece and goes straight to Play (#/take).
import { isRequestCancelled } from '../request_cancelled.js';
import { startOnDefaultPiece } from '../score/session.js';
import { button, el, loadScoreStyles } from '../score/ui.js';

const WORKING_TEXT = 'Getting your piece ready...';

export function render(root, params, isCurrent = () => true) {
  loadScoreStyles();
  const status = el('p', { className: 'start-status muted', attrs: { role: 'status' } });
  root.append(el('section', { className: 'start', children: [status] }));

  async function begin() {
    status.className = 'start-status muted';
    status.replaceChildren(WORKING_TEXT);
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
    const retry = button('Try again', begin, 'primary');
    const choose = el('a', { text: 'Choose a piece', attrs: { href: '#/score' } });
    status.className = 'start-status';
    status.replaceChildren(
      el('span', { text: message, className: 'scan-error' }),
      el('span', { className: 'start-actions', children: [retry, choose] }),
    );
  }

  return begin();
}

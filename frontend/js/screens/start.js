// Start: open a trumpet session and go to the score screen.
import { createSession } from '../api.js';
import { clearSession, setSession } from '../state.js';
import { button, el, loadScoreStyles, runGuarded } from '../score/ui.js';

const INSTRUMENT = 'trumpet'; // the app is trumpet only

export function render(root) {
  loadScoreStyles();
  const start = button('Start (trumpet)', () => startSession([start]), 'start-button');
  root.append(
    el('h1', { text: 'Trumpet practice' }),
    el('p', { text: 'Start a practice session to begin.', className: 'muted' }),
    el('p', { children: [start] }),
  );
}

async function startSession(controls) {
  const session = await runGuarded(controls, () => createSession(INSTRUMENT));
  if (!session) return;
  clearSession();
  setSession(session.session_id, session.instrument);
  window.location.hash = '#/score';
}

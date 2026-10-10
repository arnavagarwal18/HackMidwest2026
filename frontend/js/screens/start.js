// Start: pick an instrument, open a session, go to the score screen.
import { createSession } from '../api.js';
import { clearSession, setSession } from '../state.js';
import { button, el, loadScoreStyles, runGuarded } from '../score/ui.js';

const INSTRUMENTS = [
  { id: 'violin', label: 'Violin' },
  { id: 'trumpet', label: 'Trumpet' },
];

export function render(root) {
  loadScoreStyles();
  const choices = INSTRUMENTS.map(({ id, label }) => button(label, () => startSession(id, choices), 'instrument-choice'));
  root.append(
    el('h1', { text: 'What are you playing?' }),
    el('p', { text: 'Pick your instrument to begin a practice session.', className: 'muted' }),
    el('p', { className: 'instrument-choices', children: choices }),
  );
}

async function startSession(instrument, controls) {
  const session = await runGuarded(controls, () => createSession(instrument));
  if (!session) return;
  clearSession();
  setSession(session.session_id, session.instrument);
  window.location.hash = '#/score';
}

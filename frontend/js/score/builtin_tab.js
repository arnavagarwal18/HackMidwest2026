// Built-in tab: pick one of the pieces that ship with the app for this instrument, as plain rows (title, one quiet detail line, Play).
import { getBuiltins } from '../api.js';
import { reportError } from '../banner.js';
import { state } from '../state.js';
import { INSTRUMENT } from './session.js';
import { emptyState, skeleton } from '../ui/components.js';
import { button, el, runGuarded } from './ui.js';

// choose(piece) picks and confirms the piece; its errors reach the red banner through runGuarded.
export function createBuiltinTab({ choose }) {
  const list = el('ul', { className: 'builtin-list' });
  const root = el('div', { children: [list] });

  async function load() {
    list.replaceChildren(el('li', { attrs: { role: 'status', 'aria-label': 'Loading pieces' }, children: [skeleton(3)] }));
    try {
      const pieces = await getBuiltins(state.instrument ?? INSTRUMENT);
      list.replaceChildren(...(pieces.length ? pieces.map(pieceRow) : [el('li', { children: [emptyState('No built-in pieces', 'There are none for this instrument yet. Try a file or a photo.')] })]));
    } catch (err) {
      reportError(err);
      list.replaceChildren(el('li', { children: [emptyState("Couldn't load the pieces", 'Check your connection and try again.'), button('Try again', load, 'btn btn-secondary')] }));
    }
  }

  function pieceRow(piece) {
    const play = button('Play', () => runGuarded([play], () => choose(piece)), 'btn btn-ghost');
    const detail = [`${piece.bars} bars`, ...(piece.tempo_bpm ? [`${piece.tempo_bpm} bpm`] : [])].join(' · ');
    const text = el('div', { className: 'piece-text', children: [el('strong', { text: piece.title }), el('span', { text: detail, className: 'muted' })] });
    return el('li', { className: 'piece-row', children: [text, play] });
  }

  load();
  return root;
}

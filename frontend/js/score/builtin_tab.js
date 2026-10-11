// Built-in tab: pick one of the pieces that ship with the app for this instrument.
import { getBuiltins } from '../api.js';
import { reportError } from '../banner.js';
import { state } from '../state.js';
import { INSTRUMENT } from './session.js';
import { button, el, runGuarded } from './ui.js';

// choose(pieceId) picks and confirms the piece; its errors reach the red banner through runGuarded.
export function createBuiltinTab({ choose }) {
  const list = el('ul', { className: 'builtin-list' });
  const root = el('div', { children: [list] });

  async function load() {
    list.replaceChildren(el('li', { text: 'Loading pieces...', className: 'muted' }));
    try {
      const pieces = await getBuiltins(state.instrument ?? INSTRUMENT);
      list.replaceChildren(...pieces.map(pieceRow), ...(pieces.length ? [] : [el('li', { text: 'No built-in pieces for this instrument.' })]));
    } catch (err) {
      reportError(err);
      list.replaceChildren(el('li', { children: ["Couldn't load the pieces. ", button('Try again', load)] }));
    }
  }

  function pieceRow(piece) {
    const play = button('Play', () => runGuarded([play], () => choose(piece.piece_id)));
    return el('li', { children: [el('span', { text: `${piece.title} (${piece.bars} bars) ` }), play] });
  }

  load();
  return root;
}

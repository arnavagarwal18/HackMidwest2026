// Built-in tab: pick one of the pieces that ship with the app for this instrument.
import { chooseBuiltinScore, getBuiltins } from '../api.js';
import { reportError } from '../banner.js';
import { state } from '../state.js';
import { button, el, runGuarded } from './ui.js';

export function createBuiltinTab({ submit }) {
  const list = el('ul', { className: 'builtin-list' });
  const root = el('div', { children: [list] });

  async function load() {
    list.replaceChildren(el('li', { text: 'Loading pieces...', className: 'muted' }));
    try {
      const pieces = await getBuiltins(state.instrument);
      list.replaceChildren(...pieces.map(pieceRow), ...(pieces.length ? [] : [el('li', { text: 'No built-in pieces for this instrument.' })]));
    } catch (err) {
      reportError(err);
      list.replaceChildren(el('li', { children: ["Couldn't load the pieces. ", button('Try again', load)] }));
    }
  }

  function pieceRow(piece) {
    const choose = button('Use', () => runGuarded([choose], () => submit((sessionId) => chooseBuiltinScore(sessionId, piece.piece_id), 'builtin')));
    return el('li', { children: [el('span', { text: `${piece.title} (${piece.bars} bars) ` }), choose] });
  }

  load();
  return root;
}

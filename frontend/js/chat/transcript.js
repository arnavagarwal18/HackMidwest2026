// Draws chat turns. All server text goes in through textContent (via dom.js), never innerHTML.
import { button, element } from '../dom.js';
import { resolveJump } from '../results/measurements.js';
import { FALLBACK_NOTE, isFallback } from './model.js';

// One sentence. With a jump context its text is itself the tappable reference to the bar (once, no badge, no chips);
// without one (no results on screen, or a turn about another take) it is plain text.
function renderSentence(sentence, jumpContext) {
  const place = jumpContext ? resolveJump(sentence.jump, jumpContext.index) : null;
  const text = place
    ? button(sentence.text, () => jumpContext.jumper.jumpTo(place), 'sentence-text coach-link')
    : element('span', sentence.text, 'sentence-text');
  const item = element('li', '', 'sentence');
  item.append(text);
  return item;
}

function renderSentences(sentences, jumpContext) {
  const list = element('ul', '', 'sentences');
  sentences.forEach((sentence) => list.append(renderSentence(sentence, jumpContext)));
  return list;
}

// One turn as an <li>. jumpContextFor(turn) gives the jump context for that turn, or null.
export function renderTurn(turn, jumpContextFor) {
  const item = element('li', '', `chat-turn chat-${turn.role}`);
  item.append(element('span', turn.role === 'user' ? 'You' : 'Coach', 'chat-speaker'));
  if (isFallback(turn)) item.append(element('p', FALLBACK_NOTE, 'notice fallback-notice', { role: 'status' }));
  if (turn.role === 'instructor' && turn.sentences?.length) item.append(renderSentences(turn.sentences, jumpContextFor(turn)));
  else item.append(element('p', turn.text, 'chat-text'));
  return item;
}

export function renderTranscript(list, turns, jumpContextFor) {
  list.replaceChildren(...turns.map((turn) => renderTurn(turn, jumpContextFor)));
}

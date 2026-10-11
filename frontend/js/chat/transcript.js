// Draws chat turns. All server text goes in through textContent (via dom.js), never innerHTML.
import { element } from '../dom.js';
import { renderSentenceList } from '../results/sentences.js';
import { FALLBACK_NOTE, isFallback } from './model.js';

// The sentences of an instructor turn. With a jump context they get clickable text and bar/time chips like the
// feedback view; without one (no results on screen, or a turn about another take) they are plain text.
function renderSentences(sentences, jumpContext) {
  if (jumpContext) return renderSentenceList(sentences, jumpContext, { checkedBadge: true });
  const list = element('ul', '', 'sentences');
  sentences.forEach((sentence) => list.append(element('li', sentence.text, 'sentence')));
  return list;
}

// One turn as an <li>. jumpContextFor(turn) gives the jump context for that turn, or null.
export function renderTurn(turn, jumpContextFor) {
  if (turn.role === 'note') return element('li', turn.text, 'chat-note muted'); // a line the app adds, e.g. 'Now coaching: Concert'
  const item = element('li', '', `chat-turn chat-${turn.role}`);
  item.append(element('span', turn.role === 'user' ? 'You' : 'Instructor', 'chat-speaker'));
  if (isFallback(turn)) item.append(element('p', FALLBACK_NOTE, 'notice fallback-notice', { role: 'status' }));
  if (turn.role === 'instructor' && turn.sentences?.length) item.append(renderSentences(turn.sentences, jumpContextFor(turn)));
  else item.append(element('p', turn.text, 'chat-text'));
  return item;
}

export function renderTranscript(list, turns, jumpContextFor) {
  list.replaceChildren(...turns.map((turn) => renderTurn(turn, jumpContextFor)));
}

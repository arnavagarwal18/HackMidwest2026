// The first glance of the results: one word and one number for the take, Pitch / Rhythm / Tempo with the weakest one named,
// one suggestion, and the two buttons. Everything else is behind the rows in view.js.
import { OPEN_EVENT } from '../chat/panel.js';
import { button, element } from '../dom.js';
import { percent } from './scores.js';
import { overallShare, scoresOf, SCORE_NAMES, suggestionFor, verdictWord, weakestName } from './verdict.js';

export const WEAKEST_TEXT = 'Weakest';

// One small score: its name and percentage. The weakest also carries the word 'Weakest', so it never relies on colour alone.
function miniScore(name, score, isWeakest) {
  const item = element('li', '', `mini-score${isWeakest ? ' weakest' : ''}`);
  item.append(element('span', name, 'mini-label'), element('span', score ? percent(score.share) : '-', 'mini-value'));
  if (isWeakest) item.append(element('span', WEAKEST_TEXT, 'mini-flag'));
  return item;
}

// 'Ask coach' opens the coach sheet (js/chat/panel.js listens for the event); 'Try again' records the take again with the same settings.
function heroActions() {
  const actions = element('p', '', 'actions');
  const askCoach = button('Ask coach', () => document.dispatchEvent(new CustomEvent(OPEN_EVENT)), 'primary btn btn-primary');
  askCoach.id = 'ask-coach';
  actions.append(
    askCoach,
    button('Try again', () => { window.location.hash = '#/take'; }, 'try-again secondary btn'),
  );
  return actions;
}

export function renderHero(analysis) {
  const scores = scoresOf(analysis);
  const share = overallShare(scores);
  const weakest = weakestName(scores);
  const hero = element('section', '', 'hero');
  hero.append(element('h2', verdictWord(share), 'hero-word'));
  if (share !== null) hero.append(element('p', percent(share), 'hero-number'));
  const list = element('ul', '', 'mini-scores', { 'aria-label': 'Pitch, rhythm and tempo' });
  SCORE_NAMES.forEach((name) => list.append(miniScore(name, scores[name], name === weakest)));
  hero.append(list, element('p', suggestionFor(scores), 'suggestion'), heroActions());
  return hero;
}

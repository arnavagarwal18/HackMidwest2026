// The verdict under the recording: a headline naming the weakest area, Pitch / Rhythm / Tempo each with what it measures
// (the weakest marked "Focus here" in words), one suggestion, and the two buttons. The rest of the screen is in view.js.
import { OPEN_EVENT } from '../chat/panel.js';
import { button, element } from '../dom.js';
import { scoreMeasure, scoresOf, SCORE_NAMES, suggestionFor, verdictHeadline, weakestName } from './verdict.js';

export const FOCUS_TEXT = 'Focus here';

// One score: its name (with "Focus here" when it is the weakest, so the mark never relies on colour alone), its value and what that counts.
function scoreItem(name, score, isWeakest) {
  const { value, measure } = scoreMeasure(name, score);
  const item = element('li', '', `score-item${isWeakest ? ' is-focus' : ''}${score ? '' : ' not-measured'}`);
  const label = element('span', name, 'score-name');
  if (isWeakest) label.append(element('span', FOCUS_TEXT, 'focus-tag'));
  item.append(label, element('span', value, 'score-value'), element('span', measure, 'score-measure'));
  return item;
}

// 'Ask coach' opens the coach (js/chat/panel.js listens for the event); 'Try again' records the take again with the same settings.
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
  const weakest = weakestName(scores);
  const hero = element('section', '', 'hero', { 'aria-labelledby': 'verdict-title' });
  hero.append(element('h1', verdictHeadline(scores), 'verdict-title', { id: 'verdict-title' }));
  const list = element('ul', '', 'scores', { 'aria-label': 'Pitch, rhythm and tempo' });
  SCORE_NAMES.forEach((name) => list.append(scoreItem(name, scores[name], name === weakest)));
  hero.append(list, element('p', suggestionFor(scores), 'suggestion'), heroActions());
  return hero;
}

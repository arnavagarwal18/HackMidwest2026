// The plan's exercises, each a card with a 'Practice this' link to #/exercise/{id}, and the 'How the AI worked' link.
import { element, link } from '../dom.js';
import { state } from '../state.js';
import { badge, emptyState } from '../ui/components.js';

function exerciseCard(exercise) {
  const card = element('li', '', 'exercise card');
  const body = element('div', '', 'card-body');
  const bars = exercise.bar_from === exercise.bar_to ? `bar ${exercise.bar_from}` : `bars ${exercise.bar_from} to ${exercise.bar_to}`;
  const facts = element('p', '', 'exercise-facts');
  facts.append(badge(bars), badge(`${exercise.start_bpm} to ${exercise.target_bpm} bpm`));
  body.append(element('h3', exercise.title), element('p', exercise.text), facts);
  const footer = element('div', '', 'card-footer');
  const practise = link('Practice this', `#/exercise/${encodeURIComponent(exercise.id)}`, 'btn btn-primary');
  practise.addEventListener('click', () => { state.current_exercise_id = exercise.id; });
  footer.append(practise);
  card.append(body, footer);
  return card;
}

export function renderPlan(plan) {
  const section = element('section', '', 'plan', { id: 'plan' });
  section.append(element('h2', 'Your practice plan'));
  const exercises = plan?.exercises ?? [];
  if (!exercises.length) {
    section.append(emptyState('No exercises yet', 'No exercises were suggested for this take.'));
    return section;
  }
  const list = element('ul', '', 'exercises');
  exercises.forEach((exercise) => list.append(exerciseCard(exercise)));
  section.append(list);
  return section;
}

export function renderTraceLink(feedbackId) {
  return link('How the AI worked', `#/trace/${encodeURIComponent(feedbackId)}`, 'trace-link btn btn-ghost');
}

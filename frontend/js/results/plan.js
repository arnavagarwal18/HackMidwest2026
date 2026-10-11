// The plan's exercises, each with a Practice link to #/exercise/{id}, and the 'How the AI worked' link.
import { element, link } from '../dom.js';
import { state } from '../state.js';

function exerciseCard(exercise) {
  const card = element('li', '', 'exercise');
  card.append(element('h3', exercise.title), element('p', exercise.text));
  const bars = exercise.bar_from === exercise.bar_to ? `bar ${exercise.bar_from}` : `bars ${exercise.bar_from} to ${exercise.bar_to}`;
  card.append(element('p', `${bars}, from ${exercise.start_bpm} to ${exercise.target_bpm} bpm`, 'muted'));
  const practise = link('Practice', `#/exercise/${encodeURIComponent(exercise.id)}`, 'button-link');
  practise.addEventListener('click', () => { state.current_exercise_id = exercise.id; });
  card.append(practise);
  return card;
}

export function renderPlan(plan) {
  const section = element('section', '', 'plan', { id: 'plan' });
  section.append(element('h2', 'Your practice plan'));
  const exercises = plan?.exercises ?? [];
  if (!exercises.length) {
    section.append(element('p', 'No exercises were suggested for this take.', 'muted'));
    return section;
  }
  const list = element('ul', '', 'exercises');
  exercises.forEach((exercise) => list.append(exerciseCard(exercise)));
  section.append(list);
  return section;
}

export function renderTraceLink(feedbackId) {
  return link('How the AI worked', `#/trace/${encodeURIComponent(feedbackId)}`, 'trace-link');
}

// The plan's exercises, each a plain list item with a 'Practice this' link to #/exercise/{id}, and the 'How the AI worked' link.
import { element, link } from '../dom.js';
import { state } from '../state.js';
import { emptyState } from '../ui/components.js';

function exerciseItem(exercise) {
  const item = element('li', '', 'exercise');
  const bars = exercise.bar_from === exercise.bar_to ? `bar ${exercise.bar_from}` : `bars ${exercise.bar_from} to ${exercise.bar_to}`;
  const facts = element('p', `${bars}, ${exercise.start_bpm} to ${exercise.target_bpm} bpm`, 'exercise-facts muted');
  const practise = link('Practice this', `#/exercise/${encodeURIComponent(exercise.id)}`, 'btn');
  practise.addEventListener('click', () => { state.current_exercise_id = exercise.id; });
  item.append(element('h3', exercise.title), element('p', exercise.text), facts, practise);
  return item;
}

// heading: false when the caller already titles the plan (the results row).
export function renderPlan(plan, { heading = true } = {}) {
  const section = element('section', '', 'plan', { id: 'plan' });
  if (heading) section.append(element('h2', 'Your practice plan'));
  const exercises = plan?.exercises ?? [];
  if (!exercises.length) {
    section.append(emptyState('No exercises yet', 'No exercises were suggested for this take.'));
    return section;
  }
  const list = element('ul', '', 'exercises');
  exercises.forEach((exercise) => list.append(exerciseItem(exercise)));
  section.append(list);
  return section;
}

export function renderTraceLink(feedbackId) {
  return link('How the AI worked', `#/trace/${encodeURIComponent(feedbackId)}`, 'trace-link btn btn-ghost');
}

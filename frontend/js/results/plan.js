// The plan's exercises, each a plain list item with a 'Practice this' link to #/exercise/{id}; Practice next, the first few of them
// as numbered steps that can also go to their bar; and the 'How the AI worked' link.
import { button, element, link } from '../dom.js';
import { state } from '../state.js';
import { emptyState } from '../ui/components.js';

export const PRACTICE_NEXT_STEPS = 3;

const barsText = (exercise) => (exercise.bar_from === exercise.bar_to ? `bar ${exercise.bar_from}` : `bars ${exercise.bar_from} to ${exercise.bar_to}`);

// The 'Practice this' link, which also tells the trainer screen which exercise it opens.
function practiseLink(exercise) {
  const practise = link('Practice this', `#/exercise/${encodeURIComponent(exercise.id)}`, 'btn');
  practise.addEventListener('click', () => { state.current_exercise_id = exercise.id; });
  return practise;
}

function exerciseItem(exercise) {
  const item = element('li', '', 'exercise');
  const facts = element('p', `${barsText(exercise)}, ${exercise.start_bpm} to ${exercise.target_bpm} bpm`, 'exercise-facts muted');
  item.append(element('h3', exercise.title), element('p', exercise.text), facts, practiseLink(exercise));
  return item;
}

// One numbered step: the exercise, then 'Go to bar N' (when goToBar can show that bar) and 'Practice this'.
function practiceStep(exercise, goToBar) {
  const item = element('li', '', 'exercise practice-step');
  item.append(element('p', `${exercise.title}: ${exercise.text}`, 'step-text'));
  const actions = element('p', '', 'step-actions');
  if (goToBar.canShow(exercise.bar_from)) {
    actions.append(button(`Go to bar ${exercise.bar_from}`, () => goToBar.show(exercise.bar_from), 'go-to-bar btn btn-ghost'));
  }
  actions.append(practiseLink(exercise));
  item.append(actions);
  return item;
}

// Practice next: the plan's first PRACTICE_NEXT_STEPS exercises as steps; null when the plan has none.
// goToBar: { canShow(barNumber), show(barNumber) }.
export function renderPracticeNext(plan, goToBar) {
  const exercises = (plan?.exercises ?? []).slice(0, PRACTICE_NEXT_STEPS);
  if (!exercises.length) return null;
  const section = element('section', '', 'practice-next', { id: 'plan', 'aria-labelledby': 'practice-title' });
  const steps = element('ol', '', 'practice-steps');
  exercises.forEach((exercise) => steps.append(practiceStep(exercise, goToBar)));
  section.append(element('h2', 'Practice next', '', { id: 'practice-title' }), steps);
  return section;
}

// The whole plan, with its heading (the can't-tell screen shows it).
export function renderPlan(plan) {
  const section = element('section', '', 'plan', { id: 'plan' });
  section.append(element('h2', 'Your practice plan'));
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

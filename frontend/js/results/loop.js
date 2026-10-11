// "Loop this bar": which plan exercise opens for a bar, the tempo to start near, and the two buttons on a flagged bar.
// The back end cannot make an exercise for an arbitrary bar range or set its start tempo (it only serves the plan's exercises
// at GET .../exercises/{id}), so the plan exercise closest to the bar opens and the trainer screen shows the wanted bars and tempo as a hint.
import { button, element, link } from '../dom.js';
import { state } from '../state.js';

export const LOOP_TEMPO_SHARE = 0.75;

const covers = (exercise, bar) => exercise.bar_from <= bar && bar <= exercise.bar_to;
const distance = (exercise, bar) => (covers(exercise, bar) ? 0 : Math.min(Math.abs(exercise.bar_from - bar), Math.abs(exercise.bar_to - bar)));
const span = (exercise) => exercise.bar_to - exercise.bar_from;

// The plan exercise that covers the bar (the narrowest one), else the nearest one; null when the plan has none.
export function closestExercise(plan, bar) {
  const exercises = plan?.exercises ?? [];
  return [...exercises].sort((a, b) => distance(a, bar) - distance(b, bar) || span(a) - span(b))[0] ?? null;
}

// About 75% of the tempo the learner played at, as whole BPM; null when the take has no tempo.
export function loopStartBpm(analysis) {
  const played = analysis.tempo?.played_bpm;
  return typeof played === 'number' && played > 0 ? Math.round(played * LOOP_TEMPO_SHARE) : null;
}

export function loopHintText(request, exercise) {
  const parts = [`Looping bar ${request.bar} from your take.`];
  if (request.bpm) parts.push(`Aim to start near ${request.bpm} BPM, about ${Math.round(LOOP_TEMPO_SHARE * 100)}% of the tempo you played.`);
  if (!covers(exercise, request.bar)) parts.push(`Your plan has no exercise for bar ${request.bar}, so this is the closest one.`);
  return parts.join(' ');
}

// What the trainer screen should say about the loop it was opened from, once: null when it was opened some other way.
export function takeLoopRequest(exerciseId) {
  const request = state.loop_request;
  state.loop_request = null;
  return request?.exercise_id === exerciseId ? request : null;
}

// The two actions on a flagged bar. context: { plan, analysis }.
export function renderBarActions(bar, { plan, analysis }) {
  const actions = element('p', '', 'bar-actions');
  const exercise = closestExercise(plan, bar.bar);
  if (exercise) {
    const loop = link('Loop this bar', `#/exercise/${encodeURIComponent(exercise.id)}`, 'button-link loop-bar');
    loop.setAttribute('data-bar', String(bar.bar));
    loop.addEventListener('click', () => {
      state.current_exercise_id = exercise.id;
      state.loop_request = { exercise_id: exercise.id, bar: bar.bar, bpm: loopStartBpm(analysis) };
    });
    actions.append(loop);
  } else {
    actions.append(element('span', 'No loop exercise for this bar in your plan yet.', 'muted loop-missing'));
  }
  actions.append(button('Play again', () => { window.location.hash = '#/take'; }, 'play-again-bar secondary'));
  return actions;
}

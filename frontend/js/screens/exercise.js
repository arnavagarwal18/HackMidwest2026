import { getExercise, getRep, uploadRep } from '../api.js';
import { openStream, recordTake, stopStream } from '../record.js';
import { state } from '../state.js';
import { createTrainer } from '../exercise/trainer.js';
import { pollThresholds } from '../results/polling.js';
import { element } from '../dom.js';
import { loopHintText, takeLoopRequest } from '../results/loop.js';

const DEFAULT_BEATS_PER_BAR = 4;

// The rep settings: count-in is the take setup's, or one bar (the top number of the time signature) while none was chosen yet, as on the take screen.
export function repSettings(score, setup) {
  const beatsPerBar = score.time_signature?.[0] ?? DEFAULT_BEATS_PER_BAR;
  return { beatsPerBar, countInBeats: setup.count_in_beats ?? beatsPerBar, metronomeOn: setup.metronome_on };
}

// The loop trainer: see js/exercise/trainer.js. The count-in and metronome settings are the take setup's.
export async function render(root, { ex }) {
  const sessionId = state.session_id ?? 'no-session';
  state.current_exercise_id = ex;
  const setup = state.take_setup;
  const loopRequest = takeLoopRequest(ex);
  const hint = element('p', '', 'notice loop-hint', { role: 'status' });
  root.append(hint);
  const trainer = createTrainer(root, {
    sessionId,
    ex,
    ...repSettings(state.score, setup),
    thresholds: pollThresholds(),
    onFullTake: () => {
      // The take screen opens with the range the learner chose before; only fill it in when nothing was chosen.
      if (setup.bar_from === null) {
        const { exercise } = trainer.model;
        Object.assign(setup, { bar_from: exercise.bar_from, bar_to: exercise.bar_to });
      }
      window.location.hash = '#/take';
    },
  }, { getExercise, uploadRep, getRep, openStream, recordTake, stopStream });
  await trainer.start();
  if (loopRequest && trainer.model.exercise) hint.textContent = loopHintText(loopRequest, trainer.model.exercise);
  else hint.remove();
}

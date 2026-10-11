import { getExercise, getRep, uploadRep } from '../api.js';
import { openStream, recordTake, stopStream } from '../record.js';
import { state } from '../state.js';
import { createTrainer } from '../exercise/trainer.js';
import { pollThresholds } from '../results/polling.js';
import { element } from '../dom.js';
import { loopHintText, takeLoopRequest } from '../results/loop.js';

const DEFAULT_BEATS_PER_BAR = 4;

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
    beatsPerBar: state.score.time_signature?.[0] ?? DEFAULT_BEATS_PER_BAR,
    countInBeats: setup.count_in_beats,
    metronomeOn: setup.metronome_on,
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

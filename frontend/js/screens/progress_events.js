// The words of the progress timeline: a short label, a change against the first take and a plain-language explanation per event.

export const KIND_TAKE = 'take';
export const KIND_REP = 'rep';
export const KIND_EXERCISE_DONE = 'exercise_done';

const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;
const MINUS = '−';

const bpmText = (value) => `${Math.round(value)} bpm`;
const barsText = (event) => (event.bar_from === event.bar_to ? `bar ${event.bar_from}` : `bars ${event.bar_from} to ${event.bar_to}`);
const percentText = (rate) => `${Math.round(rate * 100)}%`;
const isPlayed = (event) => event.kind === KIND_TAKE || event.kind === KIND_REP;

export function takeNumbers(events) {
  let count = 0;
  return events.map((event) => (event.kind === KIND_TAKE ? (count += 1) : null));
}

export function eventLabel(event, takeNumber) {
  if (event.kind === KIND_EXERCISE_DONE) return `Completed: ${event.exercise_title ?? 'an exercise'}`;
  if (event.kind === KIND_REP) {
    return `Rep: ${event.exercise_title ?? 'Practice'} at ${bpmText(event.tempo_bpm)}, ${event.passed ? 'passed' : 'not passed'}`;
  }
  const tempo = event.played_bpm == null ? '' : `, ${bpmText(event.played_bpm)}`;
  return `Take ${takeNumber}: ${plural(event.errors, 'error')}${tempo}`;
}

// "−9 errors" against the first take; only when both cover the same bars, since error counts of different bars cannot be compared.
export function changeAgainstFirst(event, firstTake) {
  if (!isPlayed(event) || !firstTake || event === firstTake) return null;
  if (event.bar_from !== firstTake.bar_from || event.bar_to !== firstTake.bar_to) return null;
  const change = event.errors - firstTake.errors;
  if (change === 0) return { text: 'same errors', tone: 'neutral' };
  return { text: `${change < 0 ? MINUS : '+'}${plural(Math.abs(change), 'error')}`, tone: change < 0 ? 'ok' : 'error' };
}

export function eventTone(event) {
  if (event.kind === KIND_EXERCISE_DONE) return 'done';
  if (event.kind === KIND_REP) return event.passed ? 'rep-pass' : 'rep-fail';
  return 'take';
}

function playedSentences(event) {
  const sentences = [];
  const errors = event.errors === 0 ? 'No notes were wrong, missed or extra.'
    : `${plural(event.errors, 'note')} ${event.errors === 1 ? 'was' : 'were'} wrong, missed or extra`
      + `${event.error_rate == null ? '.' : ` (${percentText(event.error_rate)} of the notes).`}`;
  sentences.push(errors);
  if (event.played_bpm != null) sentences.push(`You played at about ${bpmText(event.played_bpm)}.`);
  if (event.clean_bpm != null) sentences.push(`Your clean tempo, the fastest you played without mistakes, was ${bpmText(event.clean_bpm)}.`);
  sentences.push(event.form_checked
    ? `The camera check found ${event.form_flags === 0 ? 'no form problems' : plural(event.form_flags, 'form problem')}.`
    : 'Your form was not checked (no camera).');
  return sentences;
}

export function eventDetails(event, firstTake) {
  if (event.kind === KIND_EXERCISE_DONE) {
    return [`You finished "${event.exercise_title ?? 'this exercise'}": you passed it at its target tempo.`];
  }
  const intro = event.kind === KIND_REP
    ? `A practice rep of "${event.exercise_title ?? 'an exercise'}" at ${bpmText(event.tempo_bpm)}, ${barsText(event)}. It ${event.passed ? 'passed' : 'did not pass'} the exercise's pass mark.`
    : `A take of ${barsText(event)}${event === firstTake ? ', your first one, the starting point for comparing' : ''}.`;
  const change = changeAgainstFirst(event, firstTake);
  const compare = change ? [`Compared with your first take: ${change.text}.`] : [];
  const reasons = event.kind === KIND_REP && !event.passed && event.reasons?.length ? [`Why: ${event.reasons.join('; ')}.`] : [];
  return [intro, ...playedSentences(event), ...reasons, ...compare];
}

export function timeText(event) {
  if (event.time == null) return '';
  return new Date(event.time * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

// First take against the latest one, and how many exercises are done; null when there is no take to summarise.
export function summarise(events, exercises) {
  const takes = events.filter((event) => event.kind === KIND_TAKE);
  const [first] = takes;
  const latest = takes.at(-1);
  const done = exercises.filter((exercise) => exercise.complete).length;
  return { first, latest, hasTwoTakes: takes.length > 1, exercisesDone: done, exerciseCount: exercises.length };
}

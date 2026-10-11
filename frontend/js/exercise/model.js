// Pure helpers for the loop trainer: wording, streak dots and how a rep result changes what is shown.
// No DOM and no API here, so node tests can run it.

export const PROCESSING = 'processing';
export const STILL_WORKING_TEXT = 'Still working - this can take a while';
export const TOO_LONG_TEXT = 'This is taking too long';
export const REP_MAX_SECONDS = 60;

function plural(count, word) {
  return `${count} ${word}${count === 1 ? '' : 's'}`;
}

// The pass mark in words, e.g. "No wrong or missed notes, average timing within 60 ms, and form rule: elbow height".
export function passMarkText(passMark) {
  const parts = [];
  parts.push(passMark.max_errors === 0 ? 'No wrong or missed notes' : `At most ${plural(passMark.max_errors, 'wrong or missed note')}`);
  if (passMark.max_mean_timing_ms != null) parts.push(`average timing within ${passMark.max_mean_timing_ms} ms`);
  if (passMark.form_rule) parts.push(`form rule: ${passMark.form_rule.replaceAll('_', ' ')}`);
  return parts.length > 1 ? `${parts.slice(0, -1).join(', ')} and ${parts.at(-1)}` : parts[0];
}

// A form rule is only checked on video, so the trainer records video when the exercise has one.
export function recordKind(exercise, hasVideo) {
  return exercise.pass_mark.form_rule && hasVideo ? 'video' : 'mic';
}

export function wantsVideo(exercise) {
  return Boolean(exercise.pass_mark.form_rule);
}

// One dot per rep needed: true = a pass in the streak.
export function streakDots(streak, repsToPass) {
  return Array.from({ length: repsToPass }, (_, index) => index < streak);
}

export const streakLabel = (streak, repsToPass) => `${streak} of ${repsToPass} passes in a row`;

// 'finished' when the back end has an answer for the rep (scored, not counted or failed).
export const repIsFinished = (rep) => rep.status !== PROCESSING;

// Passed or failed reps count towards the streak; anything else is a rep that did not count.
export const repWasScored = (rep) => rep.status === 'scored' && typeof rep.passed === 'boolean';

// The one plain line after a scored rep: the verdict in a word, then what happens to the tempo.
export function resultLine(previousBpm, exercise, rep) {
  if (rep.exercise_complete) return `Done — you passed ${exercise.target_bpm} BPM`;
  if (rep.passed) return rep.next_bpm > previousBpm ? `Pass — tempo up to ${rep.next_bpm}` : `Pass — staying at ${rep.next_bpm}`;
  return rep.next_bpm < previousBpm ? `Not yet — tempo down to ${rep.next_bpm}` : `Not yet — try again at ${rep.next_bpm}`;
}

// What the back end says about a rep that did not count; its own words first, a plain fallback only when it said nothing.
export function notCountedMessages(rep) {
  if (rep.reasons?.length) return rep.reasons;
  return [rep.status === 'failed' ? 'The rep could not be checked.' : 'The rep did not count.'];
}

// The exercise state after a rep result, so the screen is right before the next GET arrives.
export function stateAfterRep(exerciseState, rep) {
  if (!repWasScored(rep)) return exerciseState;
  return {
    ...exerciseState,
    current_bpm: rep.next_bpm,
    streak: rep.streak,
    complete: rep.exercise_complete,
    best_passed_bpm: rep.passed ? Math.max(rep.tempo_bpm, exerciseState.best_passed_bpm ?? 0) : exerciseState.best_passed_bpm,
  };
}

// The polling answer shape pollUntilDone expects: the rep plus done.
export const asPolled = (rep) => ({ ...rep, done: repIsFinished(rep) });

export const HISTORY_LIMIT = 8;

// The reps scored since the screen opened, newest first, as { tempo_bpm, passed }. Returns a new list.
export function historyAfterRep(history, rep) {
  if (!repWasScored(rep)) return history;
  return [{ tempo_bpm: rep.tempo_bpm, passed: rep.passed }, ...history].slice(0, HISTORY_LIMIT);
}

// The form checks of a rep in words, or null when the exercise has no form rule and nothing was flagged.
export function formFlagsText(exercise, rep) {
  const count = rep.form_flag_ids?.length ?? 0;
  if (count > 0) return `${plural(count, 'form flag')} raised`;
  return exercise.pass_mark.form_rule ? 'No form flags' : null;
}

export const repFactsText = (rep) => ({
  errors: typeof rep.errors === 'number' ? { value: String(rep.errors), label: rep.errors === 1 ? 'Wrong or missed note' : 'Wrong or missed notes' } : null,
  timing: typeof rep.mean_abs_timing_ms === 'number' ? { value: `${Math.round(rep.mean_abs_timing_ms)} ms`, label: 'Average timing' } : null,
});

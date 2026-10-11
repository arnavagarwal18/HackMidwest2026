// Pure helpers for the loop trainer: wording, the tempo ladder, streak dots and how a rep result changes what is shown.
// No DOM and no API here, so node tests can run it.

export const PROCESSING = 'processing';
export const STILL_WORKING_TEXT = 'Still working - this can take a while';
export const TOO_LONG_TEXT = 'This is taking too long';
export const REP_MAX_SECONDS = 60;

export function barsText(exercise) {
  return exercise.bar_from === exercise.bar_to ? `bar ${exercise.bar_from}` : `bars ${exercise.bar_from} to ${exercise.bar_to}`;
}

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

// The tempos from start to target in steps of step_bpm; the last one is always the target.
export function ladderSteps({ start_bpm: start, target_bpm: target, step_bpm: step }) {
  const steps = [];
  for (let bpm = start; bpm < target; bpm += step) steps.push(bpm);
  steps.push(target);
  return steps;
}

// Each ladder step as { bpm, status } with status 'passed' (at or below the best passed tempo), 'current' or 'todo'.
export function ladderView(exercise, exerciseState) {
  const steps = ladderSteps(exercise);
  const current = steps.reduce((best, bpm) => (Math.abs(bpm - exerciseState.current_bpm) < Math.abs(best - exerciseState.current_bpm) ? bpm : best), steps[0]);
  const best = exerciseState.best_passed_bpm;
  return steps.map((bpm) => {
    let status = 'todo';
    if (best != null && bpm <= best) status = 'passed';
    else if (bpm === current && !exerciseState.complete) status = 'current';
    return { bpm, status };
  });
}

// How far the current tempo is from start to target, as a whole percentage (0 to 100), for the tempo dial.
export function tempoProgressPercent({ start_bpm: start, target_bpm: target }, exerciseState) {
  if (target <= start) return 100;
  const fraction = (exerciseState.current_bpm - start) / (target - start);
  return Math.round(Math.min(1, Math.max(0, fraction)) * 100);
}

// One dot per rep needed: true = a pass in the streak.
export function streakDots(streak, repsToPass) {
  return Array.from({ length: repsToPass }, (_, index) => index < streak);
}

export const streakLabel = (streak, repsToPass) => `${streak} of ${repsToPass} passes in a row`;

export const nextRepText = (bpm) => `Next rep at ${bpm} BPM - press space`;

// 'finished' when the back end has an answer for the rep (scored, not counted or failed).
export const repIsFinished = (rep) => rep.status !== PROCESSING;

// Passed or failed reps count towards the streak; anything else is a rep that did not count.
export const repWasScored = (rep) => rep.status === 'scored' && typeof rep.passed === 'boolean';

export function tempoChangeText(previousBpm, rep) {
  if (rep.next_bpm > previousBpm) return `Tempo up: ${previousBpm} to ${rep.next_bpm} BPM`;
  if (rep.next_bpm < previousBpm) return `Tempo down: ${previousBpm} to ${rep.next_bpm} BPM`;
  return `Staying at ${rep.next_bpm} BPM`;
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

export const firstRepText = (bpm) => `Rep at ${bpm} BPM - press space`;

export const HISTORY_LIMIT = 8;

// The reps scored since the screen opened, newest first, as { tempo_bpm, passed }. Returns a new list.
export function historyAfterRep(history, rep) {
  if (!repWasScored(rep)) return history;
  return [{ tempo_bpm: rep.tempo_bpm, passed: rep.passed }, ...history].slice(0, HISTORY_LIMIT);
}

// The form checks of a rep in words, or null when the exercise has no form rule and nothing was flagged.
export function formFlagsText(exercise, rep) {
  const count = rep.form_flag_ids?.length ?? 0;
  if (count > 0) return { tone: 'warn', text: `${plural(count, 'form flag')} raised` };
  return exercise.pass_mark.form_rule ? { tone: 'ok', text: 'No form flags' } : null;
}

export const repFactsText = (rep) => ({
  errors: typeof rep.errors === 'number' ? { value: String(rep.errors), label: rep.errors === 1 ? 'Wrong or missed note' : 'Wrong or missed notes' } : null,
  timing: typeof rep.mean_abs_timing_ms === 'number' ? { value: `${Math.round(rep.mean_abs_timing_ms)} ms`, label: 'Average timing' } : null,
});

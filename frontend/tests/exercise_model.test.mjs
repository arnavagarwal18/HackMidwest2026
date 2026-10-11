// Run: node --test frontend/tests/exercise_model.test.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { mockFileFor } from '../js/mock.js';
import {
  HISTORY_LIMIT, barsText, formFlagsText, historyAfterRep, ladderSteps, ladderView, nextRepText, notCountedMessages, passMarkText, recordKind, repFactsText, stateAfterRep,
  streakDots, tempoChangeText, wantsVideo,
} from '../js/exercise/model.js';

const exercise = { bar_from: 3, bar_to: 4, start_bpm: 60, target_bpm: 96, step_bpm: 6, reps_to_pass: 3, pass_mark: { max_errors: 0, max_mean_timing_ms: 60, form_rule: null } };
const mockJson = (name) => JSON.parse(readFileSync(new URL(`../mock/${name}.json`, import.meta.url)));

test('bars and pass mark are put in words', () => {
  assert.equal(barsText(exercise), 'bars 3 to 4');
  assert.equal(barsText({ bar_from: 5, bar_to: 5 }), 'bar 5');
  assert.equal(passMarkText(exercise.pass_mark), 'No wrong or missed notes and average timing within 60 ms');
  assert.equal(passMarkText({ max_errors: 2, max_mean_timing_ms: null, form_rule: null }), 'At most 2 wrong or missed notes');
  assert.equal(passMarkText({ max_errors: 1, max_mean_timing_ms: 50, form_rule: 'elbow_height' }),
    'At most 1 wrong or missed note, average timing within 50 ms and form rule: elbow height');
});

test('the tempo ladder runs from start to target and always ends on the target', () => {
  assert.deepEqual(ladderSteps(exercise), [60, 66, 72, 78, 84, 90, 96]);
  assert.deepEqual(ladderSteps({ start_bpm: 60, target_bpm: 70, step_bpm: 8 }), [60, 68, 70]);
});

test('ladder marks passed steps and the current one', () => {
  const view = ladderView(exercise, { current_bpm: 72, best_passed_bpm: 66, complete: false });
  assert.deepEqual(view.map((s) => s.status), ['passed', 'passed', 'current', 'todo', 'todo', 'todo', 'todo']);
  const none = ladderView(exercise, { current_bpm: 60, best_passed_bpm: null, complete: false });
  assert.equal(none[0].status, 'current');
  const done = ladderView(exercise, { current_bpm: 96, best_passed_bpm: 96, complete: true });
  assert.ok(done.every((s) => s.status === 'passed'));
});

test('streak dots: one per rep needed, filled for each pass', () => {
  assert.deepEqual(streakDots(1, 3), [true, false, false]);
  assert.deepEqual(streakDots(0, 2), [false, false]);
});

test('video is wanted only when the exercise has a form rule, and a failed camera records the sound only', () => {
  const withRule = { pass_mark: { max_errors: 0, form_rule: 'elbow_height' } };
  assert.equal(wantsVideo(exercise), false);
  assert.equal(wantsVideo(withRule), true);
  assert.equal(recordKind(withRule, true), 'video');
  assert.equal(recordKind(withRule, false), 'mic');
  assert.equal(recordKind(exercise, true), 'mic');
});

test('tempo change and next rep wording', () => {
  assert.equal(nextRepText(64), 'Next rep at 64 BPM - press space');
  assert.equal(tempoChangeText(60, { next_bpm: 66 }), 'Tempo up: 60 to 66 BPM');
  assert.equal(tempoChangeText(66, { next_bpm: 60 }), 'Tempo down: 66 to 60 BPM');
  assert.equal(tempoChangeText(66, { next_bpm: 66 }), 'Staying at 66 BPM');
});

test('a rep that did not count shows the back end words, with a plain fallback', () => {
  assert.deepEqual(notCountedMessages({ status: 'not_counted', reasons: ['No notes were heard'] }), ['No notes were heard']);
  assert.deepEqual(notCountedMessages({ status: 'failed', reasons: [] }), ['The rep could not be checked.']);
});

test('a scored rep updates the exercise state; a rep that did not count leaves it alone', () => {
  const before = { current_bpm: 60, streak: 2, best_passed_bpm: null, complete: false };
  const after = stateAfterRep(before, { status: 'scored', passed: true, tempo_bpm: 60, next_bpm: 66, streak: 0, exercise_complete: false });
  assert.deepEqual(after, { current_bpm: 66, streak: 0, best_passed_bpm: 60, complete: false });
  assert.equal(stateAfterRep(before, { status: 'not_counted', passed: null }), before);
});

test('mock rep variants: processing first, then the variant for that exercise id', () => {
  const finalFile = (ex) => {
    const path = `/sessions/s/exercises/${ex}/reps/rep_1`;
    assert.equal(mockFileFor('POST', `/sessions/s/exercises/${ex}/reps`), 'post_exercise_reps');
    assert.equal(mockFileFor('GET', path), 'get_rep_processing');
    return mockFileFor('GET', path);
  };
  assert.equal(finalFile('ex1'), 'get_rep');
  assert.equal(finalFile('ex_fail'), 'get_rep_fail');
  assert.equal(finalFile('ex_not_counted'), 'get_rep_not_counted');
  assert.equal(finalFile('ex_complete'), 'get_rep_complete');
  assert.equal(mockFileFor('GET', '/sessions/s/exercises/ex_complete'), 'get_exercise_last_rep');
  assert.equal(mockFileFor('GET', '/sessions/s/exercises/ex_done'), 'get_exercise_done');
  assert.equal(mockFileFor('GET', '/sessions/s/exercises/ex_video'), 'get_exercise_video');
});

test('mock rep files carry every RepResult field and mean what their name says', () => {
  const keys = ['take_id', 'exercise_id', 'tempo_bpm', 'status', 'passed', 'reasons', 'errors', 'mean_abs_timing_ms', 'form_flag_ids', 'next_bpm', 'streak', 'exercise_complete'];
  for (const name of ['get_rep', 'get_rep_fail', 'get_rep_not_counted', 'get_rep_complete']) {
    assert.deepEqual(Object.keys(mockJson(name)).sort(), [...keys].sort(), name);
  }
  assert.equal(mockJson('get_rep').passed, true);
  assert.equal(mockJson('get_rep_fail').passed, false);
  assert.ok(mockJson('get_rep_fail').reasons.length >= 1);
  assert.equal(mockJson('get_rep_not_counted').status, 'not_counted');
  assert.equal(mockJson('get_rep_complete').exercise_complete, true);
  assert.equal(mockJson('get_exercise_done').state.complete, true);
  assert.equal(mockJson('get_exercise_video').exercise.pass_mark.form_rule, 'elbow_height');
});

test('historyAfterRep keeps scored reps newest first, ignores reps that did not count and caps the list', () => {
  let history = [];
  history = historyAfterRep(history, { status: 'scored', passed: true, tempo_bpm: 60 });
  history = historyAfterRep(history, { status: 'scored', passed: false, tempo_bpm: 66 });
  assert.deepEqual(history, [{ tempo_bpm: 66, passed: false }, { tempo_bpm: 60, passed: true }]);
  assert.equal(historyAfterRep(history, { status: 'not_counted', passed: null, tempo_bpm: 66 }), history);
  for (let i = 0; i < HISTORY_LIMIT + 3; i += 1) history = historyAfterRep(history, { status: 'scored', passed: true, tempo_bpm: 70 + i });
  assert.equal(history.length, HISTORY_LIMIT);
  assert.equal(history[0].tempo_bpm, 70 + HISTORY_LIMIT + 2);
});

test('formFlagsText and repFactsText put a rep result into words', () => {
  const plain = { pass_mark: { form_rule: null } };
  const withRule = { pass_mark: { form_rule: 'elbow_height' } };
  assert.equal(formFlagsText(plain, { form_flag_ids: [] }), null);
  assert.deepEqual(formFlagsText(withRule, { form_flag_ids: [] }), { tone: 'ok', text: 'No form flags' });
  assert.deepEqual(formFlagsText(plain, { form_flag_ids: ['a'] }), { tone: 'warn', text: '1 form flag raised' });
  assert.deepEqual(formFlagsText(withRule, { form_flag_ids: ['a', 'b'] }), { tone: 'warn', text: '2 form flags raised' });
  assert.deepEqual(repFactsText({ errors: 1, mean_abs_timing_ms: 71.6 }), {
    errors: { value: '1', label: 'Wrong or missed note' }, timing: { value: '72 ms', label: 'Average timing' },
  });
  assert.deepEqual(repFactsText({}), { errors: null, timing: null });
});

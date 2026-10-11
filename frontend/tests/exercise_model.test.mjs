// Run: node --test frontend/tests/exercise_model.test.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { mockFileFor } from '../js/mock.js';
import {
  HISTORY_LIMIT, formFlagsText, historyAfterRep, notCountedMessages, passMarkText, recordKind, repFactsText, resultLine, stateAfterRep,
  streakDots, wantsVideo,
} from '../js/exercise/model.js';

const exercise = { bar_from: 3, bar_to: 4, start_bpm: 60, target_bpm: 96, step_bpm: 6, reps_to_pass: 3, pass_mark: { max_errors: 0, max_mean_timing_ms: 60, form_rule: null } };
const mockJson = (name) => JSON.parse(readFileSync(new URL(`../mock/${name}.json`, import.meta.url)));

test('the pass mark is put in words', () => {
  assert.equal(passMarkText(exercise.pass_mark), 'No wrong or missed notes and average timing within 60 ms');
  assert.equal(passMarkText({ max_errors: 2, max_mean_timing_ms: null, form_rule: null }), 'At most 2 wrong or missed notes');
  assert.equal(passMarkText({ max_errors: 1, max_mean_timing_ms: 50, form_rule: 'elbow_height' }),
    'At most 1 wrong or missed note, average timing within 50 ms and form rule: elbow height');
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

test('the result line says the verdict in a word and what happens to the tempo', () => {
  assert.equal(resultLine(60, exercise, { passed: true, next_bpm: 66 }), 'Pass — tempo up to 66');
  assert.equal(resultLine(60, exercise, { passed: true, next_bpm: 60 }), 'Pass — staying at 60');
  assert.equal(resultLine(66, exercise, { passed: false, next_bpm: 60 }), 'Not yet — tempo down to 60');
  assert.equal(resultLine(66, exercise, { passed: false, next_bpm: 66 }), 'Not yet — try again at 66');
  assert.equal(resultLine(96, exercise, { passed: true, next_bpm: 96, exercise_complete: true }), 'Done — you passed 96 BPM');
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
  assert.equal(formFlagsText(withRule, { form_flag_ids: [] }), 'No form flags');
  assert.equal(formFlagsText(plain, { form_flag_ids: ['a'] }), '1 form flag raised');
  assert.equal(formFlagsText(withRule, { form_flag_ids: ['a', 'b'] }), '2 form flags raised');
  assert.deepEqual(repFactsText({ errors: 1, mean_abs_timing_ms: 71.6 }), {
    errors: { value: '1', label: 'Wrong or missed note' }, timing: { value: '72 ms', label: 'Average timing' },
  });
  assert.deepEqual(repFactsText({}), { errors: null, timing: null });
});

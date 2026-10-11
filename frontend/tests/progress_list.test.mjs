// The progress screen: one plain list of exercises, each a title and one quiet status line. Run: node --test frontend/tests/progress_list.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { FakeNode, installFakeBrowser } from './fake_env.mjs';

const env = installFakeBrowser({ search: '' });
env.restore();
const { renderProgress, statusText } = await import('../js/screens/progress.js');

const exercise = (extra) => ({ id: 'ex1', title: 'Bar 3 slow', start_bpm: 60, target_bpm: 96, best_passed_bpm: 72, complete: false, reps: 4, passes: 2, ...extra });
const classes = (node) => node.className.split(' ');

test('the status line is "72 of 96 BPM", "Not started yet" or "Done"', () => {
  assert.equal(statusText(exercise()), '72 of 96 BPM');
  assert.equal(statusText(exercise({ best_passed_bpm: null })), 'Not started yet');
  assert.equal(statusText(exercise({ best_passed_bpm: 96, complete: true })), 'Done');
});

test('each exercise is one row: a link to its trainer, the title and one status line', () => {
  const root = new FakeNode('main');
  renderProgress(root, { before: null, after: null, exercises: [exercise(), exercise({ id: 'ex 2', title: 'Bar 5', best_passed_bpm: 96, complete: true })] });
  const rows = root.find((node) => classes(node).includes('exercise-item'));
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map((row) => row.find((node) => classes(node).includes('exercise-status'))[0].textContent), ['72 of 96 BPM', 'Done']);
  assert.deepEqual(rows.map((row) => row.find((node) => classes(node).includes('exercise-title'))[0].textContent), ['Bar 3 slow', 'Bar 5']);
  assert.equal(rows[1].find((node) => node.tagName === 'a')[0].attrs.href, '#/exercise/ex%202');
  assert.equal(root.find((node) => ['card', 'badge'].some((name) => classes(node).includes(name))).length, 0);
});

test('the before and after comparison stays behind a disclosure under the list', () => {
  const snapshot = { source: 'take', bar_from: 1, bar_to: 2, errors: 0, error_rate: 0, played_bpm: 80, clean_bpm: 80, form_flags: 0, form_checked: false };
  const makeElement = document.createElement;
  document.createElement = (tag) => {
    const node = makeElement(tag);
    const section = () => Object.assign(new FakeNode('tbody'), { insertRow: () => { const row = new FakeNode('tr'); node.append(row); return row; } });
    return Object.assign(node, { createTHead: section, createTBody: section });
  };
  const root = new FakeNode('main');
  renderProgress(root, { before: snapshot, after: null, exercises: [exercise()] });
  document.createElement = makeElement;
  const details = root.find((node) => node.tagName === 'details');
  assert.equal(details.length, 1);
  assert.equal(details[0].children[0].textContent, 'Before and after');
  assert.ok(details[0].find((node) => node.tagName === 'table').length === 1);
});

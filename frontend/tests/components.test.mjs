// Node tests for the DOM builders in js/ui/components.js (the CSS itself is checked by eye: see frontend/dev/screens/).
import assert from 'node:assert/strict';
import test from 'node:test';
import { installFakeDom } from './fake_dom.mjs';

installFakeDom();
const { badge, emptyState, pageHeader, skeleton, stat } = await import('../js/ui/components.js');

test('badge uses the tone class and rejects an unknown tone', () => {
  const node = badge('Complete', 'ok');
  assert.equal(node.className, 'badge badge-ok');
  assert.equal(node.textContent, 'Complete');
  assert.equal(badge('Draft').className, 'badge badge-neutral');
  assert.throws(() => badge('x', 'purple'), /Unknown badge tone "purple"/);
});

test('stat holds a value and a label, with an optional tone', () => {
  const node = stat(87, 'In tune', 'ok');
  assert.equal(node.className, 'stat stat-ok');
  assert.deepEqual(node.texts('stat-value'), ['87']);
  assert.deepEqual(node.texts('stat-label'), ['In tune']);
  assert.equal(stat('3', 'Takes').className, 'stat');
  assert.throws(() => stat(1, 'x', 'loud'), /Unknown stat tone/);
});

test('emptyState shows the title and, when given, the help line', () => {
  assert.deepEqual(emptyState('Nothing yet', 'Play a piece.').all().map((n) => n.textContent), ['Nothing yet', 'Play a piece.']);
  assert.equal(emptyState('Nothing yet').all().length, 1);
});

test('skeleton makes the asked number of lines', () => {
  assert.equal(skeleton(4).withClass('skeleton').length, 4);
});

test('pageHeader marks the current step and the done ones', () => {
  const node = pageHeader({ title: 'Play', subtitle: 'Pick a piece', steps: ['Choose', 'Play', 'Review'], currentStep: 1 });
  assert.deepEqual(node.texts('page-title'), ['Play']);
  assert.deepEqual(node.texts('page-subtitle'), ['Pick a piece']);
  const items = node.all().filter((n) => n.tagName === 'LI');
  assert.deepEqual(items.map((n) => n.className), ['is-done', '', '']);
  assert.deepEqual(items.map((n) => n.attributes['aria-current']), [undefined, 'step', undefined]);
});

test('pageHeader without steps has no step list, and a bad step fails loudly', () => {
  assert.equal(pageHeader({ title: 'Progress' }).withClass('steps').length, 0);
  assert.throws(() => pageHeader({ title: 'x', steps: ['a'], currentStep: 3 }), /outside the 1 steps/);
});

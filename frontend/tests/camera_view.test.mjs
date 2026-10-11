// Node tests for the front / side camera view: picker, outline, badge, and the side-only overlay.
// Run: node --test frontend/tests/camera_view.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';

import { FakeNode, installFakeBrowser } from './fake_env.mjs';

const env = installFakeBrowser({ search: '' });
env.restore();
const stored = {};
window.localStorage = { getItem: (key) => stored[key] ?? null, setItem: (key, value) => { stored[key] = value; } };
const makeSvgNode = document.createElementNS;
document.createElementNS = (ns, tag) => Object.assign(makeSvgNode(ns, tag), { dataset: {} });

const { describeCameraCheck, IN_FRAME_TEXT } = await import('../js/take/camera_status.js');
const { createCameraGuide } = await import('../js/take/camera_guide.js');
const { createCameraPanel } = await import('../js/take/camera_panel.js');
const { DEFAULT_VIEW, SIDE_NOTE, loadView, saveView, nearSideOf } = await import('../js/take/camera_view.js');
const { detectNearSide, isNearLine, isNearPoint } = await import('../js/results/overlay/side_view.js');
const { drawOverlay, POSE_LINES } = await import('../js/results/overlay/draw.js');

const answer = (over) => ({ ok: false, missing: [], too_small: false, too_dark: false, ...over });

test('view helpers: default, near side, remembered choice', () => {
  assert.equal(DEFAULT_VIEW, 'front');
  assert.equal(nearSideOf('front'), null);
  assert.equal(nearSideOf('side-left'), 'left');
  assert.equal(nearSideOf('side-right'), 'right');
  assert.equal(loadView(), 'front');
  saveView('side-right');
  assert.equal(loadView(), 'side-right');
  stored.practice_coach_camera_view = 'upside-down';
  assert.equal(loadView(), 'front', 'an unknown stored value falls back to front');
  delete stored.practice_coach_camera_view;
});

test('front badge text is unchanged by the view argument being absent or front', () => {
  const missing = answer({ missing: ['left ear', 'hips'], too_small: true });
  assert.deepEqual(describeCameraCheck(missing), describeCameraCheck(missing, 'front'));
  assert.equal(describeCameraCheck(missing).text, 'Move back: left ear and hips not in view. Move closer, you look small in the picture');
});

test('side badge: far-side points, hips and too_small do not stop "In frame"', () => {
  const farSideOnly = answer({ missing: ['right ear', 'right shoulder', 'right elbow', 'right wrist', 'hips'], too_small: true });
  assert.deepEqual(describeCameraCheck(farSideOnly, 'side-left'), { ok: true, text: IN_FRAME_TEXT });
  assert.deepEqual(describeCameraCheck(answer({ missing: ['left ear', 'left shoulder'] }), 'side-right'), { ok: true, text: IN_FRAME_TEXT });
});

test('side badge: a missing near-side point or a dark picture is still reported', () => {
  const nearMissing = describeCameraCheck(answer({ missing: ['left elbow', 'right elbow'] }), 'side-left');
  assert.deepEqual(nearMissing, { ok: false, text: 'Move back: left elbow not in view' });
  const dark = describeCameraCheck(answer({ missing: ['right wrist'], too_dark: true }), 'side-left');
  assert.equal(dark.ok, false);
  assert.match(dark.text, /more light/);
  assert.doesNotMatch(dark.text, /Move back|Move closer/);
});

test('front guide keeps its symmetric shapes; side guide has one arm and is mirrored for the right side', () => {
  const front = createCameraGuide('trumpet');
  assert.equal(front.dataset.position, 'front');
  assert.equal(front.children.length, 6);
  assert.ok(front.children.every((node) => node.getAttribute('transform') === null));
  const left = createCameraGuide('trumpet', 'side-left');
  const right = createCameraGuide('trumpet', 'side-right');
  assert.equal(left.dataset.position, 'side-left');
  assert.equal(left.children.length, 5);
  assert.ok(left.children.every((node) => node.getAttribute('transform') === null));
  assert.equal(right.dataset.position, 'side-right');
  assert.ok(right.children.every((node) => node.getAttribute('transform').includes('scale(-1 1)')));
  assert.equal(left.children.filter((node) => node.classList.contains('guide-instrument')).length, 1);
});

test('the picker defaults to front, swaps the outline, shows the note and remembers the choice', () => {
  delete stored.practice_coach_camera_view;
  const panel = createCameraPanel({ instrument: 'trumpet', check: async () => answer({}) });
  const select = panel.element.find((node) => node.tagName === 'select')[0];
  const note = panel.element.find((node) => node.textContent === SIDE_NOTE)[0];
  const guides = () => panel.element.find((node) => node.tagName === 'svg').map((node) => node.dataset.position);
  assert.equal(panel.view, 'front');
  assert.equal(note.hidden, true);
  assert.deepEqual(select.children.map((node) => node.textContent), ['Front', 'Side (left)', 'Side (right)']);
  assert.deepEqual(guides(), ['front']);
  select.value = 'side-left';
  select.listeners.change.forEach((handler) => handler());
  assert.equal(panel.view, 'side-left');
  assert.equal(note.hidden, false);
  assert.deepEqual(guides(), ['side-left']);
  assert.equal(stored.practice_coach_camera_view, 'side-left');
  assert.equal(createCameraPanel({ instrument: 'trumpet', check: async () => answer({}) }).view, 'side-left', 'a new panel starts on the remembered view');
  delete stored.practice_coach_camera_view;
});

const point = (visibility) => [0.5, 0.5, visibility];
const poseWith = (leftVisibility, rightVisibility) => Array.from({ length: 25 }, (_, i) => point(i % 2 ? leftVisibility : rightVisibility));
// MediaPipe: odd indices (11, 13, 15, 23) are the learner's left, even (12, 14, 16, 24, 8) their right; ear 7 is odd, 8 even.

test('detectNearSide: a clearly weaker far side is a side view; similar sides or no pose are not', () => {
  assert.equal(detectNearSide([{ pose: poseWith(0.95, 0.2) }, { pose: poseWith(0.9, 0.3) }]), 'left');
  assert.equal(detectNearSide([{ pose: poseWith(0.1, 0.9) }]), 'right');
  assert.equal(detectNearSide([{ pose: poseWith(0.9, 0.8) }]), null);
  assert.equal(detectNearSide([{ pose: null }, {}]), null);
  assert.equal(detectNearSide([]), null);
  assert.equal(detectNearSide(undefined), null);
});

test('near-side filters keep the nose and the near side only', () => {
  assert.equal(isNearPoint(11, 'left'), true);
  assert.equal(isNearPoint(12, 'left'), false);
  assert.equal(isNearPoint(0, 'right'), true);
  assert.equal(isNearPoint(12, null), true);
  assert.equal(isNearLine([11, 12], 'left'), false, 'the shoulder-to-shoulder line is front-view only');
  assert.equal(isNearLine([11, 13], 'left'), true);
});

function recordDrawing(frame, options) {
  const lines = [];
  const dots = [];
  let at;
  const ctx = {
    beginPath() {}, stroke() {}, fill() {}, fillRect() {}, fillText() {}, measureText: () => ({ width: 10 }),
    moveTo: (x, y) => { at = [x, y]; }, lineTo: (x, y) => lines.push([at, [x, y]]),
    arc: (x, y) => dots.push([x, y]),
  };
  drawOverlay(ctx, { frame, rect: { x: 0, y: 0, width: 100, height: 100 }, ...options });
  return { lines, dots };
}

test('the overlay draws every visible line for a front view and only the near side for a side view', () => {
  const pose = poseWith(0.9, 0.9);
  const front = recordDrawing({ pose }, { nearSide: null });
  assert.equal(front.lines.length, POSE_LINES.length);
  const side = recordDrawing({ pose }, { nearSide: 'left' });
  assert.equal(side.lines.length, 4, 'left shoulder-elbow, elbow-wrist, ear-shoulder and shoulder-hip');
});

// The video overlay, with a fake canvas and DOM (no browser). Run: node --test frontend/tests/overlay.test.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test, { afterEach } from 'node:test';
import { installFakeDom, settle } from './fake_dom.mjs';

const dom = installFakeDom();
dom.window.location.search = '?mock=1';
const readMock = (name) => JSON.parse(readFileSync(new URL(`../mock/${name}.json`, import.meta.url), 'utf8'));
const { nearestFrame } = await import('../js/results/overlay/frames.js');
const { contentRect, toCanvas } = await import('../js/results/overlay/geometry.js');
const { activeFlags, involvedLandmarks } = await import('../js/results/overlay/flag_points.js');
const { mountOverlay, TOGGLE_TEXT, UNAVAILABLE_TEXT } = await import('../js/results/overlay.js');
const { createJumper } = await import('../js/results/jumper.js');
const { buildMeasurementIndex } = await import('../js/results/measurements.js');
const { mockFileFor } = await import('../js/mock.js');

const tracks = readMock('get_tracks');
const analysis = readMock('get_analysis');
const flag = analysis.form[0]; // trumpet_elbows_pinned, side both, 6.0 - 7.0 s, peak 6.5

test('nearestFrame picks the nearest frame by binary search and honours the 0.2 s cutoff', () => {
  const frames = [0, 0.1, 0.2, 1.0, 1.1].map((t) => ({ t }));
  assert.equal(nearestFrame(frames, 0.2).t, 0.2);
  assert.equal(nearestFrame(frames, 0.14).t, 0.1);
  assert.equal(nearestFrame(frames, 0.16).t, 0.2);
  assert.equal(nearestFrame(frames, -0.1).t, 0, 'before the first frame, within the cutoff');
  assert.equal(nearestFrame(frames, 1.25).t, 1.1, 'after the last frame, within the cutoff');
  assert.equal(nearestFrame(frames, 0.6), null, 'in the gap, more than 0.2 s from both');
  assert.equal(nearestFrame(frames, 1.31), null);
  assert.equal(nearestFrame(frames, 1.3).t, 1.1, 'exactly 0.2 s away still counts');
  assert.equal(nearestFrame(frames, NaN), null);
});

test('nearestFrame with no frames, or one frame', () => {
  assert.equal(nearestFrame([], 1), null);
  assert.equal(nearestFrame(undefined, 1), null);
  assert.equal(nearestFrame([{ t: 5 }], 4.9).t, 5);
  assert.equal(nearestFrame([{ t: 5 }], 4), null);
});

test('contentRect letterboxes object-fit: contain and toCanvas scales into it', () => {
  const wide = contentRect({ width: 800, height: 400 }, { width: 640, height: 480 }); // 4:3 video in a 2:1 box: side bars
  assert.ok(Math.abs(wide.width - 400 * (4 / 3)) < 1e-9);
  assert.deepEqual([wide.y, wide.height], [0, 400]);
  assert.equal(wide.x, (800 - wide.width) / 2);
  const tall = contentRect({ width: 400, height: 600 }, { width: 640, height: 480 }); // top and bottom bars
  assert.deepEqual([tall.x, tall.y, tall.width, tall.height], [0, 600 / 2 - 150, 400, 300]);
  assert.deepEqual(toCanvas([0.5, 1], tall), [200, 150 + 300]);
  assert.deepEqual(toCanvas([0, 0], wide), [wide.x, 0]);
});

test('contentRect for fill, cover, unknown size and an exact fit', () => {
  const box = { width: 800, height: 400 };
  const video = { width: 640, height: 480 };
  assert.deepEqual(contentRect(box, video, 'fill'), { x: 0, y: 0, width: 800, height: 400 });
  assert.deepEqual(contentRect(box, video, 'cover'), { x: 0, y: -100, width: 800, height: 600 });
  assert.deepEqual(contentRect(box, { width: 0, height: 0 }), { x: 0, y: 0, width: 800, height: 400 });
  assert.deepEqual(contentRect({ width: 640, height: 480 }, video), { x: 0, y: 0, width: 640, height: 480 });
  assert.deepEqual(contentRect({ width: 1280, height: 960 }, video, 'scale-down'), { x: 320, y: 240, width: 640, height: 480 });
});

test('involvedLandmarks by rule and side', () => {
  const points = (rule, side) => involvedLandmarks({ rule, side }).sort((a, b) => a - b);
  assert.deepEqual(points('trumpet_head_down', 'both'), [0, 7, 8]);
  assert.deepEqual(points('trumpet_head_down', 'left'), [0, 7], 'the nose is centred, the ear is sided');
  assert.deepEqual(points('trumpet_elbows_pinned', null), [11, 12, 13, 14]);
  assert.deepEqual(points('trumpet_elbows_pinned', 'right'), [12, 14]);
  assert.deepEqual(points('trumpet_elbows_wide', null), [11, 12, 13, 14]);
  assert.deepEqual(points('trumpet_elbows_wide', 'left'), [11, 13]);
  assert.deepEqual(points('trumpet_bell_angle', null), [9, 10, 15, 16], 'the mouth and both wrists');
  assert.deepEqual(points('trumpet_bell_angle', 'left'), [9, 10, 15, 16], 'the bell points are centred');
  assert.deepEqual(points('shoulders_raised', 'both'), [7, 8, 11, 12]);
  assert.deepEqual(points('shoulders_raised', 'left'), [7, 11]);
  assert.deepEqual(points('slouching', 'both'), [11, 12, 23, 24]);
  assert.deepEqual(points('slouching', 'right'), [12, 24]);
  assert.deepEqual(points('some_future_rule', 'both'), []);
});

test('activeFlags includes both ends of the span', () => {
  const flags = [{ start_s: 6, end_s: 7 }, { start_s: 8, end_s: 9 }];
  assert.equal(activeFlags(flags, 5.99).length, 0);
  assert.equal(activeFlags(flags, 6).length, 1);
  assert.equal(activeFlags(flags, 7).length, 1);
  assert.equal(activeFlags(flags, 7.5).length, 0);
});

test('the mock tracks cover the 12 s mock video and the mock flag is a trumpet rule', () => {
  assert.equal(mockFileFor('GET', '/sessions/sess_mock1/takes/take_1/tracks'), 'get_tracks');
  assert.ok(tracks.frames.at(-1).t >= 11.9, `last frame at ${tracks.frames.at(-1).t} s`);
  assert.equal(tracks.frames[0].pose.length, 25);
  assert.equal(tracks.frames[0].left_hand.length, 21);
  assert.ok(tracks.frames.some((frame) => frame.pose === null), 'a lost-tracking frame to draw around');
  assert.ok(['trumpet_head_down', 'trumpet_elbows_pinned', 'shoulders_raised', 'slouching'].includes(flag.rule));
  assert.deepEqual(analysis.form.map((f) => f.rule), ['trumpet_elbows_pinned', 'trumpet_elbows_wide', 'trumpet_bell_angle']);
  analysis.form.forEach((f) => assert.ok(f.label && involvedLandmarks(f).length > 0, `${f.rule} has a label and points`));
});

// ---- mountOverlay with a fake canvas ----

function fakeContext() {
  const log = { moves: [], lines: [], arcs: [], texts: [], clears: 0 };
  return {
    log,
    clearRect() { log.clears += 1; },
    beginPath() {}, stroke() {}, fill() {}, fillRect() {},
    moveTo(x, y) { log.moves.push([x, y]); },
    lineTo(x, y) { log.lines.push([x, y]); },
    arc(x, y, radius) { log.arcs.push({ x, y, radius, color: this.fillStyle }); },
    fillText(text) { log.texts.push(text); },
    measureText: (text) => ({ width: text.length * 7 }),
  };
}

// Every canvas the code creates gets a fake context; setup() collects them in canvasSink.
let canvasSink = [];
const mounted = [];
afterEach(() => { mounted.splice(0).forEach((overlay) => overlay?.destroy()); }); // no listener outlives its test
const createElement = dom.document.createElement;
dom.document.createElement = (name) => {
  const node = createElement(name);
  if (name === 'canvas') { node.context = fakeContext(); node.getContext = () => node.context; canvasSink.push(node); }
  return node;
};

function setup({ tag = 'video', analysisOverride = {}, getTracks = async () => tracks, size = { width: 640, height: 480 } } = {}) {
  const canvases = [];
  canvasSink = canvases;
  const mediaElement = dom.document.createElement(tag);
  Object.assign(mediaElement, { currentTime: 0, videoWidth: 640, videoHeight: 480, clientWidth: size.width, clientHeight: size.height });
  const stage = dom.document.createElement('div');
  stage.append(mediaElement);
  const formFlagSlot = dom.document.createElement('div');
  const section = dom.document.createElement('section');
  section.append(stage, formFlagSlot);
  dom.body.append(section);

  const seeks = [];
  const player = { mediaElement, stage, formFlagSlot, seekTo: (seconds) => seeks.push(seconds) };
  const analysisUsed = { ...analysis, ...analysisOverride };
  const jumper = createJumper({ player, barList: { highlight() {} } });
  const rendered = { player, analysis: analysisUsed, index: buildMeasurementIndex(analysisUsed), jumper };

  const fetches = [];
  const frameQueue = new Map();
  let nextId = 1;
  const cancelled = [];
  const deps = {
    getTracks: async (...args) => { fetches.push(args); return getTracks(...args); },
    requestAnimationFrame: (fn) => { frameQueue.set(nextId, fn); return nextId++; },
    cancelAnimationFrame: (id) => { cancelled.push(id); frameQueue.delete(id); },
  };
  const step = () => { const [id, fn] = [...frameQueue][0]; frameQueue.delete(id); fn(); };
  const overlay = mountOverlay(rendered, { sessionId: 'sess_mock1', take: 'take_1' }, deps);
  mounted.push(overlay);
  return { overlay, rendered, mediaElement, stage, formFlagSlot, section, seeks, fetches, canvases, frameQueue, cancelled, step };
}

const drawAt = (env, seconds) => { env.mediaElement.currentTime = seconds; env.canvases[0].context.log.arcs.length = 0; env.canvases[0].context.log.texts.length = 0; env.step(); return env.canvases[0].context.log; };
const redDots = (log) => log.arcs.filter((arc) => arc.color === '#d92d20');

test('the tracks are fetched once, when form_status is done', async () => {
  const env = setup();
  env.overlay.onAnalysis({ form_status: 'processing' });
  await settle();
  assert.equal(env.fetches.length, 0, 'not fetched before the form check is done');
  env.overlay.onAnalysis({ form_status: 'done' });
  env.overlay.onAnalysis({ form_status: 'done' });
  await settle();
  env.overlay.onAnalysis({ form_status: 'done' });
  assert.deepEqual(env.fetches, [['sess_mock1', 'take_1']]);
  assert.equal(env.canvases.length, 1);
  assert.equal(env.stage.children.at(-1), env.canvases[0], 'the canvas sits in the video stage, after the video');
  env.overlay.destroy();
});

test('a mic take has no overlay and no fetch', async () => {
  const env = setup({ tag: 'audio' });
  assert.equal(env.overlay, null);
  assert.equal(env.fetches.length, 0);
  assert.equal(env.canvases.length, 0);
});

test('draws pose lines and hand points scaled to the video, letterboxed inside a wider box', async () => {
  const env = setup({ size: { width: 800, height: 480 } }); // 4:3 picture is 640 px wide, centred: x offset 80
  env.overlay.onAnalysis({ form_status: 'done' });
  await settle();
  const log = drawAt(env, 2.0);
  const frame = tracks.frames.find((f) => f.t === 2);
  const [sx, sy] = frame.pose[11];
  assert.deepEqual(log.moves.at(1), [80 + sx * 640, sy * 480], 'shoulder-elbow line starts at the left shoulder');
  assert.equal(log.moves.length, 9, 'nine pose lines');
  assert.equal(env.canvases[0].width, 800);
  assert.equal(env.canvases[0].height, 480);
  const handDots = log.arcs.filter((arc) => arc.color === '#2e90fa');
  assert.equal(handDots.length, 21 * (frame.left_hand ? 2 : 1));
  assert.equal(redDots(log).length, 0, 'no flag at 2 s');
  assert.deepEqual(log.texts, []);
  env.overlay.destroy();
});

test('during the flag span the involved points are red and the label shows; outside it they are not', async () => {
  const env = setup();
  env.overlay.onAnalysis({ form_status: 'done' });
  await settle();
  const inside = drawAt(env, 6.5);
  assert.equal(redDots(inside).length, 4, 'elbows and shoulders, side both');
  assert.deepEqual(inside.texts, [flag.label]);
  const frame = tracks.frames.find((f) => f.t === 6.5);
  assert.ok(redDots(inside).some((dot) => dot.x === frame.pose[13][0] * 640 && dot.y === frame.pose[13][1] * 480), 'left elbow');
  const before = drawAt(env, 5.9);
  assert.equal(redDots(before).length, 0);
  assert.deepEqual(before.texts, []);
  env.overlay.destroy();
});

test('a one-sided flag reddens only that side', async () => {
  const left = { ...flag, rule: 'shoulders_raised', side: 'left' };
  const env = setup({ analysisOverride: { form: [left] } });
  env.overlay.onAnalysis({ form_status: 'done' });
  await settle();
  assert.equal(redDots(drawAt(env, 6.5)).length, 2, 'left ear and left shoulder');
  env.overlay.destroy();
});

test('nothing is drawn when the nearest frame is too far away or tracking was lost', async () => {
  const env = setup();
  env.overlay.onAnalysis({ form_status: 'done' });
  await settle();
  const lost = tracks.frames.find((f) => f.pose === null).t;
  assert.equal(drawAt(env, lost).moves.length, 0, 'a frame with no pose draws no lines');
  env.mediaElement.currentTime = 50;
  const log = env.canvases[0].context.log;
  log.moves.length = 0;
  env.step();
  assert.equal(log.moves.length, 0, 'past the end of the tracks');
  env.overlay.destroy();
});

test('the checkbox turns the overlay off and on', async () => {
  const env = setup();
  env.overlay.onAnalysis({ form_status: 'done' });
  await settle();
  const box = env.formFlagSlot.all().find((n) => n.tagName === 'INPUT');
  assert.ok(box.checked);
  assert.match(env.formFlagSlot.textContent, new RegExp(TOGGLE_TEXT));
  const clears = env.canvases[0].context.log.clears;
  box.checked = false;
  box.listeners.change.forEach((fn) => fn());
  assert.equal(env.frameQueue.size, 0, 'the loop stops while off');
  assert.equal(env.canvases[0].context.log.clears, clears + 1, 'and the canvas is cleared');
  box.checked = true;
  box.listeners.change.forEach((fn) => fn());
  assert.equal(env.frameQueue.size, 1, 'the loop runs again');
  env.overlay.destroy();
});

test('a failed tracks fetch shows a note, no canvas, no retry; the flag list still jumps', async () => {
  const failures = [];
  const original = console.error;
  console.error = (...args) => failures.push(args);
  try {
    const env = setup({ getTracks: async () => { throw new Error('HTTP 409'); } });
    env.overlay.onAnalysis({ form_status: 'done' });
    await settle();
    env.overlay.onAnalysis({ form_status: 'done' });
    await settle();
    assert.equal(env.fetches.length, 1, 'no auto-retry');
    assert.equal(env.canvases.length, 0);
    assert.equal(env.frameQueue.size, 0);
    assert.deepEqual(env.formFlagSlot.texts('overlay-note'), [UNAVAILABLE_TEXT]);
    assert.equal(failures.length, 1, 'the failure is logged');
    env.formFlagSlot.withClass('sentence-text')[0].click();
    assert.deepEqual(env.seeks, [6.5]);
  } finally {
    console.error = original;
  }
});

test('an answer without a frames list counts as a failure', async () => {
  const original = console.error;
  console.error = () => {};
  try {
    const env = setup({ getTracks: async () => ({ fps: 10 }) });
    env.overlay.onAnalysis({ form_status: 'done' });
    await settle();
    assert.deepEqual(env.formFlagSlot.texts('overlay-note'), [UNAVAILABLE_TEXT]);
    assert.equal(env.canvases.length, 0);
  } finally {
    console.error = original;
  }
});

test('the flag list jumps to peak_s exactly, from the label and from the chip', () => {
  const env = setup();
  assert.deepEqual(env.formFlagSlot.texts('sentence-text'), analysis.form.map((f) => f.label), 'the new flags are listed too');
  env.formFlagSlot.withClass('sentence-text')[0].click();
  env.formFlagSlot.withClass('chip')[0].click();
  assert.deepEqual(env.seeks, [6.5, 6.5], 'no 1 s lead for a form flag');
  assert.equal(env.formFlagSlot.withClass('chip')[0].textContent, '6.5 s');
  env.formFlagSlot.withClass('sentence-text').slice(1).forEach((item) => item.click());
  assert.deepEqual(env.seeks.slice(2), [8.5, 10.5], 'the new flags jump to their own peak_s');
});

test('no flags: no list', () => {
  const env = setup({ analysisOverride: { form: [] } });
  assert.equal(env.formFlagSlot.withClass('form-flags').length, 0);
});

test('leaving the route (hashchange) stops the loop and drops the listener', async () => {
  const env = setup();
  env.overlay.onAnalysis({ form_status: 'done' });
  await settle();
  assert.equal(dom.window.count('hashchange'), 1);
  assert.equal(env.frameQueue.size, 1);
  dom.window.dispatch('hashchange');
  assert.equal(env.frameQueue.size, 0, 'the pending animation frame is cancelled');
  assert.equal(env.cancelled.length, 1);
  assert.equal(dom.window.count('hashchange'), 0);
  assert.equal(env.stage.children.includes(env.canvases[0]), false, 'the canvas is removed');
});

test('a screen replaced without a hashchange stops the loop on the next frame', async () => {
  const env = setup();
  env.overlay.onAnalysis({ form_status: 'done' });
  await settle();
  env.section.remove();
  env.canvases[0].parent = null; // the whole screen is gone from the document
  env.stage.parent = null;
  env.step();
  assert.equal(env.frameQueue.size, 0);
  assert.equal(dom.window.count('hashchange'), 0);
});

test('leaving while the tracks are still loading draws nothing afterwards', async () => {
  let release;
  const env = setup({ getTracks: () => new Promise((resolve) => { release = resolve; }) });
  env.overlay.onAnalysis({ form_status: 'done' });
  dom.window.dispatch('hashchange');
  release(tracks);
  await settle();
  assert.equal(env.canvases.length, 0);
  assert.equal(env.frameQueue.size, 0);
});

// Node tests for the tone page: exact Hz, 20 ms fades, Hold, and one note at a time. Run: node --test frontend/tests/
import assert from 'node:assert/strict';
import test from 'node:test';
import { FakeNode, installFakeBrowser } from './fake_env.mjs';

const env = installFakeBrowser({ search: '?mock=1&instrument=trumpet&note=F4' });
const { createTonePlayer, FADE_S, TONE_GAIN, AUTO_STOP_S } = await import('../js/tone/player.js');
const { stopWhenLeaving } = await import('../js/tone/lifecycle.js');
const { startTonePage, buttonLabel, formatHz, readParams } = await import('../js/tone/page.js');
const { mockRequestLog } = await import('../js/mock.js');

// A context that records every oscillator, with its frequency, start/stop times and gain automation.
function recordingContext() {
  const ctx = {
    currentTime: 10, state: 'running', suspends: 0, destination: {}, voices: [],
    async suspend() { ctx.suspends += 1; ctx.state = 'suspended'; },
    async resume() { ctx.state = 'running'; },
    createOscillator() {
      const osc = { type: '', frequency: { value: 0 }, starts: [], stops: [], connect: (node) => node, start(t) { this.starts.push(t); }, stop(t) { this.stops.push(t); } };
      ctx.voices.push(osc);
      return osc;
    },
    createGain() {
      const events = [];
      const gain = { value: TONE_GAIN, setValueAtTime: (v, t) => events.push(['set', v, t]), linearRampToValueAtTime: (v, t) => events.push(['ramp', v, t]),
        cancelScheduledValues: (t) => events.push(['cancel', t]) };
      const node = { gain, events, connect: (n) => n, disconnect() {} };
      ctx.voices[ctx.voices.length - 1].gainNode = node;
      return node;
    },
  };
  return ctx;
}
const F4 = { name: 'F4', hz: 349.23 };
const Bb4 = { name: 'Bb4', hz: 466.16 };

function newPlayer(ctx, extra = {}) {
  const shown = [];
  const errors = [];
  const player = createTonePlayer({ getContext: async () => ctx, onChange: (name) => shown.push(name), onError: (err) => errors.push(err.message), ...extra });
  return { player, shown, errors };
}

test('a tap plays a sine at the exact Hz with a 20 ms fade in at gain 0.5 and no audio-clock end', async () => {
  const ctx = recordingContext();
  const { player, shown } = newPlayer(ctx);
  await player.toggle(Bb4);
  const [osc] = ctx.voices;
  assert.equal(osc.type, 'sine');
  assert.equal(osc.frequency.value, 466.16);
  assert.deepEqual(osc.starts, [10]);
  assert.deepEqual(osc.stops, [], 'the end comes from the wall-clock auto-stop, not a scheduled stop');
  assert.deepEqual([AUTO_STOP_S, FADE_S, TONE_GAIN], [10, 0.02, 0.5]);
  assert.deepEqual(osc.gainNode.events, [['set', 0, 10], ['ramp', 0.5, 10.02]]);
  assert.deepEqual(shown, ['Bb4']);
  await player.stop();
});

test('tapping another note stops the current one first (with a fade), and tapping the same note stops it', async () => {
  const ctx = recordingContext();
  const { player, shown } = newPlayer(ctx);
  await player.toggle(F4);
  ctx.currentTime = 11;
  await player.toggle(Bb4);
  assert.deepEqual(ctx.voices[0].stops.at(-1), 11 + FADE_S);
  assert.deepEqual(ctx.voices[0].gainNode.events.slice(-4), [['ramp', 0.5, 10.02], ['cancel', 11], ['set', 0.5, 11], ['ramp', 0, 11.02]]);
  assert.deepEqual(ctx.voices[1].starts, [11]);
  assert.equal(player.playing(), 'Bb4');
  await player.toggle(Bb4);
  assert.equal(ctx.voices[1].stops.at(-1), 11 + FADE_S);
  assert.equal(player.playing(), null);
  assert.deepEqual(shown, ['F4', 'Bb4', null]);
});

test('starting a new note leaves only one source alive', async () => {
  const ctx = recordingContext();
  const { player } = newPlayer(ctx);
  await player.toggle(F4);
  await player.toggle(Bb4);
  await player.toggle(F4);
  assert.equal(ctx.voices.length, 3);
  assert.deepEqual(ctx.voices.map((osc) => osc.stops.length > 0), [true, true, false]);
  await player.stop();
});

test('Stop silences a playing note at once (gain 0, source stopped), suspends the context and clears the highlight', async () => {
  const ctx = recordingContext();
  const { player, shown } = newPlayer(ctx);
  await player.toggle(F4);
  ctx.currentTime = 12;
  await player.stop();
  assert.deepEqual(ctx.voices[0].gainNode.events.slice(-2), [['cancel', 12], ['set', 0, 12]]);
  assert.deepEqual(ctx.voices[0].stops, [12]);
  assert.equal(ctx.suspends, 1);
  assert.equal(player.playing(), null);
  assert.deepEqual(shown, ['F4', null]);
  await player.stop(); // nothing playing: still fine, and it does not suspend twice
  assert.equal(ctx.suspends, 1);
});

test('a tone after Stop wakes the suspended context again', async () => {
  const ctx = recordingContext();
  const { player } = newPlayer(ctx, { getContext: async () => { await ctx.resume(); return ctx; } });
  await player.toggle(F4);
  await player.stop();
  await player.toggle(F4);
  assert.equal(ctx.state, 'running');
  assert.equal(player.playing(), 'F4');
  await player.stop();
});

test('a Stop that comes while the context is still waking keeps the tap from starting a tone', async () => {
  const ctx = recordingContext();
  let wake;
  const { player, shown } = newPlayer(ctx, { getContext: () => new Promise((resolve) => { wake = () => resolve(ctx); }) });
  const tap = player.toggle(F4);
  await player.stop();
  wake();
  await tap;
  assert.equal(ctx.voices.length, 0);
  assert.deepEqual(shown, [null]);
});

test('without Hold the note stops by itself after 10 s; with Hold it keeps playing until Stop', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const ctx = recordingContext();
  const { player, shown } = newPlayer(ctx);
  await player.toggle(F4);
  t.mock.timers.tick(AUTO_STOP_S * 1000 - 1);
  assert.equal(player.playing(), 'F4');
  t.mock.timers.tick(1);
  await Promise.resolve();
  assert.equal(player.playing(), null);
  assert.equal(ctx.suspends, 1);
  assert.deepEqual(shown, ['F4', null]);

  player.setHold(true);
  await player.toggle(F4);
  t.mock.timers.tick(10 * AUTO_STOP_S * 1000);
  assert.equal(player.playing(), 'F4', 'Hold: no auto-stop');
  await player.stop();
  assert.equal(player.playing(), null);
});

test('turning Hold on during a note cancels its auto-stop, and turning it off starts a fresh 10 s', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const ctx = recordingContext();
  const { player } = newPlayer(ctx);
  await player.toggle(F4);
  t.mock.timers.tick(9000);
  player.setHold(true);
  t.mock.timers.tick(60000);
  assert.equal(player.playing(), 'F4');
  player.setHold(false);
  t.mock.timers.tick(9999);
  assert.equal(player.playing(), 'F4');
  t.mock.timers.tick(1);
  assert.equal(player.playing(), null);
});

test('a failing stop step is logged and reported, and the other steps still run', async () => {
  const ctx = recordingContext();
  const { player, errors } = newPlayer(ctx);
  const realError = console.error;
  const logged = [];
  console.error = (...args) => logged.push(args);
  try {
    await player.toggle(F4);
    ctx.voices[0].stop = () => { throw new Error('InvalidStateError'); };
    await player.stop();
  } finally {
    console.error = realError;
  }
  assert.equal(player.playing(), null);
  assert.deepEqual(ctx.voices[0].gainNode.events.at(-1), ['set', 0, 10], 'gain still went to 0');
  assert.match(errors[0], /Press Stop, or close this page/);
  assert.equal(logged.length, 1);
  assert.equal(ctx.suspends, 1);
});

test('a context that cannot be suspended is reported with a message to act on', async () => {
  const ctx = recordingContext();
  ctx.suspend = async () => { throw new Error('boom'); };
  const { player, errors } = newPlayer(ctx);
  const realError = console.error;
  console.error = () => {};
  try {
    await player.toggle(F4);
    await player.stop();
  } finally {
    console.error = realError;
  }
  assert.match(errors[0], /tone is silent/);
});

test('pagehide and the page turning hidden stop the tone; visible does not', async () => {
  const ctx = recordingContext();
  const { player } = newPlayer(ctx);
  const pageListeners = {};
  const docListeners = {};
  const doc = { visibilityState: 'visible', addEventListener: (type, fn) => { docListeners[type] = fn; } };
  stopWhenLeaving(player, { page: { addEventListener: (type, fn) => { pageListeners[type] = fn; } }, doc });
  await player.toggle(F4);
  docListeners.visibilitychange();
  assert.equal(player.playing(), 'F4', 'still visible');
  doc.visibilityState = 'hidden';
  docListeners.visibilitychange();
  assert.equal(player.playing(), null);
  assert.equal(ctx.suspends, 1);
  await player.toggle(F4);
  pageListeners.pagehide();
  assert.equal(player.playing(), null);
});

test('the page labels each button with the note and exact Hz, and reads the URL', () => {
  assert.equal(buttonLabel({ name: 'A4', hz: 440 }), 'A4 - 440.0 Hz'); // a whole number keeps one decimal
  assert.equal(buttonLabel({ name: 'Bb3', hz: 233.08 }), 'Bb3 - 233.08 Hz');
  assert.equal(formatHz(466.16), '466.16');
  assert.deepEqual(readParams('?instrument=trumpet&note=F4'), { instrument: 'trumpet', askedNote: 'F4' });
  assert.deepEqual(readParams(''), { instrument: 'trumpet', askedNote: '' });
});

test('page: the three notes from GET /reference-notes?instrument=, a highlight while playing, and Hold', async () => {
  mockRequestLog.length = 0;
  const root = new FakeNode('main');
  await startTonePage(root, '?instrument=trumpet&note=F4');
  assert.equal(mockRequestLog[0].path, '/reference-notes?instrument=trumpet');
  const labels = root.find((n) => n.tagName === 'button').map((n) => n.textContent);
  assert.deepEqual(labels, ['Bb3 - 233.08 Hz', 'F4 - 349.23 Hz', 'Bb4 - 466.16 Hz', 'Hold: off', 'Stop']);
  assert.ok(root.hasText('The app is asking for F4.'));
  const a4 = root.button('F4 - 349.23 Hz');
  assert.ok(a4.classList.contains('asked'));
  await a4.click(); // the first tap creates the AudioContext
  assert.ok(env.audioContext, 'AudioContext created by the tap');
  assert.ok(a4.classList.contains('playing'));
  assert.equal(a4.attrs['aria-pressed'], 'true');
  await root.button('Bb4 - 466.16 Hz').click();
  assert.ok(!a4.classList.contains('playing'));
  assert.ok(root.button('Bb4 - 466.16 Hz').classList.contains('playing'));
  await root.button('Hold: off').click();
  assert.equal(root.button('Hold: on').attrs['aria-pressed'], 'true');
  await root.button('Stop').click(); // Stop silences the held note and the highlight follows
  assert.ok(!root.button('Bb4 - 466.16 Hz').classList.contains('playing'));
  assert.equal(root.button('Bb4 - 466.16 Hz').attrs['aria-pressed'], 'false');
  assert.equal(env.audioContext.state, 'suspended');
});

test('page: the page turning hidden silences the note and clears its highlight', async () => {
  const root = new FakeNode('main');
  await startTonePage(root, '?instrument=trumpet');
  const f4 = root.button('F4 - 349.23 Hz');
  await f4.click();
  assert.ok(f4.classList.contains('playing'));
  document.visibilityState = 'hidden';
  env.documentListeners.visibilitychange.forEach((handler) => handler());
  await new Promise((resolve) => setImmediate(resolve));
  document.visibilityState = 'visible';
  assert.ok(!f4.classList.contains('playing'));
  assert.equal(f4.attrs['aria-pressed'], 'false');
  assert.equal(env.audioContext.state, 'suspended');
});

test('page: a failed notes request shows the message in the red banner and no buttons', async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 500, json: async () => ({}) }); // the mock file cannot be read
  const root = new FakeNode('main');
  await startTonePage(root, '?instrument=trumpet');
  globalThis.fetch = realFetch;
  assert.equal(env.banner.hidden, false);
  assert.match(env.banner.textContent, /No mock response for GET \/reference-notes\?instrument=trumpet/);
  assert.equal(root.find((n) => n.tagName === 'button').length, 0);
});

test('page: with no instrument in the URL it asks for the trumpet notes', async () => {
  mockRequestLog.length = 0;
  await startTonePage(new FakeNode('main'), '');
  assert.equal(mockRequestLog[0].path, '/reference-notes?instrument=trumpet');
});

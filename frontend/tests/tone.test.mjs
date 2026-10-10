// Node tests for the tone page: exact Hz, 20 ms fades, Hold, and one note at a time. Run: node --test frontend/tests/
import assert from 'node:assert/strict';
import test from 'node:test';
import { FakeNode, installFakeBrowser } from './fake_env.mjs';

const env = installFakeBrowser({ search: '?mock=1&instrument=trumpet&note=F4' });
const { createTonePlayer, FADE_S, TONE_GAIN, TONE_SECONDS, HOLD_LIMIT_S } = await import('../js/tone/player.js');
const { startTonePage, buttonLabel, formatHz, readParams } = await import('../js/tone/page.js');
const { mockRequestLog } = await import('../js/mock.js');

// A context that records every oscillator, with its frequency, start/stop times and gain automation.
function recordingContext() {
  const ctx = {
    currentTime: 10, destination: {}, voices: [],
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

test('a tap plays a sine at the exact Hz for 4 s with 20 ms fades at gain 0.5', async () => {
  const ctx = recordingContext();
  const shown = [];
  const player = createTonePlayer({ getContext: async () => ctx, onChange: (name) => shown.push(name) });
  await player.toggle(Bb4);
  const [osc] = ctx.voices;
  assert.equal(osc.type, 'sine');
  assert.equal(osc.frequency.value, 466.16);
  assert.deepEqual(osc.starts, [10]);
  assert.deepEqual(osc.stops, [10 + TONE_SECONDS]);
  assert.deepEqual([TONE_SECONDS, FADE_S, TONE_GAIN], [4, 0.02, 0.5]);
  assert.deepEqual(osc.gainNode.events, [
    ['set', 0, 10], ['ramp', 0.5, 10.02], // fade in
    ['set', 0.5, 13.98], ['ramp', 0, 14], // fade out
  ]);
  assert.deepEqual(shown, ['Bb4']);
});

test('tapping another note stops the current one first (with a fade), and tapping the same note stops it', async () => {
  const ctx = recordingContext();
  const shown = [];
  const player = createTonePlayer({ getContext: async () => ctx, onChange: (name) => shown.push(name) });
  await player.toggle(F4);
  ctx.currentTime = 11;
  await player.toggle(Bb4);
  assert.deepEqual(ctx.voices[0].stops.at(-1), 11 + FADE_S);
  assert.deepEqual(ctx.voices[0].gainNode.events.slice(-3), [['cancel', 11], ['set', 0.5, 11], ['ramp', 0, 11.02]]);
  assert.deepEqual(ctx.voices[1].starts, [11]);
  assert.equal(player.playing(), 'Bb4');
  await player.toggle(Bb4);
  assert.equal(ctx.voices[1].stops.at(-1), 11 + FADE_S);
  assert.equal(player.playing(), null);
  assert.deepEqual(shown, ['F4', 'Bb4', null]);
});

test('Hold keeps the note playing until it is tapped again, and releasing it ends the note', async () => {
  const ctx = recordingContext();
  const player = createTonePlayer({ getContext: async () => ctx });
  await player.setHold(true);
  await player.toggle(F4);
  assert.equal(ctx.voices[0].stops.at(-1), 10 + HOLD_LIMIT_S, 'no 4 s end while holding');
  ctx.currentTime = 20; // well past 4 s
  assert.equal(player.playing(), 'F4');
  await player.setHold(false); // let go late: the note ends right away, not in the past
  assert.equal(ctx.voices[0].stops.at(-1), 20 + FADE_S);
  await player.toggle(F4);
  assert.equal(player.playing(), null);
  // switching Hold on during a normal note cancels its scheduled end
  await player.toggle(Bb4);
  ctx.currentTime = 21;
  await player.setHold(true);
  assert.equal(ctx.voices[1].stops.at(-1), 20 + HOLD_LIMIT_S);
  assert.deepEqual(ctx.voices[1].gainNode.events.find((event) => event[0] === 'cancel'), ['cancel', 20 + TONE_SECONDS - FADE_S]);
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
  assert.deepEqual(labels, ['Bb3 - 233.08 Hz', 'F4 - 349.23 Hz', 'Bb4 - 466.16 Hz', 'Hold: off']);
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

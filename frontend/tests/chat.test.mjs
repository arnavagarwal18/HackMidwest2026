// Instructor chat panel logic with a fake DOM (no browser). Run: node --test frontend/tests/chat.test.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { installFakeDom, settle } from './fake_dom.mjs';

installFakeDom();
const { MAX_MESSAGE_LENGTH, EMPTY_MESSAGE_ERROR, TOO_LONG_ERROR, TIMEOUT_MESSAGE, FALLBACK_NOTE, validateMessage, withTimeout, openingTurn } =
  await import('../js/chat/model.js');
const { createChatPanel } = await import('../js/chat/panel.js');
const { buildMeasurementIndex } = await import('../js/results/measurements.js');
const { mockFileFor } = await import('../js/mock.js');

const ANALYSIS = { notes: [{ id: 'n:t1:3:2', bar: 3, expected_onset_s: 4.5 }], bars: [{ id: 'b:t1:3', bar: 3 }] };
const sentence = (text, extra = {}) => ({ text, cites: ['n:t1:3:2'], claims: [], jump: { bar: 3, time_s: 4.5 }, checked: true, ...extra });
const turn = (n, role, text, extra = {}) => ({ turn: n, role, text, take_id: 'take_1', sentences: null, dropped: null, mode: null, created_at: 'x', ...extra });
const aiReply = (text = 'The E sounded as an F.') => ({
  user_turn: turn(1, 'user', 'Why?'),
  instructor_turn: turn(2, 'instructor', text, { sentences: [sentence(text)], mode: 'ai' }),
});

function deferred() {
  const d = {};
  d.promise = new Promise((resolve, reject) => { d.resolve = resolve; d.reject = reject; });
  return d;
}

// Builds a panel with fakes; options.getChat / sendChat override the defaults.
async function setup(options = {}) {
  const root = document.createElement('aside');
  const errors = [];
  const sent = [];
  const jumps = [];
  const panel = createChatPanel(root, {
    sessionId: 's1',
    take: 'take_1',
    getChat: options.getChat ?? (async () => ({ turns: [] })),
    sendChat: options.sendChat ?? (async (...args) => { sent.push(args); return aiReply(); }),
    reportError: (err) => errors.push(err.message),
    timeoutMs: options.timeoutMs,
    timers: options.timers,
  });
  await panel.whenReady;
  const jumpContext = { index: buildMeasurementIndex(ANALYSIS), jumper: { jumpTo: (place) => jumps.push(place) } };
  return { root, panel, errors, sent, jumps, jumpContext, input: root.withClass('chat-input')[0], send: root.button('Send') };
}

test('validateMessage accepts 1-1000 characters and explains the rest', () => {
  assert.equal(validateMessage('a'), null);
  assert.equal(validateMessage('a'.repeat(MAX_MESSAGE_LENGTH)), null);
  assert.equal(validateMessage(''), EMPTY_MESSAGE_ERROR);
  assert.equal(validateMessage('   \n'), EMPTY_MESSAGE_ERROR);
  assert.equal(validateMessage('a'.repeat(MAX_MESSAGE_LENGTH + 1)), TOO_LONG_ERROR);
  assert.equal(validateMessage(` ${'a'.repeat(MAX_MESSAGE_LENGTH)} `), null, 'only the trimmed text that is sent counts');
});

test('withTimeout rejects at the limit and clears its timer when the promise settles first', async () => {
  const cleared = [];
  let scheduled;
  const timers = { setTimer: (fn, ms) => { scheduled = { fn, ms }; return scheduled; }, clearTimer: (timer) => cleared.push(timer) };
  const slow = withTimeout(new Promise(() => {}), 35000, 'too slow', timers);
  assert.equal(scheduled.ms, 35000);
  scheduled.fn();
  await assert.rejects(slow, /too slow/);
  assert.equal(await withTimeout(Promise.resolve(7), 1000, 'x', timers), 7);
  await assert.rejects(withTimeout(Promise.reject(new Error('boom')), 1000, 'x', timers), /boom/);
  assert.equal(cleared.length, 2, 'the timer is cleared when the promise settles first');
});

test('openingTurn is the feedback sentences as an instructor turn, or null without any', () => {
  const opening = openingTurn({ mode: 'ai', sentences: [sentence('One.'), sentence('Two.')] }, 'take_1');
  assert.equal(opening.role, 'instructor');
  assert.equal(opening.text, 'One. Two.');
  assert.equal(openingTurn({ sentences: [] }, 'take_1'), null);
  assert.equal(openingTurn(null, 'take_1'), null);
});

test('shows the history and the opening message, with jumps once results are set', async () => {
  const history = { turns: [turn(1, 'user', 'Why was bar 3 wrong?'), turn(2, 'instructor', 'x', { sentences: [sentence('Bar 3 sounded wrong.')], mode: 'ai' })] };
  const { root, panel, jumpContext, jumps } = await setup({ getChat: async () => history });
  assert.equal(root.withClass('chat-turn').length, 2);
  panel.setResults({ jumpContext, feedback: { mode: 'ai', sentences: [sentence('Welcome, here is what I heard.')] } });
  const turns = root.withClass('chat-turn');
  assert.equal(turns.length, 3);
  assert.match(turns[0].textContent, /Welcome, here is what I heard\./);
  assert.match(turns[1].textContent, /Why was bar 3 wrong\?/);
  const textButton = root.withClass('sentence-text').find((n) => n.tagName === 'BUTTON' && n.textContent === 'Bar 3 sounded wrong.');
  textButton.click();
  root.withClass('chip').find((chip) => chip.textContent === 'bar 3').click();
  assert.deepEqual(jumps.map((j) => [j.bar, j.time_s]), [[3, 4.5], [3, 4.5]]);
});

test('without results to jump in, or for another take, sentences are plain text', async () => {
  const history = { turns: [turn(2, 'instructor', 'x', { take_id: 'take_9', sentences: [sentence('About another take.')], mode: 'ai' })] };
  const { root, panel, jumpContext } = await setup({ getChat: async () => history });
  assert.equal(root.withClass('chip').length + root.withClass('sentence-text').length, 0);
  panel.setResults({ jumpContext, feedback: null });
  assert.equal(root.withClass('chip').length, 0, 'the turn about take_9 stays plain');
  assert.equal(root.withClass('chat-turn').length, 1);
});

test('a question posts the trimmed text with the take, disables Send while pending, then shows the checked reply', async () => {
  const reply = deferred();
  const sent = [];
  const { root, panel, input, send, jumpContext } = await setup({ sendChat: (...args) => { sent.push(args); return reply.promise; } });
  panel.setResults({ jumpContext, feedback: null });
  const thinking = root.withClass('chat-thinking')[0];
  assert.equal(thinking.hidden, true);
  assert.equal(send.disabled, false);
  input.value = '  Why was bar 3 wrong?  ';
  send.click();
  assert.deepEqual(sent, [['s1', 'Why was bar 3 wrong?', 'take_1']]);
  assert.equal(send.disabled, true);
  assert.equal(thinking.hidden, false);
  send.click();
  assert.equal(sent.length, 1, 'a second click while pending sends nothing');
  reply.resolve(aiReply());
  await settle();
  assert.equal(send.disabled, false);
  assert.equal(thinking.hidden, true);
  assert.equal(input.value, '');
  const instructor = root.withClass('chat-instructor');
  assert.equal(instructor.length, 1);
  assert.equal(root.withClass('badge-checked').length, 1);
  assert.equal(root.withClass('fallback-notice').length, 0);
});

test('Send is disabled until the history has loaded, and stays usable when loading fails', async () => {
  const history = deferred();
  const root = document.createElement('aside');
  const errors = [];
  const panel = createChatPanel(root, { sessionId: 's1', take: 'take_1', getChat: () => history.promise, sendChat: async () => aiReply(), reportError: (e) => errors.push(e.message) });
  assert.equal(root.button('Send').disabled, true);
  history.reject(new Error('Session not found.'));
  await panel.whenReady;
  assert.deepEqual(errors, ['Session not found.']);
  assert.equal(root.button('Send').disabled, false);
});

test('a fallback reply shows the AI instructor unavailable note', async () => {
  const fallback = aiReply('Bar 3 had a wrong note.');
  fallback.instructor_turn.mode = 'fallback';
  const { root, input, send } = await setup({ sendChat: async () => fallback });
  input.value = 'Why?';
  send.click();
  await settle();
  assert.deepEqual(root.texts('fallback-notice'), [FALLBACK_NOTE]);
  assert.equal(FALLBACK_NOTE, 'AI instructor unavailable');
});

test('an empty or too-long message is not sent; the banner gets the reason', async () => {
  const { errors, sent, input, send } = await setup();
  input.value = '   ';
  send.click();
  input.value = 'a'.repeat(MAX_MESSAGE_LENGTH + 1);
  send.click();
  assert.deepEqual(errors, [EMPTY_MESSAGE_ERROR, TOO_LONG_ERROR]);
  assert.equal(sent.length, 0);
  assert.equal(input.value.length, MAX_MESSAGE_LENGTH + 1, 'the typed text stays');
});

test('a 409 or other error reports its message, keeps the text and re-enables Send', async () => {
  const { root, errors, input, send } = await setup({ sendChat: async () => { throw Object.assign(new Error('Instructor is already replying.'), { code: 'wrong_state', status: 409 }); } });
  input.value = 'Why was bar 3 wrong?';
  send.click();
  await settle();
  assert.deepEqual(errors, ['Instructor is already replying.']);
  assert.equal(input.value, 'Why was bar 3 wrong?');
  assert.equal(send.disabled, false);
  assert.equal(root.withClass('chat-user').length, 0, 'nothing is added to the transcript');
});

test('the UI gives up after the reply limit with a plain error and keeps the text', async () => {
  let fire;
  const timers = { setTimer: (fn, ms) => { fire = { fn, ms }; return 1; }, clearTimer() {} };
  const { errors, input, send } = await setup({ sendChat: () => new Promise(() => {}), timers });
  input.value = 'Still there?';
  send.click();
  assert.equal(fire.ms, 35000);
  assert.equal(send.disabled, true);
  fire.fn();
  await settle();
  assert.deepEqual(errors, [TIMEOUT_MESSAGE]);
  assert.equal(input.value, 'Still there?');
  assert.equal(send.disabled, false);
});

test('server text is set as text, never parsed as HTML', async () => {
  const markup = '<img src=x onerror=alert(1)>';
  const { root, input, send } = await setup({ sendChat: async () => aiReply(markup) });
  input.value = markup;
  send.click();
  await settle();
  assert.equal(root.all().filter((n) => n.tagName === 'IMG').length, 0);
  assert.match(root.textContent, /<img src=x onerror=alert\(1\)>/);
});

test('mock mode answers the chat POST with the AI reply, or the fallback reply for take_fallback', () => {
  assert.equal(mockFileFor('GET', '/sessions/s/chat'), 'get_chat');
  assert.equal(mockFileFor('POST', '/sessions/s/chat', { message: 'hi', take_id: 'take_1' }), 'post_chat');
  assert.equal(mockFileFor('POST', '/sessions/s/chat', { message: 'hi', take_id: null }), 'post_chat');
  assert.equal(mockFileFor('POST', '/sessions/s/chat', { message: 'hi', take_id: 'take_fallback' }), 'post_chat_fallback');
  const read = (name) => JSON.parse(readFileSync(new URL(`../mock/${name}.json`, import.meta.url)));
  assert.equal(read('post_chat').instructor_turn.mode, 'ai');
  assert.equal(read('post_chat_fallback').instructor_turn.mode, 'fallback');
});

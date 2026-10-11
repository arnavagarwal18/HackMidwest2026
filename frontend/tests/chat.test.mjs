// Instructor chat panel logic with a fake DOM (no browser). Run: node --test frontend/tests/chat.test.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { installFakeDom, settle } from './fake_dom.mjs';

const { setWide, listenerCount } = installFakeDom();
const { MAX_MESSAGE_LENGTH, EMPTY_MESSAGE_ERROR, TOO_LONG_ERROR, TIMEOUT_MESSAGE, FALLBACK_NOTE, validateMessage, withTimeout, openingTurn, suggestedQuestions } =
  await import('../js/chat/model.js');
const { createChatPanel, OPEN_EVENT } = await import('../js/chat/panel.js');
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

// Builds a panel with fakes; options.getChat / sendChat override the defaults, options.wide builds it on a wide (docked) screen.
async function setup(options = {}) {
  press('Escape'); // shuts the sheets earlier tests left open, so their document listeners do not leak into this test
  setWide(Boolean(options.wide));
  const root = document.createElement('div');
  document.body.replaceChildren(root); // a panel only answers 'coach:open' while it is on the page; earlier tests' panels leave it
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

const chips = (root) => root.withClass('coach-chip');
const sheetOf = (root) => root.withClass('coach-sheet')[0];
const press = (key, extra = {}) => document.dispatch('keydown', { key, preventDefault() {}, stopPropagation() {}, ...extra }); // keys are heard on the document
const browserDropsFocus = () => { document.activeElement = document.body; }; // what a browser does when the focused control is disabled

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

test('openingTurn is the first feedback sentence as an instructor turn, or null without any', () => {
  const opening = openingTurn({ mode: 'ai', sentences: [sentence('One.'), sentence('Two.')] }, 'take_1');
  assert.equal(opening.role, 'instructor');
  assert.equal(opening.text, 'One.', 'the page shows the rest');
  assert.equal(opening.sentences.length, 1);
  assert.equal(openingTurn({ sentences: [] }, 'take_1'), null);
  assert.equal(openingTurn(null, 'take_1'), null);
});

test('shows the history and the opening message, with jumps once results are set', async () => {
  const history = { turns: [turn(1, 'user', 'Why was bar 3 wrong?'), turn(2, 'instructor', 'x', { sentences: [sentence('Bar 3 sounded wrong.')], mode: 'ai' })] };
  const { root, panel, jumpContext, jumps } = await setup({ getChat: async () => history });
  assert.equal(root.withClass('chat-turn').length, 2);
  assert.equal(chips(root).length, 0, 'a take that already has questions asked shows no suggestions');
  panel.setResults({ jumpContext, feedback: { mode: 'ai', sentences: [sentence('Welcome, here is what I heard.')] } });
  const turns = root.withClass('chat-turn');
  assert.equal(turns.length, 3);
  assert.match(turns[0].textContent, /Welcome, here is what I heard\./);
  assert.match(turns[1].textContent, /Why was bar 3 wrong\?/);
  const textButton = root.withClass('sentence-text').find((n) => n.tagName === 'BUTTON' && n.textContent === 'Bar 3 sounded wrong.');
  textButton.click();
  assert.deepEqual(jumps.map((j) => [j.bar, j.time_s]), [[3, 4.5]]);
  assert.equal(root.withClass('chip').length, 0, 'no per-sentence bar chips: each reference shows once');
  assert.equal(root.withClass('badge').length, 0, 'no badges');
});

test('without results to jump in, or for another take, sentences are plain text', async () => {
  const history = { turns: [turn(2, 'instructor', 'x', { take_id: 'take_9', sentences: [sentence('About another take.')], mode: 'ai' })] };
  const { root, panel, jumpContext } = await setup({ getChat: async () => history });
  assert.equal(root.withClass('coach-link').length, 0);
  panel.setResults({ jumpContext, feedback: null });
  assert.equal(root.withClass('coach-link').length, 0, 'the turn about take_9 stays plain');
  assert.equal(root.withClass('chat-turn').length, 1);
});

test('a question posts the trimmed text with the take, disables Send while pending, then shows the reply', async () => {
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
  assert.equal(root.withClass('badge-checked').length, 0, 'no checked badge');
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

test('the panel is a closed dialog sheet until coach:open; Close and Escape shut it and focus goes in and back', async () => {
  const { root } = await setup();
  const sheet = sheetOf(root);
  const [backdrop] = root.withClass('coach-backdrop');
  assert.equal(sheet.hidden, true, 'closed by default');
  assert.equal(backdrop.hidden, true);
  assert.equal(sheet.attributes.role, 'dialog');
  assert.equal(sheet.attributes['aria-modal'], 'true');
  const opener = document.createElement('button');
  opener.focus();
  document.dispatch(OPEN_EVENT);
  assert.equal(sheet.hidden, false);
  assert.equal(backdrop.hidden, false);
  assert.ok(document.activeElement === sheet, 'focus moves into the sheet');
  root.button('Close').click();
  assert.equal(sheet.hidden, true);
  assert.ok(document.activeElement === opener, 'focus goes back to where it was');
  document.dispatch(OPEN_EVENT);
  press('Escape');
  assert.equal(sheet.hidden, true, 'Escape closes');
  document.dispatch(OPEN_EVENT);
  backdrop.click();
  assert.equal(sheet.hidden, true, 'a tap on the backdrop closes');
});

test('the grabber toggles half and full height on a tap, and a drag up expands, down shrinks and then closes', async () => {
  const { root } = await setup();
  const sheet = sheetOf(root);
  const [grabber] = root.withClass('coach-grabber');
  document.dispatch(OPEN_EVENT);
  assert.equal(sheet.attributes['data-size'], 'half', 'opens at half height');
  grabber.click();
  assert.equal(sheet.attributes['data-size'], 'full');
  assert.equal(grabber.attributes['aria-expanded'], 'true');
  grabber.click();
  assert.equal(sheet.attributes['data-size'], 'half');
  const drag = (from, to) => { grabber.listeners.pointerdown[0]({ clientY: from }); grabber.listeners.pointerup[0]({ clientY: to }); grabber.click(); };
  drag(300, 200);
  assert.equal(sheet.attributes['data-size'], 'full', 'a drag up expands (and its click does not toggle back)');
  drag(200, 300);
  assert.equal(sheet.attributes['data-size'], 'half', 'a drag down shrinks');
  drag(200, 300);
  assert.equal(sheet.hidden, true, 'a drag down from half closes');
});

test('Tab stays inside the open sheet', async () => {
  const { root } = await setup();
  const sheet = sheetOf(root);
  const focusables = [root.withClass('coach-grabber')[0], root.button('Close'), root.withClass('chat-input')[0], root.button('Send')];
  sheet.querySelectorAll = () => focusables;
  document.dispatch(OPEN_EVENT);
  let prevented = false;
  focusables.at(-1).focus();
  press('Tab', { preventDefault: () => { prevented = true; } });
  assert.ok(document.activeElement === focusables[0], 'Tab from the last control wraps to the first');
  assert.equal(prevented, true);
  press('Tab', { shiftKey: true });
  assert.ok(document.activeElement === focusables.at(-1), 'shift+Tab from the first control goes to the last');
});

test('Escape and Tab still work after Send disables the box and the browser drops focus; focus comes back after the reply', async () => {
  const reply = deferred();
  const { root, input, send } = await setup({ sendChat: () => reply.promise });
  const sheet = sheetOf(root);
  const focusables = [root.withClass('coach-grabber')[0], root.button('Close'), input, send];
  sheet.querySelectorAll = () => focusables;
  document.dispatch(OPEN_EVENT);
  input.focus();
  input.value = 'Why?';
  send.click();
  browserDropsFocus();
  press('Tab');
  assert.ok(document.activeElement === focusables[0], 'Tab from the page behind goes back into the sheet');
  browserDropsFocus();
  press('Tab', { shiftKey: true });
  assert.ok(document.activeElement === focusables.at(-1), 'shift+Tab from the page behind goes to the last control');
  browserDropsFocus();
  reply.resolve(aiReply());
  await settle();
  assert.ok(document.activeElement === input, 'focus returns to the question box after the reply');
  browserDropsFocus();
  press('Escape');
  assert.equal(sheet.hidden, true, 'Escape works with focus on the page behind');
});

test('Escape works while a reply is pending, and focus returns to the box after an error', async () => {
  const reply = deferred();
  const { root, input, send } = await setup({ sendChat: () => reply.promise });
  document.dispatch(OPEN_EVENT);
  input.focus();
  input.value = 'Why?';
  send.click();
  browserDropsFocus();
  reply.reject(new Error('Offline'));
  await settle();
  assert.ok(document.activeElement === input, 'focus returns to the box after an error');
  browserDropsFocus();
  press('Escape');
  assert.equal(sheetOf(root).hidden, true);
});

test('focus that lands outside the open sheet is moved back in, and a closed sheet stops listening', async () => {
  const { root } = await setup();
  const sheet = sheetOf(root);
  const outside = document.createElement('button');
  document.dispatch(OPEN_EVENT);
  outside.focus();
  document.dispatch('focusin', { target: outside });
  assert.ok(document.activeElement === sheet, 'focus is pulled back into the sheet');
  document.dispatch('focusin', { target: root.button('Close') });
  assert.ok(document.activeElement === sheet, 'focus inside the sheet is left alone');
  root.button('Close').click();
  assert.equal(document.count('keydown'), 0, 'no key listener stays behind');
  assert.equal(document.count('focusin'), 0, 'no focus listener stays behind');
});

test('a panel that left the page stops answering coach:open', async () => {
  const { root } = await setup();
  root.remove();
  document.dispatch(OPEN_EVENT);
  assert.equal(sheetOf(root).hidden, true);
  assert.equal(document.count(OPEN_EVENT), 0, 'its listener is gone (as are those of earlier tests panels)');
});

test('suggestedQuestions: pitch, plan and one about the weakest bar when the feedback names one', () => {
  const feedback = { tier1: [{ jump: { bar: 4 } }], sentences: [sentence('x', { jump: { bar: 3, time_s: 1 } })] };
  assert.deepEqual(suggestedQuestions(feedback), ['Fix my pitch', 'Practice plan', 'Why was bar 4 off?'], 'the first problem names the weakest bar');
  assert.deepEqual(suggestedQuestions({ sentences: [sentence('x', { jump: { bar: 3, time_s: 1 } })] }).at(-1), 'Why was bar 3 off?');
  assert.deepEqual(suggestedQuestions({ sentences: [sentence('x', { jump: null })] }), ['Fix my pitch', 'Practice plan']);
  assert.deepEqual(suggestedQuestions(null), ['Fix my pitch', 'Practice plan']);
});

test('on open the sheet shows the first feedback sentence once and chips; a chip sends its question and then the chips go', async () => {
  const { root, panel, sent, input, jumpContext } = await setup();
  const feedback = { mode: 'ai', tier1: [{ jump: { bar: 3 } }], sentences: [sentence('First line.'), sentence('Second line.')] };
  panel.setResults({ jumpContext, feedback });
  document.dispatch(OPEN_EVENT);
  assert.deepEqual(root.texts('sentence-text'), ['First line.'], 'the page has the rest; nothing is repeated');
  assert.deepEqual(chips(root).map((chip) => chip.textContent), ['Fix my pitch', 'Practice plan', 'Why was bar 3 off?']);
  input.value = 'half typed';
  chips(root)[2].click();
  assert.deepEqual(sent, [['s1', 'Why was bar 3 off?', 'take_1']]);
  await settle();
  assert.equal(input.value, 'half typed', 'a chip leaves what was typed alone');
  assert.equal(chips(root).length, 0, 'the chips make way once a question was asked');
  assert.equal(root.withClass('chat-user').length, 1);
});

test('chips are disabled while a reply is pending', async () => {
  const reply = deferred();
  const { root, panel, jumpContext } = await setup({ sendChat: () => reply.promise });
  panel.setResults({ jumpContext, feedback: null });
  chips(root)[0].click();
  assert.ok(chips(root).every((chip) => chip.disabled));
  chips(root)[1].click(); // does nothing
  reply.resolve(aiReply());
  await settle();
});

test('a bar reference closes the sheet and then jumps', async () => {
  const { root, panel, jumpContext, jumps } = await setup();
  panel.setResults({ jumpContext, feedback: { mode: 'ai', sentences: [sentence('Bar 3 sounded wrong.')] } });
  document.dispatch(OPEN_EVENT);
  root.withClass('coach-link')[0].click();
  assert.equal(sheetOf(root).hidden, true, 'the bar is in view, not behind the sheet');
  assert.deepEqual(jumps.map((j) => j.bar), [3]);
});

// ---- docked mode (wide screens) ----

test('on a wide screen the panel is a visible, non-modal complementary region with a Collapse button and no scrim', async () => {
  const { root } = await setup({ wide: true });
  const sheet = sheetOf(root);
  assert.equal(sheet.hidden, false, 'visible without coach:open');
  assert.equal(sheet.attributes.role, 'complementary');
  assert.equal(sheet.attributes['aria-label'], 'Coach');
  assert.equal(sheet.attributes['aria-modal'], undefined);
  assert.equal(root.withClass('coach-backdrop')[0].hidden, true, 'no scrim');
  assert.equal(root.withClass('coach-grabber')[0].hidden, true, 'no grabber');
  assert.ok(sheet.className.split(' ').includes('is-docked'));
  assert.equal(root.button('Close'), undefined);
  assert.ok(root.button('Collapse'));
  assert.equal(document.count('keydown'), 0);
  assert.equal(document.count('focusin'), 0);
  assert.notEqual(document.activeElement, sheet, 'focus is not moved into it on load');
});

test('docked: Escape does nothing and focus is never moved in automatically', async () => {
  const { root, input } = await setup({ wide: true });
  const outside = document.createElement('button');
  outside.focus();
  press('Escape');
  assert.equal(sheetOf(root).hidden, false);
  document.dispatch('focusin', { target: outside });
  assert.ok(document.activeElement === outside, 'focus on the page is not pulled back');
  assert.notEqual(document.activeElement, input);
});

test('docked: no focus trap, Tab is left alone', async () => {
  const { root } = await setup({ wide: true });
  sheetOf(root).querySelectorAll = () => [root.button('Collapse'), root.withClass('chat-input')[0], root.button('Send')];
  root.button('Send').focus();
  let prevented = false;
  press('Tab', { preventDefault: () => { prevented = true; } });
  assert.equal(prevented, false);
  assert.ok(document.activeElement === root.button('Send'));
});

test('docked: Collapse hides the panel and coach:open expands it again and focuses the question box', async () => {
  const { root, input, panel } = await setup({ wide: true });
  root.button('Collapse').click();
  assert.equal(sheetOf(root).hidden, true);
  assert.equal(panel.isOpen(), false);
  document.dispatch(OPEN_EVENT);
  assert.equal(sheetOf(root).hidden, false);
  assert.equal(panel.isOpen(), true);
  assert.ok(document.activeElement === input, 'focus goes to the input');
  assert.equal(document.count('keydown'), 0, 'still no modal listeners');
});

test('docked: coach:open on the visible panel focuses the question box', async () => {
  const { input } = await setup({ wide: true });
  document.dispatch(OPEN_EVENT);
  assert.ok(document.activeElement === input);
});

test('docked: a bar link jumps and does not close the panel', async () => {
  const { root, panel, jumpContext, jumps } = await setup({ wide: true });
  panel.setResults({ jumpContext, feedback: { mode: 'ai', sentences: [sentence('Bar 3 sounded wrong.')] } });
  root.withClass('coach-link')[0].click();
  assert.equal(sheetOf(root).hidden, false, 'the panel stays');
  assert.deepEqual(jumps.map((j) => j.bar), [3]);
});

test('docked: a reply that disables the box gives focus back only if it was in the panel', async () => {
  const reply = deferred();
  const { input, send } = await setup({ wide: true, sendChat: () => reply.promise });
  const outside = document.createElement('button');
  input.focus();
  input.value = 'Why?';
  send.click();
  browserDropsFocus();
  reply.resolve(aiReply());
  await settle();
  assert.ok(document.activeElement === input, 'focus was in the panel, so it returns to the box');

  const second = deferred();
  const again = await setup({ wide: true, sendChat: () => second.promise });
  again.input.value = 'Why?';
  outside.focus();
  again.send.click();
  second.resolve(aiReply());
  await settle();
  assert.ok(document.activeElement === outside, 'focus was elsewhere, so it is left there');
});

test('widening an open sheet docks it: the scrim and the document listeners are gone, and the panel shows', async () => {
  const { root } = await setup();
  const sheet = sheetOf(root);
  document.dispatch(OPEN_EVENT);
  assert.equal(document.count('keydown'), 1);
  setWide(true);
  assert.equal(sheet.hidden, false);
  assert.equal(sheet.attributes.role, 'complementary');
  assert.equal(sheet.attributes['aria-modal'], undefined);
  assert.equal(root.withClass('coach-backdrop')[0].hidden, true, 'no stuck scrim');
  assert.equal(document.count('keydown'), 0);
  assert.equal(document.count('focusin'), 0);
  press('Escape');
  assert.equal(sheet.hidden, false);
});

test('narrowing a docked panel returns to a closed modal sheet that works as before', async () => {
  const { root } = await setup({ wide: true });
  const sheet = sheetOf(root);
  setWide(false);
  assert.equal(sheet.hidden, true, 'no modal appears unasked');
  assert.equal(sheet.attributes.role, 'dialog');
  assert.equal(sheet.attributes['aria-modal'], 'true');
  assert.equal(root.withClass('coach-grabber')[0].hidden, false);
  assert.ok(root.button('Close'));
  document.dispatch(OPEN_EVENT);
  assert.equal(root.withClass('coach-backdrop')[0].hidden, false);
  assert.ok(document.activeElement === sheet);
  press('Escape');
  assert.equal(sheet.hidden, true);
  assert.equal(document.count('keydown'), 0);
});

test('switching width back and forth leaves no listeners, and a panel that left the page stops listening to the width', async () => {
  const { root } = await setup();
  document.dispatch(OPEN_EVENT);
  setWide(true);
  setWide(false);
  document.dispatch(OPEN_EVENT);
  setWide(true);
  assert.equal(document.count('keydown'), 0);
  assert.equal(document.count('focusin'), 0);
  assert.equal(listenerCount(), 1, 'one width listener for the one live panel (earlier tests panels already left)');
  root.remove();
  setWide(false);
  assert.equal(listenerCount(), 0, 'a panel that left the page removes its width listener');
});

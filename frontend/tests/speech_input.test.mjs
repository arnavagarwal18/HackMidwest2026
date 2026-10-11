// Voice input for the coach's question box, with a mocked recognition object (no browser). Run: node --test frontend/tests/speech_input.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { installFakeDom, settle } from './fake_dom.mjs';

installFakeDom();
const { createSpeechInput, ERROR_MESSAGES, UNSUPPORTED_MESSAGE, INSECURE_MESSAGE, LANGUAGE } = await import('../js/chat/speech_input.js');
const { createChatPanel } = await import('../js/chat/panel.js');

class FakeRecognition {
  static instances = [];
  constructor() { this.started = false; this.stopped = false; FakeRecognition.instances.push(this); }
  start() { if (FakeRecognition.startError) throw FakeRecognition.startError; this.started = true; }
  abort() { this.aborted = true; }
  stop() { this.stopped = true; this.onend?.(); }
  say(parts) { this.onresult?.({ results: parts.map((transcript) => [{ transcript }]) }); }
  fail(error) { this.onerror?.({ error }); this.onend?.(); }
}

function setup({ value = '', win = { SpeechRecognition: FakeRecognition, isSecureContext: true } } = {}) {
  FakeRecognition.instances = [];
  FakeRecognition.startError = null;
  const input = { value };
  const errors = [];
  const warnings = [];
  const speech = createSpeechInput({ input, reportError: (err) => errors.push(err.message), win, logger: { warn: (...args) => warnings.push(args) } });
  return { input, errors, warnings, speech, mic: speech.element, current: () => FakeRecognition.instances.at(-1) };
}

test('supported: click starts listening in en-US with interim results, click again stops', () => {
  const { mic, current } = setup();
  assert.equal(mic.attributes['aria-disabled'], undefined);
  mic.click();
  assert.equal(current().lang, LANGUAGE);
  assert.equal(current().interimResults, true);
  assert.ok(current().started);
  assert.equal(mic.attributes['aria-pressed'], 'true');
  assert.ok(mic.className.includes('is-recording'));
  assert.equal(mic.textContent, 'Stop');
  mic.click();
  assert.ok(FakeRecognition.instances[0].stopped);
  assert.equal(mic.attributes['aria-pressed'], 'false');
  assert.ok(!mic.className.includes('is-recording'));
  assert.equal(mic.textContent, 'Speak');
});

test('the webkit-prefixed constructor is used when the standard one is missing', () => {
  const { mic, current } = setup({ win: { webkitSpeechRecognition: FakeRecognition, isSecureContext: true } });
  mic.click();
  assert.ok(current().started);
});

test('unsupported browser: the button explains why, and clicking reports it without starting anything', () => {
  const { mic, errors, warnings } = setup({ win: { isSecureContext: true } });
  assert.equal(mic.attributes['aria-disabled'], 'true');
  assert.equal(mic.attributes.title, UNSUPPORTED_MESSAGE);
  mic.click();
  assert.deepEqual(errors, [UNSUPPORTED_MESSAGE]);
  assert.equal(warnings.length, 1, 'the refusal is logged');
  assert.equal(FakeRecognition.instances.length, 0);
});

test('insecure context: the button explains it needs HTTPS or localhost', () => {
  const { mic, errors } = setup({ win: { SpeechRecognition: FakeRecognition, isSecureContext: false } });
  assert.equal(mic.attributes['aria-disabled'], 'true');
  assert.equal(mic.attributes.title, INSECURE_MESSAGE);
  mic.click();
  assert.deepEqual(errors, [INSECURE_MESSAGE]);
  assert.equal(FakeRecognition.instances.length, 0);
});

test('interim text then the final result fill the box after what was already typed, and nothing is sent', () => {
  const { input, mic, current, errors } = setup({ value: 'How is my ' });
  mic.click();
  current().say(['breath']);
  assert.equal(input.value, 'How is my breath');
  current().say(['breath support']);
  assert.equal(input.value, 'How is my breath support', 'interim text is replaced, not piled up');
  current().say(['breath support ', 'on high notes']);
  assert.equal(input.value, 'How is my breath support on high notes');
  mic.click();
  assert.equal(input.value, 'How is my breath support on high notes', 'stopping keeps the text for review');
  assert.deepEqual(errors, []);
});

test('speaking into an empty box adds no leading space', () => {
  const { input, mic, current } = setup();
  mic.click();
  current().say(['hello there']);
  assert.equal(input.value, 'hello there');
});

for (const code of ['not-allowed', 'no-speech', 'network']) {
  test(`${code} error: an actionable message, a console warning, and the button resets`, () => {
    const { mic, errors, warnings, current } = setup({ value: 'typed' });
    mic.click();
    current().fail(code);
    assert.deepEqual(errors, [ERROR_MESSAGES[code]]);
    assert.match(errors[0], /try again|type/i);
    assert.equal(warnings.length, 1);
    assert.equal(mic.attributes['aria-pressed'], 'false');
    assert.equal(mic.textContent, 'Speak');
    mic.click();
    assert.equal(FakeRecognition.instances.length, 2, 'it can be started again');
  });
}

test('an unknown error code still gets a message that names the code', () => {
  const { mic, errors, current } = setup();
  mic.click();
  current().fail('something-new');
  assert.match(errors[0], /something-new/);
});

test('an error leaves the typed text alone', () => {
  const { input, mic, current } = setup({ value: 'typed' });
  mic.click();
  current().fail('no-speech');
  assert.equal(input.value, 'typed');
});

test('a start() that throws is reported, logged and leaves the button ready', () => {
  const { mic, errors, warnings } = setup();
  FakeRecognition.startError = new Error('already started');
  mic.click();
  assert.equal(errors.length, 1);
  assert.equal(warnings.length, 1);
  assert.equal(mic.attributes['aria-pressed'], 'false');
});

test('cancel (on Send) aborts listening, resets the button, and ignores a late final result', () => {
  const { input, mic, speech, current, errors } = setup({ value: 'Why' });
  mic.click();
  const recognition = current();
  recognition.say(['was it flat']);
  input.value = ''; // what the panel does after a successful send
  speech.cancel();
  assert.ok(recognition.aborted);
  assert.equal(mic.attributes['aria-pressed'], 'false');
  assert.equal(mic.textContent, 'Speak');
  recognition.say(['was it flat today']); // a late final result
  recognition.fail('aborted');
  recognition.onend?.();
  assert.equal(input.value, '', 'the sent text does not come back');
  assert.deepEqual(errors, []);
  mic.click();
  assert.equal(FakeRecognition.instances.length, 2, 'a new session can start');
});

test('cancel with nothing listening does nothing', () => {
  const { speech, mic } = setup();
  speech.cancel();
  assert.equal(mic.attributes['aria-pressed'], 'false');
});

test('in the panel: Send cancels listening and a late result does not refill the cleared box', async () => {
  const sent = [];
  FakeRecognition.instances = [];
  FakeRecognition.startError = null;
  window.SpeechRecognition = FakeRecognition;
  window.isSecureContext = true;
  const root = document.createElement('div');
  document.body.replaceChildren(root);
  const reply = { user_turn: { turn: 1, role: 'user', text: 'x', take_id: 'take_1' }, instructor_turn: { turn: 2, role: 'instructor', text: 'ok', take_id: 'take_1', sentences: null, mode: 'ai' } };
  const panel = createChatPanel(root, { sessionId: 's1', take: 'take_1', getChat: async () => ({ turns: [] }), sendChat: async (...args) => { sent.push(args); return reply; }, reportError: () => {} });
  await panel.whenReady;
  const mic = root.withClass('chat-mic')[0];
  const input = root.withClass('chat-input')[0];
  input.value = '';
  mic.click();
  const recognition = FakeRecognition.instances[0];
  recognition.say(['and bar four']);
  root.button('Send').click();
  assert.ok(recognition.aborted);
  assert.equal(mic.attributes['aria-pressed'], 'false');
  await settle();
  assert.equal(sent.length, 1);
  assert.equal(input.value, '', 'cleared after a successful send');
  recognition.say(['and bar four please']);
  assert.equal(input.value, '', 'a late result is ignored');
  delete window.SpeechRecognition;
});

test('in the panel: the mic sits in the question form, fills the box, and never sends', async () => {
  const sent = [];
  const errors = [];
  FakeRecognition.instances = [];
  FakeRecognition.startError = null;
  window.SpeechRecognition = FakeRecognition;
  window.isSecureContext = true;
  const root = document.createElement('div');
  document.body.replaceChildren(root);
  const panel = createChatPanel(root, { sessionId: 's1', take: 'take_1', getChat: async () => ({ turns: [] }), sendChat: async (...args) => { sent.push(args); }, reportError: (err) => errors.push(err.message) });
  await panel.whenReady;
  const mic = root.withClass('chat-mic')[0];
  const input = root.withClass('chat-input')[0];
  input.value = ''; // a real textarea starts empty; the fake node has no value
  mic.click();
  FakeRecognition.instances[0].say(['why was bar three flat']);
  assert.equal(input.value, 'why was bar three flat');
  assert.deepEqual(sent, [], 'review comes before Send');
  FakeRecognition.instances[0].fail('network');
  assert.deepEqual(errors, [ERROR_MESSAGES.network]);
  delete window.SpeechRecognition;
});

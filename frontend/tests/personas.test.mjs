// Coach style (persona) switch and picker with a fake DOM and mock mode (no browser, no back end).
// Run: node --test frontend/tests/personas.test.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { installFakeDom, settle } from './fake_dom.mjs';

const dom = installFakeDom();
dom.window.location.search = '?mock=1';
const stored = new Map();
dom.window.localStorage = { getItem: (key) => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value), removeItem: (key) => stored.delete(key) };
globalThis.fetch = async (url) => ({ ok: true, status: 200, json: async () => JSON.parse(readFileSync(new URL(`../${url}`, import.meta.url), 'utf8')) });

const { state } = await import('../js/state.js');
const { ApiError } = await import('../js/http.js');
const { orderPersonas, presetTempo, personaLabel, FALLBACK_COACH_TEXT, FEEDBACK_PENDING_TEXT } = await import('../js/persona/model.js');
const { waitForNewFeedback, SLOW_FEEDBACK_TEXT } = await import('../js/persona/pending_feedback.js');
const { loadPersonas } = await import('../js/persona/load.js');
const { createSegmented } = await import('../js/persona/segmented.js');
const { savePersona } = await import('../js/persona/change.js');
const { createMenu } = await import('../js/persona/menu.js');
const { createCoachSwitch } = await import('../js/persona/coach_switch.js');
const { createPersonaPicker } = await import('../js/persona/picker.js');
const { renderCoachedBy } = await import('../js/persona/coached_by.js');
const { createChatPanel } = await import('../js/chat/panel.js');
const { mockResponse } = await import('../js/mock.js');
const { resumeSession } = await import('../js/resume.js');

const FIXTURE = JSON.parse(readFileSync(new URL('../mock/get_personas.json', import.meta.url), 'utf8'));
const PERSONAS = orderPersonas(FIXTURE.personas, FIXTURE.default);
const turn = (n, role, extra = {}) => ({ turn: n, role, text: 'x', take_id: 'take_1', sentences: null, mode: null, ...extra });

function deferred() {
  const d = {};
  d.promise = new Promise((resolve, reject) => { d.resolve = resolve; d.reject = reject; });
  return d;
}

const segments = (root) => root.withClass('segment');
const chosen = (root) => segments(root).filter((s) => s.attributes['aria-pressed'] === 'true').map((s) => s.textContent);
const clickSegment = (root, label) => segments(root).find((s) => s.textContent === label).click();

// The coach menu: the button, its popup items, and picking an option by its label.
const trigger = (root) => root.withClass('coach-menu-button')[0];
const items = (root) => root.withClass('coach-menu-item');
const itemLabels = (root) => items(root).map((item) => item.children[0].textContent);
const checked = (root) => items(root).filter((item) => item.attributes['aria-checked'] === 'true').map((item) => item.children[0].textContent);
const pick = (root, label) => { trigger(root).click(); items(root).find((item) => item.children[0].textContent === label).click(); };
const key = (node, name) => { const event = { key: name, prevented: false, preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; } }; node.listeners.keydown.forEach((fn) => fn(event)); return event; };
const menuOpen = (root) => !root.withClass('coach-menu-list')[0].hidden;

// A coach switch over fakes. Calls are recorded in `log` in the order they happen.
function setupSwitch({ patch, rerun, waitForFeedback } = {}) {
  const log = [];
  const errors = [];
  const drawn = [];
  const coach = createCoachSwitch({
    personas: PERSONAS,
    sessionId: 's1',
    take: 'take_1',
    savePersona: (sessionId, id) => savePersona(sessionId, id, async (...args) => { log.push(['patch', ...args]); return patch ? patch(...args) : { session_id: 's1', persona: args[1].persona }; }),
    rerunFeedback: async (...args) => { log.push(['rerun', ...args]); return rerun ? rerun(...args) : { id: 'fb_2', mode: 'ai', persona: 'concert' }; },
    waitForFeedback: async (previousId) => { log.push(['wait', previousId]); return waitForFeedback ? waitForFeedback(previousId) : null; },
    currentFeedbackId: () => 'fb_1',
    onFeedback: (body) => drawn.push(body),
    onCoachChanged: (label) => log.push(['coaching', label]),
    reportError: (err) => errors.push(err.message),
  });
  return { coach, log, errors, drawn, root: coach.element, status: coach.status };
}

test.beforeEach(() => {
  state.persona = 'standard';
  state.personas = null;
});

test('the options are Standard first, then the back end order; a persona names its label and presets a tempo', () => {
  assert.deepEqual(orderPersonas([{ id: 'concert' }, { id: 'standard' }, { id: 'beginner' }], 'standard').map((p) => p.id), ['standard', 'concert', 'beginner']);
  assert.deepEqual(PERSONAS.map((p) => p.label), ['Standard', 'Concert', 'Marching', 'Beginner']);
  assert.equal(personaLabel(PERSONAS, 'marching'), 'Marching');
  assert.equal(personaLabel(PERSONAS, 'unknown_one'), 'unknown_one');
  const byId = (id) => PERSONAS.find((p) => p.id === id);
  assert.equal(presetTempo(byId('standard'), 96), 96);
  assert.equal(presetTempo(byId('beginner'), 96), 67, '0.7 x 96, rounded');
  assert.equal(presetTempo(byId('marching'), 96), 120, 'a fixed tempo ignores the written one');
  assert.equal(presetTempo(byId('beginner'), 40), 30, 'never below the allowed range');
  assert.equal(presetTempo({ tempo: {} }, 96), null);
  assert.equal(presetTempo({ tempo: { kind: 'other', value: 2 } }, 96), null, 'an unknown kind is left alone');
  assert.equal(presetTempo(null, 96), null);
});

test('the fixture carries the four personas with their hints and tempo rules', () => {
  assert.equal(FIXTURE.default, 'standard');
  assert.deepEqual(FIXTURE.personas.map((p) => [p.id, p.tempo]), [
    ['standard', { kind: 'written_factor', value: 1 }], ['concert', { kind: 'written_factor', value: 1 }],
    ['marching', { kind: 'fixed_bpm', value: 120 }], ['beginner', { kind: 'written_factor', value: 0.7 }],
  ]);
  assert.equal(FIXTURE.personas[2].hint, 'Marching band, pep band and field shows');
});

test('loadPersonas reads the list once and caches it; a failure gives null and a console record', async () => {
  const personas = await loadPersonas();
  assert.deepEqual(personas.map((p) => p.id), ['standard', 'concert', 'marching', 'beginner']);
  assert.equal(state.personas, personas);
  assert.equal(await loadPersonas(), personas, 'the second call answers from the cache');

  state.personas = null;
  const realFetch = globalThis.fetch;
  const logged = [];
  const realError = console.error;
  console.error = (...args) => logged.push(args[0]);
  globalThis.fetch = async () => ({ ok: false, status: 404, json: async () => ({ error: { code: 'not_found', message: 'Not found.' } }) });
  try {
    assert.equal(await loadPersonas(), null, 'a 404 hides the controls');
    assert.equal(state.personas, null);
    assert.ok(logged.some((message) => /coach styles could not be read/.test(message)), 'the failure is logged');
  } finally {
    globalThis.fetch = realFetch;
    console.error = realError;
  }
});

test('the segmented control shows the given options in order, moves on a click and tells the caller once', () => {
  const picked = [];
  const control = createSegmented({ label: 'Coach style', options: PERSONAS, value: 'standard', onChange: (id) => picked.push(id) });
  assert.deepEqual(segments(control.element).map((s) => s.textContent), ['Standard', 'Concert', 'Marching', 'Beginner']);
  assert.deepEqual(chosen(control.element), ['Standard']);
  clickSegment(control.element, 'Concert');
  clickSegment(control.element, 'Concert');
  assert.deepEqual(picked, ['concert'], 'choosing the chosen option again does nothing');
  assert.deepEqual(chosen(control.element), ['Concert']);
  control.setValue('beginner');
  assert.deepEqual(chosen(control.element), ['Beginner']);
  assert.deepEqual(picked, ['concert'], 'setValue does not call back');
  control.setDisabled(true);
  assert.ok(segments(control.element).every((s) => s.disabled));
});

test('arrow keys move the choice', () => {
  const picked = [];
  const control = createSegmented({ label: 'x', options: PERSONAS, value: 'standard', onChange: (id) => picked.push(id) });
  segments(control.element)[0].listeners.keydown[0]({ key: 'ArrowRight', preventDefault() {} });
  segments(control.element)[1].listeners.keydown[0]({ key: 'ArrowLeft', preventDefault() {} });
  assert.deepEqual(picked, ['concert', 'standard']);
});

test('changing the coach style saves it, builds the feedback again, and keeps the switch disabled until it arrives', async () => {
  const rerun = deferred();
  const { coach, log, drawn, root } = setupSwitch({ rerun: () => rerun.promise });
  pick(root, 'Concert');
  await settle();
  assert.deepEqual(log, [['patch', 's1', { persona: 'concert' }], ['coaching', 'Concert'], ['rerun', 's1', 'take_1']]);
  assert.equal(trigger(root).disabled, true, 'disabled while the feedback is being made');
  assert.equal(trigger(root).textContent, 'Coach: Concert ▾');
  assert.equal(state.persona, 'concert');
  rerun.resolve({ id: 'fb_2', mode: 'ai' });
  await settle();
  assert.deepEqual(drawn, [{ id: 'fb_2', mode: 'ai' }]);
  assert.equal(trigger(root).disabled, true, 'still disabled until the screen has the new feedback');
  coach.enable();
  assert.equal(trigger(root).disabled, false);
});

test('a failed save puts the control back, shows the error and builds nothing', async () => {
  const { log, errors, root } = setupSwitch({ patch: async () => { throw new ApiError('boom', 'The coach style was not saved.', 500); } });
  pick(root, 'Marching');
  await settle();
  assert.deepEqual(errors, ['The coach style was not saved.']);
  assert.deepEqual(log.map((entry) => entry[0]), ['patch'], 'no re-run, no "Now coaching" line');
  assert.deepEqual(checked(root), ['Standard']);
  assert.equal(trigger(root).textContent, 'Coach: Standard ▾');
  assert.equal(state.persona, 'standard');
  assert.equal(trigger(root).disabled, false);
});

const stillRunning = async () => { throw new ApiError('wrong_state', 'Feedback is in progress.', 409); };

test('a 409 on the re-run waits for the running feedback, then draws the record that differs from the one shown', async () => {
  const realError = console.error;
  console.error = () => {};
  try {
    const arrives = deferred();
    const { coach, log, errors, drawn, root, status } = setupSwitch({ rerun: stillRunning, waitForFeedback: () => arrives.promise });
    pick(root, 'Beginner');
    await settle();
    assert.equal(trigger(root).disabled, true, 'disabled while waiting');
    const pending = status.withClass('coach-pending')[0];
    assert.equal(pending.hidden, false);
    assert.equal(pending.textContent, FEEDBACK_PENDING_TEXT);
    assert.deepEqual(log.at(-1), ['wait', 'fb_1'], 'waits for a record other than the one shown');
    arrives.resolve({ id: 'fb_3', mode: 'ai' });
    await settle();
    assert.deepEqual(drawn, [{ id: 'fb_3', mode: 'ai' }]);
    coach.enable(); // what the results screen does once it has drawn the record
    assert.equal(trigger(root).disabled, false);
    assert.equal(pending.hidden, true);
    assert.deepEqual(errors, []);
  } finally {
    console.error = realError;
  }
});

test('when no new feedback arrives in time the switch is enabled again and the banner says so', async () => {
  const realError = console.error;
  console.error = () => {};
  try {
    const { errors, drawn, root, status } = setupSwitch({ rerun: stillRunning, waitForFeedback: async () => null });
    pick(root, 'Beginner');
    await settle();
    assert.deepEqual(errors, ['Feedback is taking longer than usual']);
    assert.equal(SLOW_FEEDBACK_TEXT, 'Feedback is taking longer than usual');
    assert.deepEqual(drawn, []);
    assert.equal(trigger(root).disabled, false);
    assert.equal(status.withClass('coach-pending')[0].hidden, true);
  } finally {
    console.error = realError;
  }
});

test('waitForNewFeedback polls every 2 s for up to 60 s, skipping not-ready answers and the id already shown', async () => {
  const waits = [];
  const answers = [() => { throw new ApiError('wrong_state', 'Feedback not ready.', 409); }, () => ({ id: 'fb_1' }), () => ({ id: 'fb_2' })];
  const body = await waitForNewFeedback({ previousId: 'fb_1', getFeedback: async () => answers.shift()(), wait: async (ms) => { waits.push(ms); } });
  assert.deepEqual(body, { id: 'fb_2' });
  assert.deepEqual(waits, [2000, 2000, 2000]);

  const slowWaits = [];
  const none = await waitForNewFeedback({ previousId: 'fb_1', getFeedback: async () => ({ id: 'fb_1' }), wait: async (ms) => { slowWaits.push(ms); } });
  assert.equal(none, null);
  assert.equal(slowWaits.length, 30, '30 polls of 2 s make the 60 s limit');

  await assert.rejects(
    waitForNewFeedback({ previousId: 'fb_1', getFeedback: async () => { throw new ApiError('boom', 'Server error.', 500); }, wait: async () => {} }),
    /Server error/,
  );
});

test('another re-run failure shows the error and gives the switch back', async () => {
  const { errors, root } = setupSwitch({ rerun: async () => { throw new ApiError('oops', 'The feedback could not be made.', 500); } });
  pick(root, 'Beginner');
  await settle();
  assert.deepEqual(errors, ['The feedback could not be made.']);
  assert.equal(trigger(root).disabled, false);
});

test('the fallback notice shows only while the latest mode is fallback', () => {
  const { coach, status } = setupSwitch();
  const notice = status.withClass('coach-fallback')[0];
  assert.equal(notice.textContent, FALLBACK_COACH_TEXT);
  assert.equal(notice.hidden, true);
  coach.showMode('fallback');
  assert.equal(notice.hidden, false);
  coach.showMode('ai');
  assert.equal(notice.hidden, true);
});

test('the coach menu reads "Coach: Standard ▾", lists the four styles with the chosen one checked, and tells the caller once', () => {
  const { root, log } = setupSwitch();
  assert.equal(trigger(root).textContent, 'Coach: Standard ▾');
  assert.equal(root.withClass('segmented').length, 0, 'no segmented control any more');
  assert.equal(menuOpen(root), false);
  assert.equal(trigger(root).attributes['aria-expanded'], 'false');
  trigger(root).click();
  assert.equal(menuOpen(root), true);
  assert.equal(trigger(root).attributes['aria-expanded'], 'true');
  assert.deepEqual(itemLabels(root), ['Standard', 'Concert', 'Marching', 'Beginner']);
  assert.deepEqual(checked(root), ['Standard']);
  assert.equal(root.withClass('coach-menu-list')[0].attributes.role, 'menu');
  items(root)[0].click(); // the chosen one again
  assert.equal(menuOpen(root), false);
  assert.deepEqual(log, [], 'choosing the chosen style does nothing');
});

test('the menu works from the keyboard: arrows open and move, Escape closes without closing the sheet, Tab closes', () => {
  const picked = [];
  const menu = createMenu({ label: 'Coach', menuLabel: 'Coach style', options: PERSONAS, value: 'concert', onChange: (id) => picked.push(id) });
  const root = menu.element;
  const focused = () => items(root).findIndex((item) => item === document.activeElement);
  const down = key(trigger(root), 'ArrowDown');
  assert.equal(down.prevented, true);
  assert.equal(menuOpen(root), true);
  assert.equal(focused(), 1, 'opens on the chosen item');
  key(items(root)[1], 'ArrowDown');
  assert.equal(focused(), 2);
  key(items(root)[2], 'End');
  assert.equal(focused(), 3);
  key(items(root)[3], 'ArrowDown');
  assert.equal(focused(), 0, 'wraps');
  key(items(root)[0], 'ArrowUp');
  assert.equal(focused(), 3);
  key(items(root)[3], 'Home');
  assert.equal(focused(), 0);
  const escape = key(items(root)[0], 'Escape');
  assert.equal(escape.stopped, true, 'the sheet does not see this Escape');
  assert.equal(menuOpen(root), false);
  assert.ok(document.activeElement === trigger(root), 'focus returns to the button');
  key(trigger(root), 'ArrowUp');
  assert.equal(focused(), 3, 'ArrowUp opens on the last item');
  key(items(root)[3], 'Tab');
  assert.equal(menuOpen(root), false);
  trigger(root).click();
  items(root)[3].click();
  assert.deepEqual(picked, ['beginner']);
  assert.equal(trigger(root).textContent, 'Coach: Beginner ▾');
});

test('a click outside closes the menu; a disabled menu cannot be opened', () => {
  const menu = createMenu({ label: 'Coach', menuLabel: 'Coach style', options: PERSONAS, value: 'standard', onChange: () => {} });
  const root = menu.element;
  trigger(root).click();
  document.dispatch('click', { target: document.body });
  assert.equal(menuOpen(root), false);
  trigger(root).click();
  menu.setDisabled(true);
  assert.equal(menuOpen(root), false, 'disabling closes it');
  assert.equal(trigger(root).disabled, true);
  menu.setValue('marching');
  assert.deepEqual(checked(root), ['Marching']);
});

// The coach panel with the menu mounted by the real factory shape: mountCoachSwitch({ menu, status }, { onCoachChanged }).
async function setupPanel({ history = [], rerun, patch } = {}) {
  const root = document.createElement('div');
  document.body.replaceChildren(root);
  const drawn = [];
  let controller = null;
  const panel = createChatPanel(root, {
    sessionId: 's1',
    take: 'take_1',
    getChat: async () => ({ turns: history }),
    sendChat: async () => ({ user_turn: turn(1, 'user'), instructor_turn: turn(2, 'instructor', { mode: 'fallback', sentences: [] }) }),
    reportError: () => {},
    mountCoachSwitch: async ({ menu, status }, { onCoachChanged }) => {
      controller = createCoachSwitch({
        personas: PERSONAS, sessionId: 's1', take: 'take_1',
        savePersona: (sessionId, id) => savePersona(sessionId, id, patch ?? (async (_s, body) => ({ session_id: 's1', persona: body.persona }))),
        rerunFeedback: rerun ?? (async () => ({ id: 'fb_2', mode: 'ai' })),
        waitForFeedback: async () => null,
        currentFeedbackId: () => 'fb_1',
        onFeedback: (body) => { drawn.push(body); panel.setResults({ feedback: { ...body, sentences: [] } }); },
        onCoachChanged, reportError: () => {},
      });
      menu.append(controller.element);
      status.append(controller.status);
      return controller;
    },
  });
  await panel.whenReady;
  return { root, panel, drawn, notice: () => root.withClass('coach-fallback')[0] };
}

test('the menu sits in the sheet header, and a change adds a "Now coaching" line to the transcript', async () => {
  const { root, drawn } = await setupPanel();
  const header = root.withClass('coach-head')[0];
  assert.ok(header.all().includes(trigger(root)), 'the menu is in the header');
  assert.equal(root.withClass('coach-title')[0].hidden, true, 'the plain title gives way to the menu');
  assert.equal(root.withClass('coached-by').length, 0);
  pick(root, 'Concert');
  await settle();
  assert.deepEqual(root.texts('chat-note'), ['Now coaching: Concert']);
  assert.equal(drawn.length, 1);
  assert.equal(trigger(root).disabled, false, 'the new feedback record enabled the menu again');
});

test('the fallback notice, inside the sheet, follows the latest feedback or instructor turn', async () => {
  const { root, panel, notice } = await setupPanel({ history: [turn(2, 'instructor', { mode: 'fallback', sentences: [] })] });
  assert.equal(notice().hidden, false, 'the last instructor turn in the history was a fallback');
  panel.setResults({ feedback: { mode: 'ai', sentences: [] } });
  assert.equal(notice().hidden, true, 'a newer AI feedback record clears it');
  panel.setResults({ feedback: { mode: 'fallback', sentences: [] } });
  assert.equal(notice().hidden, false);
  assert.equal(notice().textContent, 'No AI coach connected: showing the built-in feedback');
  assert.equal(root.withClass('coach-sheet')[0].all().includes(notice()), true, 'the notice is inside the sheet');
});

test('a panel without the menu (personas unavailable) still works and keeps its plain title', async () => {
  const root = document.createElement('div');
  document.body.replaceChildren(root);
  const panel = createChatPanel(root, { sessionId: 's1', take: 'take_1', getChat: async () => ({ turns: [] }), sendChat: async () => ({}), reportError: () => {}, mountCoachSwitch: async () => null });
  await panel.whenReady;
  assert.equal(root.withClass('coach-menu').length, 0);
  assert.equal(root.withClass('coach-title')[0].hidden, false);
  assert.equal(root.withClass('coach-menu-slot')[0].children.length, 0);
});

test('the Play picker is preselected to the session persona; a change saves it and presets the tempo', async () => {
  state.persona = 'concert';
  const tempos = [];
  const errors = [];
  const patches = [];
  const picker = createPersonaPicker({
    personas: PERSONAS, sessionId: 's1', writtenTempoBpm: 96,
    savePersona: (sessionId, id) => savePersona(sessionId, id, async (...args) => { patches.push(args); return { persona: args[1].persona }; }),
    onTempo: (bpm) => tempos.push(bpm), reportError: (err) => errors.push(err.message),
  });
  assert.equal(picker.element.texts('persona-picker-label')[0], 'What are you practicing?');
  assert.deepEqual(chosen(picker.element), ['Concert']);
  assert.equal(picker.element.texts('persona-hint')[0], 'Band, orchestra, solos and etudes');
  clickSegment(picker.element, 'Beginner');
  await settle();
  clickSegment(picker.element, 'Marching');
  await settle();
  assert.deepEqual(patches, [['s1', { persona: 'beginner' }], ['s1', { persona: 'marching' }]]);
  assert.deepEqual(tempos, [67, 120]);
  assert.equal(state.persona, 'marching');
  assert.deepEqual(errors, []);
});

test('a failed save in the Play picker reverts it, shows the error and leaves the tempo', async () => {
  const tempos = [];
  const errors = [];
  const picker = createPersonaPicker({
    personas: PERSONAS, sessionId: 's1', writtenTempoBpm: 96,
    savePersona: (sessionId, id) => savePersona(sessionId, id, async () => { throw new ApiError('boom', 'Could not save.', 500); }),
    onTempo: (bpm) => tempos.push(bpm), reportError: (err) => errors.push(err.message),
  });
  clickSegment(picker.element, 'Beginner');
  await settle();
  assert.deepEqual(chosen(picker.element), ['Standard']);
  assert.deepEqual(errors, ['Could not save.']);
  assert.deepEqual(tempos, []);
  assert.equal(state.persona, 'standard');
  assert.ok(segments(picker.element).every((s) => !s.disabled));
});

test('"Coached by" names the persona of the feedback, and is left out without one or without the list', () => {
  state.personas = PERSONAS;
  assert.equal(renderCoachedBy({ persona: 'marching' }).textContent, 'Coached by Marching');
  assert.equal(renderCoachedBy({}), null);
  state.personas = null;
  assert.equal(renderCoachedBy({ persona: 'marching' }), null);
});

test('mock mode: GET /personas, PATCH echoes the persona, and the session, feedback and chat turns name it', async () => {
  const list = await mockResponse('GET', '/personas');
  assert.equal(list.status, 200);
  assert.equal(list.body.personas.length, 4);
  const patched = await mockResponse('PATCH', '/sessions/sess_mock1', { persona: 'concert' });
  assert.deepEqual(patched.body, { session_id: 'sess_mock1', persona: 'concert' });
  assert.equal((await mockResponse('GET', '/sessions/sess_mock1')).body.persona, 'concert');
  await mockResponse('GET', '/sessions/sess_mock1/takes/take_1/feedback'); // not ready on the first poll
  const first = (await mockResponse('GET', '/sessions/sess_mock1/takes/take_1/feedback')).body;
  assert.equal(first.persona, 'concert');
  const rebuilt = (await mockResponse('POST', '/sessions/sess_mock1/takes/take_1/feedback', {})).body;
  assert.equal(rebuilt.persona, 'concert');
  assert.notEqual(rebuilt.id, first.id, 'a re-run answers with a new feedback record');
  const chat = (await mockResponse('POST', '/sessions/sess_mock1/chat', { message: 'hi', take_id: 'take_1' })).body;
  assert.equal(chat.instructor_turn.persona, 'concert');
  await mockResponse('POST', '/sessions', { instrument: 'trumpet' });
  assert.equal((await mockResponse('GET', '/sessions/sess_mock1')).body.persona, 'standard', 'a new session starts on the default');
});

test('resuming a session reads its persona; a session without one is standard', async () => {
  await mockResponse('PATCH', '/sessions/sess_mock1', { persona: 'marching' });
  state.persona = 'standard';
  await resumeSession('#/take');
  assert.equal(state.persona, 'marching');
  await mockResponse('POST', '/sessions', { instrument: 'trumpet' });
  await resumeSession('#/take');
  assert.equal(state.persona, 'standard');
});

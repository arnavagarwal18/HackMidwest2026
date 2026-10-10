// The Instructor chat panel: history, the opening message, the question box and the pending-reply state.
// deps: { sessionId, take, getChat, sendChat, reportError, timeoutMs, timers } so tests can run it without a back end.
import { button, element } from '../dom.js';
import { REPLY_TIMEOUT_MS, TIMEOUT_MESSAGE, openingTurn, validateMessage, withTimeout } from './model.js';
import { renderTranscript } from './transcript.js';

const THINKING_TEXT = 'The Instructor is thinking…';
const EMPTY_TEXT = 'Ask the Instructor about this take.';

// Returns { setResults, whenReady, state }. setResults({ jumpContext, feedback }) is called by the results screen once
// the take's results are on screen: the feedback sentences become the opening message and jumps start to work.
export function createChatPanel(root, deps) {
  const { sessionId, take, getChat, sendChat, reportError, timeoutMs = REPLY_TIMEOUT_MS, timers } = deps;
  let history = [];
  let opening = null;
  let jumpContext = null;
  let pending = false;
  let loading = true; // the history is still being fetched

  const heading = element('h2', 'Instructor');
  const transcript = element('ul', '', 'chat-transcript', { 'aria-live': 'polite' });
  const emptyNote = element('p', EMPTY_TEXT, 'muted chat-empty');
  const thinking = element('p', THINKING_TEXT, 'chat-thinking muted', { role: 'status' });
  thinking.hidden = true;
  const input = element('textarea', '', 'chat-input', { rows: '3', 'aria-label': 'Your question for the Instructor' });
  const send = button('Send', () => submit(), 'chat-send');
  const form = element('div', '', 'chat-form');
  form.append(input, send);
  root.replaceChildren(heading, transcript, emptyNote, thinking, form);

  const sameTake = (turn) => (turn.take_id === take ? jumpContext : null);

  function redraw() {
    const turns = opening ? [opening, ...history] : history;
    renderTranscript(transcript, turns, sameTake);
    emptyNote.hidden = turns.length > 0;
  }

  function updateControls() {
    send.disabled = pending || loading;
    input.disabled = pending;
    thinking.hidden = !pending;
  }

  function setPending(value) {
    pending = value;
    updateControls();
  }

  async function submit() {
    if (pending) return;
    const message = input.value.trim();
    const problem = validateMessage(input.value);
    if (problem) return reportError(new Error(problem));
    setPending(true);
    try {
      const reply = await withTimeout(sendChat(sessionId, message, take), timeoutMs, TIMEOUT_MESSAGE, timers);
      history = [...history, reply.user_turn, reply.instructor_turn];
      input.value = '';
      redraw();
    } catch (err) {
      reportError(err); // the typed text stays in the box
    } finally {
      setPending(false);
    }
  }

  const finishLoading = () => { loading = false; redraw(); updateControls(); };
  const ready = getChat(sessionId).then(
    (result) => { history = result.turns ?? []; finishLoading(); },
    (err) => { reportError(err); finishLoading(); },
  ).catch(reportError);
  updateControls();

  return {
    whenReady: ready,
    setResults({ jumpContext: context = null, feedback = null } = {}) {
      jumpContext = context;
      opening = openingTurn(feedback, take);
      redraw();
    },
  };
}

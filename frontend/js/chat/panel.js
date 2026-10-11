// The Instructor chat panel: history, the opening message, the question box and the pending-reply state.
// deps: { sessionId, take, getChat, sendChat, reportError, timeoutMs, timers, mountCoachSwitch } so tests can run it without a back end.
// mountCoachSwitch(slot, { onCoachChanged }) is optional: it puts the Coach style switch in `slot` and resolves to its controller (or null).
import { button, element } from '../dom.js';
import { REPLY_TIMEOUT_MS, TIMEOUT_MESSAGE, openingTurn, validateMessage, withTimeout } from './model.js';
import { nowCoachingText } from '../persona/model.js';
import { renderTranscript } from './transcript.js';

const THINKING_TEXT = 'The Instructor is thinking…';
const EMPTY_TEXT = 'Ask the Instructor about this take.';

// Returns { setResults, whenReady, state }. setResults({ jumpContext, feedback }) is called by the results screen once
// the take's results are on screen: the feedback sentences become the opening message and jumps start to work.
export function createChatPanel(root, deps) {
  const { sessionId, take, getChat, sendChat, reportError, timeoutMs = REPLY_TIMEOUT_MS, timers, mountCoachSwitch } = deps;
  let history = [];
  let opening = null;
  let jumpContext = null;
  let pending = false;
  let loading = true; // the history is still being fetched
  let coach = null; // the Coach style switch controller, once mounted
  let coachMode = null; // the mode of the latest feedback or instructor turn

  const heading = element('h2', 'Instructor');
  const transcript = element('ul', '', 'chat-transcript', { 'aria-live': 'polite' });
  const emptyNote = element('p', EMPTY_TEXT, 'muted chat-empty');
  const thinking = element('p', THINKING_TEXT, 'chat-thinking muted', { role: 'status' });
  thinking.hidden = true;
  const input = element('textarea', '', 'chat-input', { rows: '3', 'aria-label': 'Your question for the Instructor' });
  const send = button('Send', () => submit(), 'chat-send');
  const form = element('div', '', 'chat-form');
  form.append(input, send);
  const coachSlot = element('div', '', 'coach-slot'); // fixed at the bottom of the panel
  root.replaceChildren(heading, transcript, emptyNote, thinking, form, coachSlot);

  const sameTake = (turn) => (turn.take_id === take ? jumpContext : null);

  function redraw() {
    const turns = opening ? [opening, ...history] : history;
    renderTranscript(transcript, turns, sameTake);
    emptyNote.hidden = turns.length > 0;
  }

  function setCoachMode(mode) {
    coachMode = mode;
    coach?.showMode(coachMode);
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
      setCoachMode(reply.instructor_turn.mode ?? null);
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
    (result) => {
      history = [...(result.turns ?? []), ...history]; // history is empty here unless a 'Now coaching' line was added meanwhile
      finishLoading();
      if (coachMode === null) setCoachMode(history.findLast((turn) => turn.role === 'instructor')?.mode ?? null);
    },
    (err) => { reportError(err); finishLoading(); },
  ).catch(reportError);
  updateControls();

  const coachReady = mountCoachSwitch
    ? mountCoachSwitch(coachSlot, { onCoachChanged: (label) => { history = [...history, { role: 'note', text: nowCoachingText(label) }]; redraw(); } })
      .then((controller) => { coach = controller; coach?.showMode(coachMode); }, reportError)
    : Promise.resolve();

  return {
    whenReady: Promise.all([ready, coachReady]),
    setResults({ jumpContext: context = null, feedback = null } = {}) {
      jumpContext = context;
      opening = openingTurn(feedback, take);
      if (feedback) setCoachMode(feedback.mode ?? null);
      coach?.enable();
      redraw();
    },
  };
}

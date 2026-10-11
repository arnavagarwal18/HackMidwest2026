// The coach panel: a sheet that is closed until 'coach:open' is dispatched on the document. It holds the coach's opening line,
// suggested-question chips, the transcript, the pending-reply state and the question box.
// deps: { sessionId, take, getChat, sendChat, reportError, timeoutMs, timers, mountCoachSwitch } so tests can run it without a back end.
// mountCoachSwitch({ menu, status }, { onCoachChanged }) is optional: it puts the 'Coach: Standard' menu in `menu` and the
// notices in `status`, and resolves to its controller (or null).
import { button, element } from '../dom.js';
import { loadStylesheet } from '../ui/styles.js';
import { REPLY_TIMEOUT_MS, TIMEOUT_MESSAGE, openingTurn, suggestedQuestions, validateMessage, withTimeout } from './model.js';
import { nowCoachingText } from '../persona/model.js';
import { createSheet } from './sheet.js';
import { createSuggestions } from './suggestions.js';
import { renderTranscript } from './transcript.js';

const STYLE_HREF = 'css/coach.css';
export const OPEN_EVENT = 'coach:open';
const THINKING_TEXT = 'The coach is thinking…';

// Returns { setResults, whenReady, open, close, isOpen }. setResults({ jumpContext, feedback }) is called by the results screen once
// the take's results are on screen: the first feedback sentence becomes the opening line, the chips follow the feedback, and jumps start to work.
export function createChatPanel(root, deps) {
  const { sessionId, take, getChat, sendChat, reportError, timeoutMs = REPLY_TIMEOUT_MS, timers, mountCoachSwitch } = deps;
  loadStylesheet(STYLE_HREF);
  let history = [];
  let opening = null;
  let jumpContext = null;
  let questions = suggestedQuestions(null);
  let pending = false;
  let loading = true; // the history is still being fetched
  let coach = null; // the Coach menu controller, once mounted
  let coachMode = null; // the mode of the latest feedback or instructor turn

  const sheet = createSheet({ title: 'Coach' });
  const title = element('span', 'Coach', 'coach-title'); // shown until the style menu is mounted
  const menuSlot = element('div', '', 'coach-menu-slot');
  const statusSlot = element('div', '', 'coach-status');
  const transcript = element('ul', '', 'chat-transcript', { 'aria-live': 'polite' });
  const thinking = element('p', THINKING_TEXT, 'chat-thinking muted', { role: 'status' });
  thinking.hidden = true;
  const suggestions = createSuggestions({ onPick: (question) => ask(question) });
  const input = element('textarea', '', 'chat-input', { rows: '2', placeholder: 'Ask the coach', 'aria-label': 'Your question for the coach' });
  const send = button('Send', () => ask(input.value, { fromInput: true }), 'btn btn-primary chat-send');
  const form = element('div', '', 'chat-form');
  form.append(input, send);
  sheet.headerSlot.append(title, menuSlot);
  sheet.body.append(statusSlot, transcript, thinking, suggestions.element);
  sheet.footer.append(form);
  root.replaceChildren(...sheet.nodes);

  // A jump closes the sheet first so the bar it points at is in view.
  const sameTake = (turn) => {
    if (turn.take_id !== take || !jumpContext) return null;
    return { ...jumpContext, jumper: { jumpTo: (place) => { sheet.close(); jumpContext.jumper.jumpTo(place); } } };
  };

  function redraw() {
    const turns = opening ? [opening, ...history] : history;
    renderTranscript(transcript, turns, sameTake);
    suggestions.show(history.some((turn) => turn.role === 'user') ? [] : questions);
    sheet.body.scrollTop = sheet.body.scrollHeight;
  }

  function setCoachMode(mode) {
    coachMode = mode;
    coach?.showMode(coachMode);
  }

  function updateControls() {
    send.disabled = pending || loading;
    input.disabled = pending;
    thinking.hidden = !pending;
    suggestions.setDisabled(pending || loading);
  }

  function setPending(value) {
    pending = value;
    updateControls();
  }

  async function ask(text, { fromInput = false } = {}) {
    if (pending) return;
    const problem = validateMessage(text);
    if (problem) return reportError(new Error(problem));
    setPending(true);
    try {
      const reply = await withTimeout(sendChat(sessionId, text.trim(), take), timeoutMs, TIMEOUT_MESSAGE, timers);
      history = [...history, reply.user_turn, reply.instructor_turn];
      setCoachMode(reply.instructor_turn.mode ?? null);
      if (fromInput) input.value = '';
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
  redraw();

  const coachReady = mountCoachSwitch
    ? mountCoachSwitch({ menu: menuSlot, status: statusSlot }, { onCoachChanged: (label) => { history = [...history, { role: 'note', text: nowCoachingText(label) }]; redraw(); } })
      .then((controller) => {
        coach = controller;
        title.hidden = coach !== null;
        coach?.showMode(coachMode);
      }, reportError)
    : Promise.resolve();

  // One listener per panel; the results screen builds a new panel each visit, so a panel that left the page stops listening.
  const onOpenRequest = () => {
    if (!root.isConnected) return document.removeEventListener(OPEN_EVENT, onOpenRequest);
    sheet.open();
  };
  document.addEventListener(OPEN_EVENT, onOpenRequest);

  return {
    whenReady: Promise.all([ready, coachReady]),
    open: sheet.open,
    close: sheet.close,
    isOpen: sheet.isOpen,
    setResults({ jumpContext: context = null, feedback = null } = {}) {
      jumpContext = context;
      opening = openingTurn(feedback, take);
      questions = suggestedQuestions(feedback);
      if (feedback) setCoachMode(feedback.mode ?? null);
      coach?.enable();
      redraw();
    },
  };
}

// Voice input for the coach's question box: a mic button that fills the box from the browser's speech recognition.
// It never sends: the user reads what was heard, edits it and presses Send.
// createSpeechInput({ input, reportError, win, logger }) -> { element, stop, setDisabled }. `win` and `logger` are for tests.
import { button } from '../dom.js';

export const LANGUAGE = 'en-US';
export const UNSUPPORTED_MESSAGE = 'Voice input needs Chrome, Edge or Safari';
export const INSECURE_MESSAGE = 'Voice input needs HTTPS or localhost';
const START_LABEL = 'Speak';
const STOP_LABEL = 'Stop';
const START_HINT = 'Speak your question; click again to stop';
const STOP_HINT = 'Stop listening';

export const ERROR_MESSAGES = {
  'not-allowed': 'The microphone is blocked. Allow it in the browser’s site settings, then try again.',
  'service-not-allowed': 'The microphone is blocked. Allow it in the browser’s site settings, then try again.',
  'no-speech': 'No speech was heard. Click Speak and try again, closer to the microphone.',
  'audio-capture': 'No microphone was found. Plug one in or check the system settings, then try again.',
  network: 'Voice input needs an internet connection. Check it and try again, or type your question.',
  'language-not-supported': 'Voice input does not support this language in your browser. Type your question instead.',
};
const genericMessage = (code) => `Voice input stopped (${code}). Try again, or type your question.`;

// Returns null when voice input can work here, otherwise the sentence that says why not.
export function unavailableReason(win) {
  if (!(win.SpeechRecognition || win.webkitSpeechRecognition)) return UNSUPPORTED_MESSAGE;
  if (!win.isSecureContext) return INSECURE_MESSAGE;
  return null;
}

export function createSpeechInput({ input, reportError, win = window, logger = console }) {
  const mic = button(START_LABEL, () => toggle(), 'btn btn-ghost chat-mic');
  let recognition = null;
  let base = ''; // what was in the box when listening started

  const unavailable = unavailableReason(win);
  const setListening = (listening) => {
    mic.textContent = listening ? STOP_LABEL : START_LABEL;
    mic.setAttribute('aria-pressed', String(listening));
    mic.setAttribute('title', listening ? STOP_HINT : START_HINT);
    mic.className = `btn btn-ghost chat-mic${listening ? ' is-recording' : ''}`;
  };
  setListening(false);
  if (unavailable) {
    mic.setAttribute('aria-disabled', 'true'); // not `disabled`, so the tooltip and the click message still work
    mic.setAttribute('title', unavailable);
  }

  function fail(message, ...details) {
    logger.warn(`Voice input: ${message}`, ...details);
    reportError(new Error(message));
  }

  function fillInput(event) {
    const heard = Array.from(event.results, (result) => result[0].transcript).join('').trim();
    input.value = base && heard ? `${base} ${heard}` : base || heard;
  }

  function start() {
    const Recognition = win.SpeechRecognition || win.webkitSpeechRecognition;
    base = input.value.trimEnd();
    recognition = new Recognition();
    recognition.lang = LANGUAGE;
    recognition.interimResults = true;
    recognition.onresult = fillInput;
    recognition.onerror = (event) => {
      if (event.error === 'aborted') return; // we stopped it ourselves; `end` resets the button
      fail(ERROR_MESSAGES[event.error] ?? genericMessage(event.error), event);
    };
    recognition.onend = () => { recognition = null; setListening(false); };
    try {
      recognition.start();
      setListening(true);
    } catch (err) {
      recognition = null;
      setListening(false);
      fail('Voice input could not start. Wait a moment and try again, or type your question.', err);
    }
  }

  function stop() {
    recognition?.stop(); // the final result still arrives, then `end` resets the button
  }

  function toggle() {
    if (unavailable) return fail(unavailable);
    if (recognition) return stop();
    start();
  }

  return { element: mic, stop, setDisabled: (disabled) => { mic.disabled = disabled; } };
}

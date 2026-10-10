// Pure logic of the Instructor chat panel: message checks, the reply time limit and what a turn looks like.
export const MAX_MESSAGE_LENGTH = 1000;
export const REPLY_TIMEOUT_MS = 35000;
export const FALLBACK_NOTE = 'AI instructor unavailable';
export const TIMEOUT_MESSAGE = 'The Instructor took too long to reply. Please try again.';
export const EMPTY_MESSAGE_ERROR = 'Type a question for the Instructor first.';
export const TOO_LONG_ERROR = `Keep your message to ${MAX_MESSAGE_LENGTH} characters or fewer.`;

// The problem with a message, or null when it can be sent. Length is measured on the trimmed text that is sent.
export function validateMessage(text) {
  const length = text.trim().length;
  if (length === 0) return EMPTY_MESSAGE_ERROR;
  if (length > MAX_MESSAGE_LENGTH) return TOO_LONG_ERROR;
  return null;
}

// Settles like `promise`, but rejects with Error(message) after timeoutMs. setTimer/clearTimer are injectable for tests.
export function withTimeout(promise, timeoutMs, message, { setTimer = setTimeout, clearTimer = clearTimeout } = {}) {
  return new Promise((resolve, reject) => {
    const timer = setTimer(() => reject(new Error(message)), timeoutMs);
    promise.then(
      (value) => { clearTimer(timer); resolve(value); },
      (err) => { clearTimer(timer); reject(err); },
    );
  });
}

// The instructor's opening message: the take's feedback sentences, as a turn the transcript can draw.
// Returns null when the take has no sentences to open with.
export function openingTurn(feedback, take) {
  const sentences = feedback?.sentences ?? [];
  if (!sentences.length) return null;
  return { turn: 0, role: 'instructor', text: sentences.map((s) => s.text).join(' '), take_id: take, sentences, mode: feedback.mode ?? null };
}

export const isFallback = (turn) => turn.role === 'instructor' && turn.mode === 'fallback';

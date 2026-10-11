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

// The coach's opening line: the first sentence of the take's feedback (the page shows the rest), as a turn the transcript can draw.
// Returns null when the take has no sentences to open with.
export function openingTurn(feedback, take) {
  const first = feedback?.sentences?.[0];
  if (!first) return null;
  return { turn: 0, role: 'instructor', text: first.text, take_id: take, sentences: [first], mode: feedback.mode ?? null };
}

export const PITCH_QUESTION = 'Fix my pitch';
export const PLAN_QUESTION = 'Practice plan';
export const weakestBarQuestion = (bar) => `Why was bar ${bar} off?`;

// The bar of the first problem the feedback names (the most important one), or null when none points at a bar.
function weakestBar(feedback) {
  const places = [...(feedback?.tier1 ?? []), ...(feedback?.sentences ?? [])];
  return places.map((item) => item.jump?.bar).find(Number.isInteger) ?? null;
}

// The questions offered as chips: two that always apply and one about the weakest bar when the feedback names one.
export function suggestedQuestions(feedback) {
  const bar = weakestBar(feedback);
  return [PITCH_QUESTION, PLAN_QUESTION, ...(bar === null ? [] : [weakestBarQuestion(bar)])];
}

export const isFallback = (turn) => turn.role === 'instructor' && turn.mode === 'fallback';

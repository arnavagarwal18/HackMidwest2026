// After a re-run answered 409 (a feedback run is already going): poll GET .../feedback until a record other than the one on screen
// arrives. 'Not ready' answers (409 wrong_state) are part of waiting; any other failure is thrown.
export const POLL_INTERVAL_MS = 2000;
export const POLL_LIMIT_MS = 60000;
export const SLOW_FEEDBACK_TEXT = 'Feedback is taking longer than usual';

const isNotReady = (err) => err?.status === 409 || err?.code === 'wrong_state';
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Resolves to the new feedback body, or null when none arrived within limitMs.
export async function waitForNewFeedback({ getFeedback, previousId, intervalMs = POLL_INTERVAL_MS, limitMs = POLL_LIMIT_MS, wait = sleep }) {
  for (let waited = 0; waited < limitMs; waited += intervalMs) {
    await wait(intervalMs);
    try {
      const body = await getFeedback();
      if (body.id !== previousId) return body;
    } catch (err) {
      if (!isNotReady(err)) throw err;
    }
  }
  return null;
}

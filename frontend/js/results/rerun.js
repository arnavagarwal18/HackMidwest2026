// After the user changes the transposition by hand: the back end re-checks the notes in the background but does not
// write the feedback again, so the old feedback (often the can't-tell one) would be shown unchanged. This waits for the
// re-check, asks for new feedback once, and returns the same { done, analysis, feedback, plan } the screen shows.
import { waitForKey, writeFeedbackAgain } from './autokey_run.js';

// Resolves to { outcome: 'done', result } | { outcome: 'timeout' } | { outcome: 'stopped' }. Errors propagate.
export async function refreshAfterKeyChange({ sessionId, take, semitones, isActive }) {
  const polled = await waitForKey(sessionId, take, semitones, isActive);
  if (polled.outcome !== 'done') return { outcome: polled.outcome };
  const result = await writeFeedbackAgain(sessionId, take, polled.result.analysis, isActive);
  return { outcome: 'done', result };
}

// After the user changes the transposition by hand: the back end checks the notes again in the background and then
// builds the take's feedback again. This waits for the new key to show in the analysis, then for the new feedback (a
// different id from the one on screen), and returns the same { done, analysis, feedback, plan } the screen shows.
import { fetchResultsOnce } from './load.js';
import { pollUntilDone } from './polling.js';
import { keyThresholds, waitForKey } from './take_wait.js';

// Resolves to { outcome: 'done', result } | { outcome: 'timeout' } | { outcome: 'stopped' }. Errors propagate.
export async function refreshAfterKeyChange({ sessionId, take, semitones, previousFeedbackId, isActive }) {
  const rechecked = await waitForKey(sessionId, take, semitones, isActive);
  if (rechecked.outcome !== 'done') return { outcome: rechecked.outcome };
  const rebuilt = await pollUntilDone({
    isActive,
    thresholds: keyThresholds(),
    onTick: () => {},
    fetchOnce: async () => {
      const result = await fetchResultsOnce(sessionId, take);
      return { ...result, done: result.done && result.feedback?.id !== previousFeedbackId };
    },
  });
  return rebuilt.outcome === 'done' ? { outcome: 'done', result: rebuilt.result } : { outcome: rebuilt.outcome };
}

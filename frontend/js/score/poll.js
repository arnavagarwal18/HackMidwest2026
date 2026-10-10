// Polls the scan status until it stops being 'scanning'.
// Resolves { outcome: 'done', status } | { outcome: 'timeout', status } | { outcome: 'cancelled' }.
// A failing fetchStatus rejects; the caller reports it. Nothing here retries by itself.
export const POLL_INTERVAL_MS = 2000;
export const SLOW_AFTER_MS = 90 * 1000;
export const GIVE_UP_AFTER_MS = 300 * 1000;

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function pollScoreStatus({
  fetchStatus,
  isActive,
  onSlow,
  intervalMs = POLL_INTERVAL_MS,
  slowAfterMs = SLOW_AFTER_MS,
  giveUpAfterMs = GIVE_UP_AFTER_MS,
  now = () => performance.now(),
  sleep = wait,
}) {
  const startedAt = now();
  let slowShown = false;
  for (;;) {
    if (!isActive()) return { outcome: 'cancelled' };
    const status = await fetchStatus();
    if (!isActive()) return { outcome: 'cancelled' };
    if (status.score_status !== 'scanning') return { outcome: 'done', status };
    const elapsed = now() - startedAt;
    if (elapsed >= giveUpAfterMs) return { outcome: 'timeout', status };
    if (!slowShown && elapsed >= slowAfterMs) {
      slowShown = true;
      onSlow();
    }
    await sleep(intervalMs);
  }
}

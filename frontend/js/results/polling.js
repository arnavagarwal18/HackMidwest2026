// Polls the back end once a second until a job is done, with a 'still working' signal and a hard stop.
// The thresholds can be shortened from the URL for tests: ?poll_ms=100&slow_after_s=3&give_up_after_s=6
export const DEFAULT_THRESHOLDS = { intervalMs: 1000, slowAfterMs: 90_000, giveUpAfterMs: 300_000 };

export function pollThresholds(search = window.location.search) {
  const params = new URLSearchParams(search);
  const read = (name, scale, fallback) => {
    const value = Number(params.get(name));
    return params.has(name) && value > 0 ? value * scale : fallback;
  };
  return {
    intervalMs: read('poll_ms', 1, DEFAULT_THRESHOLDS.intervalMs),
    slowAfterMs: read('slow_after_s', 1000, DEFAULT_THRESHOLDS.slowAfterMs),
    giveUpAfterMs: read('give_up_after_s', 1000, DEFAULT_THRESHOLDS.giveUpAfterMs),
  };
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// fetchOnce() -> { done, ...anything }. Resolves to { outcome: 'done', result }, { outcome: 'timeout', result }
// (last answer, after giveUpAfterMs) or { outcome: 'stopped' } when isActive() turns false.
// onTick({ result, slow }) runs after every answer that is not done yet. A thrown error ends the loop and propagates.
export async function pollUntilDone({ fetchOnce, onTick, isActive, thresholds = pollThresholds() }) {
  const started = performance.now();
  for (;;) {
    const result = await fetchOnce();
    if (!isActive()) return { outcome: 'stopped' };
    if (result.done) return { outcome: 'done', result };
    const elapsed = performance.now() - started;
    if (elapsed >= thresholds.giveUpAfterMs) return { outcome: 'timeout', result };
    onTick({ result, slow: elapsed >= thresholds.slowAfterMs });
    await wait(thresholds.intervalMs);
    if (!isActive()) return { outcome: 'stopped' };
  }
}

// Posts one camera frame about every second and reports the answer. At most one check is in flight; the next
// one is scheduled intervalMs after the last answer, so checks never come faster than once a second.
// A failed check stops the loop (onFailure runs once) instead of retrying behind the learner's back.
export const CHECK_INTERVAL_MS = 1000;

// captureFrame() resolves a JPEG Blob, or null when the camera has no picture yet (that tick is skipped).
// check(blob) resolves the camera-check answer. onResult(answer) and onFailure(error) are called only while running.
export function createCameraChecker({ captureFrame, check, onResult, onFailure, intervalMs = CHECK_INTERVAL_MS }) {
  let running = false;
  let timer = null;

  async function tick() {
    timer = null;
    try {
      const frame = await captureFrame();
      const answer = frame ? await check(frame) : null;
      if (!running) return;
      if (answer) onResult(answer);
    } catch (err) {
      if (!running) return;
      running = false;
      console.error('Camera check failed; checks stopped for this screen:', err);
      onFailure(err);
      return;
    }
    if (running) timer = setTimeout(tick, intervalMs);
  }

  return {
    start() {
      if (running) return;
      running = true;
      timer = setTimeout(tick, 0);
    },
    stop() {
      running = false;
      clearTimeout(timer);
      timer = null;
    },
    get running() { return running; },
  };
}

// Finding the tracked frame to draw: the one nearest the video's current time.
export const MAX_FRAME_GAP_S = 0.2; // no drawing when the nearest tracked frame is further than this from the video time

// frames are sorted by t (seconds). Returns the nearest frame, or null when there are none or the nearest is more than maxGapS away.
export function nearestFrame(frames, t, maxGapS = MAX_FRAME_GAP_S) {
  if (!frames?.length || !Number.isFinite(t)) return null;
  let low = 0;
  let high = frames.length - 1;
  while (low < high) { // first frame with frame.t >= t
    const mid = (low + high) >> 1;
    if (frames[mid].t < t) low = mid + 1;
    else high = mid;
  }
  const candidates = [frames[low - 1], frames[low]].filter(Boolean);
  const best = candidates.reduce((a, b) => (Math.abs(b.t - t) < Math.abs(a.t - t) ? b : a));
  return Math.abs(best.t - t) <= maxGapS ? best : null;
}

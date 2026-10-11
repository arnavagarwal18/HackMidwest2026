// A take filmed from the side shows one side of the body clearly; the far side is hidden or guessed.
// This finds which side that is and which pose points and lines belong to it.
const NEAR_POINTS = { left: [7, 11, 13, 15, 23], right: [8, 12, 14, 16, 24] }; // ear, shoulder, elbow, wrist, hip
export const SIDE_VISIBILITY_GAP = 0.25; // the weaker side must be this much less visible, on average, to count as a side view

const meanVisibility = (frames, indices) => {
  let total = 0;
  indices.forEach((index) => frames.forEach((frame) => { total += frame.pose[index]?.[2] ?? 0; }));
  return total / (indices.length * frames.length);
};

// 'left' or 'right' for a side-on take, null for a front view or when there is no pose to judge by.
export function detectNearSide(frames) {
  const posed = (frames ?? []).filter((frame) => Array.isArray(frame.pose));
  if (!posed.length) return null;
  const left = meanVisibility(posed, NEAR_POINTS.left);
  const right = meanVisibility(posed, NEAR_POINTS.right);
  if (Math.abs(left - right) < SIDE_VISIBILITY_GAP) return null;
  return left > right ? 'left' : 'right';
}

const NOSE = 0; // on the centre line, so it is seen from either side
export const isNearPoint = (index, nearSide) => nearSide === null || index === NOSE || NEAR_POINTS[nearSide].includes(index);
export const isNearLine = ([from, to], nearSide) => isNearPoint(from, nearSide) && isNearPoint(to, nearSide);

// Which body points a form flag is about, and which flags are active at a video time. MediaPipe pose indices; left and
// right are the learner's own. `center` points belong to both sides; each `sided` pair is [left, right].
const NOSE = 0;
const EARS = [7, 8];
const SHOULDERS = [11, 12];
const ELBOWS = [13, 14];
const HIPS = [23, 24];

export const RULE_LANDMARKS = {
  trumpet_head_down: { center: [NOSE], sided: [EARS] },
  trumpet_elbows_pinned: { center: [], sided: [ELBOWS, SHOULDERS] },
  shoulders_raised: { center: [], sided: [SHOULDERS, EARS] },
  slouching: { center: [], sided: [SHOULDERS, HIPS] },
};

// Pose indices to draw red for one flag. A rule with no entry here (a new rule) has no points; its label still shows.
export function involvedLandmarks(flag) {
  const rule = RULE_LANDMARKS[flag.rule];
  if (!rule) return [];
  const sides = flag.side === 'left' ? [0] : flag.side === 'right' ? [1] : [0, 1];
  return [...rule.center, ...rule.sided.flatMap((pair) => sides.map((side) => pair[side]))];
}

export function activeFlags(flags, t) {
  return flags.filter((flag) => t >= flag.start_s && t <= flag.end_s);
}

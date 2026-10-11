// Draws one tracked frame (and the active form flags) onto the overlay canvas context.
import { involvedLandmarks } from './flag_points.js';
import { toCanvas } from './geometry.js';
import { isNearLine, isNearPoint } from './side_view.js';

export const VISIBILITY_MIN = 0.5; // pose points less visible than this are not drawn (same cut-off as the back end)
const LINE_COLOR = '#12b76a';
const HAND_COLOR = '#2e90fa';
const FLAG_COLOR = '#d92d20';
const LABEL_BACKGROUND = 'rgba(0, 0, 0, 0.65)';
const LABEL_TEXT = '#ffffff';

// [from, to] pose indices: shoulders, shoulder-elbow, elbow-wrist, ear-shoulder, shoulder-hip.
export const POSE_LINES = [[11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [7, 11], [8, 12], [11, 23], [12, 24]];

const isVisible = (point) => Boolean(point) && (point[2] ?? 1) >= VISIBILITY_MIN;

function drawLine(ctx, from, to, rect) {
  ctx.beginPath();
  ctx.moveTo(...toCanvas(from, rect));
  ctx.lineTo(...toCanvas(to, rect));
  ctx.stroke();
}

function drawDot(ctx, point, rect, radius, color) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(...toCanvas(point, rect), radius, 0, Math.PI * 2);
  ctx.fill();
}

function drawLabels(ctx, labels, rect) {
  ctx.font = '14px sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  labels.forEach((label, row) => {
    const x = rect.x + rect.width / 2;
    const y = rect.y + 16 + row * 24;
    const width = Math.min(ctx.measureText(label).width + 16, rect.width);
    ctx.fillStyle = LABEL_BACKGROUND;
    ctx.fillRect(x - width / 2, y - 11, width, 22);
    ctx.fillStyle = LABEL_TEXT;
    ctx.fillText(label, x, y, rect.width - 16);
  });
}

// frame: { pose, left_hand, right_hand } (each may be null). rect: where the picture is on the canvas.
// flags: the flags active now. Flag text goes in with fillText, never as HTML.
// nearSide: 'left' or 'right' for a take filmed from the side (only that side is drawn); null draws both sides.
export function drawOverlay(ctx, { frame, rect, flags = [], nearSide = null }) {
  const pose = frame.pose ?? [];
  ctx.lineWidth = 3;
  ctx.lineCap = 'round';
  ctx.strokeStyle = LINE_COLOR;
  POSE_LINES.filter((line) => isNearLine(line, nearSide)).forEach(([from, to]) => {
    if (isVisible(pose[from]) && isVisible(pose[to])) drawLine(ctx, pose[from], pose[to], rect);
  });
  const hands = nearSide === null ? [frame.left_hand, frame.right_hand] : [frame[`${nearSide}_hand`]];
  hands.forEach((hand) => (hand ?? []).forEach((point) => drawDot(ctx, point, rect, 3, HAND_COLOR)));
  new Set(flags.flatMap(involvedLandmarks)).forEach((index) => {
    if (isNearPoint(index, nearSide) && isVisible(pose[index])) drawDot(ctx, pose[index], rect, 7, FLAG_COLOR);
  });
  drawLabels(ctx, flags.map((flag) => flag.label), rect);
}

// Turns a camera-check answer { ok, missing, too_small, too_dark } into the badge the learner sees.
import { nearSideOf } from './camera_view.js';

export const IN_FRAME_TEXT = 'In frame';
export const UNAVAILABLE_TEXT = 'The camera check is not available right now. You can still record.';
export const UNAVAILABLE_CODE = 'form_unavailable';

function joinWords(words) {
  if (words.length <= 1) return words.join('');
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

// From the side only the side facing the camera can be seen, so the far side's points and too_small (shoulders
// that look close together side-on) do not count. The server reports hips as one point, which can't be told apart.
function sideAnswer(result, nearSide) {
  const farSide = nearSide === 'left' ? 'right' : 'left';
  const missing = (result.missing || []).filter((name) => name !== 'hips' && !name.startsWith(`${farSide} `));
  return { ...result, missing, too_small: false, ok: !missing.length && !result.too_dark };
}

// Returns { ok, text }. Recording stays allowed when ok is false. view is a camera_view.js id (front by default).
export function describeCameraCheck(answer, view) {
  const nearSide = nearSideOf(view);
  const result = nearSide ? sideAnswer(answer, nearSide) : answer;
  if (result.ok) return { ok: true, text: IN_FRAME_TEXT };
  const parts = [];
  if (result.missing && result.missing.length) parts.push(`Move back: ${joinWords(result.missing)} not in view`);
  if (result.too_small) parts.push('Move closer, you look small in the picture');
  if (result.too_dark) parts.push('Add more light, the picture is dark');
  return { ok: false, text: parts.length ? parts.join('. ') : 'Adjust your position until you fit the outline' };
}

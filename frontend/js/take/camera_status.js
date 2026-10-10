// Turns a camera-check answer { ok, missing, too_small, too_dark } into the badge the learner sees.
export const IN_FRAME_TEXT = 'In frame';
export const UNAVAILABLE_TEXT = 'The camera check is not available right now. You can still record.';
export const UNAVAILABLE_CODE = 'form_unavailable';

function joinWords(words) {
  if (words.length <= 1) return words.join('');
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

// Returns { ok, text }. Recording stays allowed when ok is false.
export function describeCameraCheck(result) {
  if (result.ok) return { ok: true, text: IN_FRAME_TEXT };
  const parts = [];
  if (result.missing && result.missing.length) parts.push(`Move back: ${joinWords(result.missing)} not in view`);
  if (result.too_small) parts.push('Move closer, you look small in the picture');
  if (result.too_dark) parts.push('Add more light, the picture is dark');
  return { ok: false, text: parts.length ? parts.join('. ') : 'Adjust your position until you fit the outline' };
}

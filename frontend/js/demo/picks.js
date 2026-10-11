// The two file pickers of the demo upload: the sheet-music photo and the video of the playing.
import { PHOTO_ACCEPT } from '../score/photo_tab.js';
import { el } from '../score/ui.js';
import { UPLOAD_ACCEPT, uploadTypeProblem } from '../take/upload_types.js';

// A message the dev can act on when the chosen files cannot go through the normal flow, or null when they can.
export function picksProblem({ photo, video }) {
  if (!photo) return 'Choose the sheet-music photo first.';
  if (!photo.type.startsWith('image/')) return `"${photo.name}" is not a photo. Choose a JPEG, PNG or WebP picture of the sheet music.`;
  if (!video) return 'Choose the video of the playing first.';
  return uploadTypeProblem(video);
}

const pickerRow = (label, accept) => {
  const input = el('input', { attrs: { type: 'file', accept } });
  return { input, row: el('p', { children: [el('label', { className: 'file-pick', children: [`${label} `, input] })] }) };
};

// onChange() runs when either file changes. read() gives { photo, video }: the File objects themselves, never copies.
export function createPicks({ onChange }) {
  const photo = pickerRow('Sheet-music photo', PHOTO_ACCEPT);
  const video = pickerRow('Video of the playing', UPLOAD_ACCEPT);
  [photo.input, video.input].forEach((input) => input.addEventListener('change', onChange));
  return {
    element: el('div', { children: [photo.row, video.row] }),
    read: () => ({ photo: photo.input.files[0], video: video.input.files[0] }),
  };
}

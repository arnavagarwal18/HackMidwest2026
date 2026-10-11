// Photo tab: take or choose a photo, drag a rectangle round the music, send the crop.
import { uploadScorePhoto } from '../api.js';
import { reportError } from '../banner.js';
import { Cropper } from '../crop.js';
import { button, el, runGuarded } from './ui.js';

export const PHOTO_ACCEPT = 'image/*';
const UNREADABLE_PHOTO = "This browser can't open that photo. Try a JPEG or PNG picture.";

function fileInput(label, capture) {
  const input = el('input', { attrs: { type: 'file', accept: PHOTO_ACCEPT } });
  if (capture) input.setAttribute('capture', 'environment');
  return { input, label: el('label', { className: 'file-pick', children: [`${label} `, input] }) };
}

// submit(call, source) starts the score upload and shows its result; it throws what the back end threw.
export function createPhotoTab({ submit }) {
  const canvas = el('canvas', { className: 'crop-canvas', attrs: { 'aria-label': 'Your photo. Drag a rectangle round the music.' } });
  const cropper = new Cropper(canvas);
  const take = fileInput('Take a photo', true);
  const choose = fileInput('Choose a photo', false);
  const whole = button('Use the whole photo', () => cropper.clearRect());
  const send = button('Read this music', () => runGuarded([send, whole], async () => {
    const jpeg = await cropper.exportJpeg();
    await submit((sessionId) => uploadScorePhoto(sessionId, jpeg), 'photo');
  }), 'primary');
  const hint = el('p', { text: 'Drag a rectangle round the music. Leave it out to use the whole photo.', className: 'muted' });
  const stage = el('div', { className: 'crop-stage', attrs: { hidden: '' }, children: [hint, canvas, el('p', { children: [whole, ' ', send] })] });

  async function loadPhoto(file) {
    try {
      cropper.setImage(await createImageBitmap(file));
      stage.hidden = false;
    } catch (err) {
      console.error('Could not decode the chosen photo:', err);
      reportError(new Error(UNREADABLE_PHOTO));
    }
  }

  [take.input, choose.input].forEach((input) => {
    input.addEventListener('change', () => input.files[0] && loadPhoto(input.files[0]));
  });

  return el('div', { children: [el('p', { children: [take.label, ' ', choose.label] }), stage] });
}

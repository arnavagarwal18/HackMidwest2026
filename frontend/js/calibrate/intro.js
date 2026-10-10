// The top of the calibration screen: the QR code and address of the tone page, and the always-visible fallback.
import { element } from '../dom.js';
import { createQrSvg } from './qr.js';

export const FALLBACK_LINE = 'Or use any tuner app or keyboard that plays these notes.';

export const noteLabel = (note) => `${note.name} - ${note.hz} Hz`;

// Returns the block. The notes with their Hz and the fallback line are always there, even if the QR code cannot be drawn.
export function renderIntro({ notes, url, addressNote }) {
  const block = element('section', '', 'calibrate-intro');
  block.append(element('p', 'On your phone or another device, scan this code to open the tone page. It plays the three notes.'));
  const qrBox = element('div', '', 'calibrate-qr');
  try {
    qrBox.append(createQrSvg(url));
  } catch (err) {
    console.error('Could not draw the QR code:', err);
    qrBox.append(element('p', 'The QR code could not be drawn. Type the address below instead.', 'muted'));
  }
  block.append(qrBox, element('p', url, 'calibrate-address'));
  if (addressNote) block.append(element('p', addressNote, 'muted'));
  block.append(element('p', FALLBACK_LINE));
  const list = element('ul', '', 'calibrate-notes');
  notes.forEach((note) => list.append(element('li', noteLabel(note))));
  block.append(list);
  return block;
}

// File tab: upload a MusicXML or MIDI file.
import { uploadScoreFile } from '../api.js';
import { card } from '../ui/card.js';
import { button, el, runGuarded } from './ui.js';

export const SCORE_FILE_TYPES = '.musicxml,.xml,.mxl,.mid,.midi';

export function createFileTab({ submit }) {
  const input = el('input', { attrs: { type: 'file', accept: SCORE_FILE_TYPES } });
  const upload = button('Use this file', () => runGuarded([upload], () => submit((sessionId) => uploadScoreFile(sessionId, input.files[0]), 'file')), 'btn btn-primary primary');
  upload.disabled = true;
  input.addEventListener('change', () => { upload.disabled = input.files.length === 0; });
  return card({
    title: 'Upload a score file',
    body: [
      el('p', { text: 'MusicXML (.musicxml, .xml, .mxl) or MIDI (.mid, .midi), up to 5 MB.', className: 'muted' }),
      el('p', { className: 'file-row', children: [input, ' ', upload] }),
    ],
  });
}

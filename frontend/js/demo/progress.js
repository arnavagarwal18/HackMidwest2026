// The upload progress line of the demo video: a bar plus "42% (4.6 of 10.9 MB)".
import { el } from '../score/ui.js';

const MEGABYTE = 1024 * 1024;
const megabytes = (bytes) => (bytes / MEGABYTE).toFixed(1);

export function describeProgress({ loaded, total }) {
  const percent = Math.min(100, Math.floor((loaded / total) * 100));
  return `Uploading the video: ${percent}% (${megabytes(loaded)} of ${megabytes(total)} MB)`;
}

export function createUploadProgress() {
  const bar = el('progress', { attrs: { max: '100', value: '0' } });
  const label = el('span', { className: 'muted' });
  const root = el('p', { className: 'demo-progress', children: [bar, ' ', label] });
  root.hidden = true;
  return {
    element: root,
    reset() {
      bar.setAttribute('value', '0');
      label.textContent = 'Uploading the video: 0%';
      root.hidden = false;
    },
    update(progress) {
      bar.setAttribute('value', String(Math.floor((progress.loaded / progress.total) * 100)));
      label.textContent = describeProgress(progress);
    },
    hide() { root.hidden = true; },
  };
}

// The live camera preview with the guide outline on top and the "In frame" badge underneath.
// attach(stream) shows the preview and starts the once-a-second camera checks; pauseChecks() and detach() stop them.
import { el } from '../score/ui.js';
import { describeCameraCheck, UNAVAILABLE_CODE, UNAVAILABLE_TEXT } from './camera_status.js';
import { createCameraChecker } from './camera_checker.js';
import { createCameraGuide } from './camera_guide.js';
import { captureFrame } from './frame_capture.js';

// check(jpegBlob) is the camera-check call for this session (api.js checkCamera).
export function createCameraPanel({ instrument, check }) {
  const video = el('video', { attrs: { autoplay: '', playsinline: '', 'aria-label': 'Camera preview' } });
  video.muted = true; // the mic is in the stream; playing it back would feed the clicks and the sound into the mic
  const badge = el('p', { className: 'camera-badge', attrs: { role: 'status' } });
  const note = el('p', { className: 'muted camera-note' });
  badge.hidden = true;
  const stage = el('div', { className: 'camera-stage', children: [video, createCameraGuide(instrument)] });
  const element = el('div', { className: 'camera-panel', children: [stage, badge, note] });
  element.hidden = true;

  const checker = createCameraChecker({
    captureFrame: () => captureFrame(video),
    check,
    onResult(answer) {
      const { ok, text } = describeCameraCheck(answer);
      badge.hidden = false;
      badge.textContent = text;
      badge.className = `camera-badge ${ok ? 'camera-ok' : 'camera-warn'}`;
    },
    onFailure(err) {
      badge.hidden = true;
      note.textContent = err.code === UNAVAILABLE_CODE ? UNAVAILABLE_TEXT : `The camera check stopped: ${err.message} You can still record.`;
    },
  });

  function pauseChecks() {
    checker.stop();
    badge.hidden = true;
  }

  return {
    element,
    get checking() { return checker.running; },
    attach(stream) {
      video.srcObject = stream;
      element.hidden = false;
      note.textContent = '';
      checker.start();
    },
    pauseChecks,
    detach() {
      pauseChecks();
      video.srcObject = null;
      element.hidden = true;
    },
  };
}

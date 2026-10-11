// The live camera preview with the guide outline on top and the "In frame" badge underneath.
// attach(stream) shows the preview and starts the once-a-second camera checks; pauseChecks() and detach() stop them.
import { el } from '../score/ui.js';
import { describeCameraCheck, UNAVAILABLE_CODE, UNAVAILABLE_TEXT } from './camera_status.js';
import { createCameraChecker } from './camera_checker.js';
import { createCameraGuide } from './camera_guide.js';
import { apiViewOf, isSideView, loadView, saveView, SIDE_NOTE, VIEWS } from './camera_view.js';
import { captureFrame } from './frame_capture.js';

// check(jpegBlob, view) is the camera-check call for this session (api.js checkCamera); view is 'front', 'left' or 'right'.
export function createCameraPanel({ instrument, check }) {
  const video = el('video', { attrs: { autoplay: '', playsinline: '', 'aria-label': 'Camera preview' } });
  video.muted = true; // the mic is in the stream; playing it back would feed the clicks and the sound into the mic
  const badge = el('p', { className: 'camera-badge', attrs: { role: 'status' } });
  const note = el('p', { className: 'muted camera-note' });
  badge.hidden = true;
  let view = loadView();
  let lastAnswer = null; // re-described when the learner changes the view, without waiting for the next check
  const guideHost = el('div', { className: 'camera-guide-host', children: [createCameraGuide(instrument, view)] });
  const stage = el('div', { className: 'camera-stage', children: [video, guideHost] });
  const viewSelect = el('select', { attrs: { id: 'camera-view', 'aria-label': 'Camera view' },
    children: VIEWS.map(({ id, label, hint }) => el('option', { text: label, attrs: { value: id, ...(hint ? { title: hint } : {}) } })) });
  viewSelect.value = view;
  const viewNote = el('p', { className: 'muted camera-note', text: SIDE_NOTE });
  const element = el('div', { className: 'camera-panel', children: [stage, el('label', { text: 'Camera view ', className: 'field camera-field', children: [viewSelect] }), viewNote, badge, note] });
  element.hidden = true;

  function showAnswer(answer) {
    const { ok, text } = describeCameraCheck(answer, view);
    badge.hidden = false;
    badge.textContent = text;
    badge.className = `camera-badge ${ok ? 'camera-ok' : 'camera-warn'}`;
  }

  function showView() {
    guideHost.replaceChildren(createCameraGuide(instrument, view));
    viewNote.hidden = !isSideView(view);
    if (lastAnswer && !badge.hidden) showAnswer(lastAnswer);
  }

  viewSelect.addEventListener('change', () => {
    view = viewSelect.value;
    saveView(view);
    showView();
  });
  viewNote.hidden = !isSideView(view);

  const checker = createCameraChecker({
    captureFrame: () => captureFrame(video),
    check: (jpeg) => check(jpeg, apiViewOf(view)),
    onResult(answer) {
      lastAnswer = answer;
      showAnswer(answer);
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
    get view() { return view; },
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

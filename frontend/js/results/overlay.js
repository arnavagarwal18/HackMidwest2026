// The body-lines overlay on a video take's results: a canvas over the <video> that draws the tracked pose and hands,
// red points and the label while a form flag is active, an off checkbox, and the form flag list.
// The tracks (several MB) are fetched once, when form_status is 'done'; a failure hides the overlay and is not retried.
import { getTracks } from '../api.js';
import { element } from '../dom.js';
import { drawOverlay } from './overlay/draw.js';
import { renderFlagList } from './overlay/flag_list.js';
import { activeFlags } from './overlay/flag_points.js';
import { nearestFrame } from './overlay/frames.js';
import { contentRect } from './overlay/geometry.js';

export const UNAVAILABLE_TEXT = 'Body lines unavailable';
export const TOGGLE_TEXT = 'Show body lines';

const objectFitOf = (video) => globalThis.getComputedStyle?.(video).objectFit || 'contain';

function validTracks(tracks) {
  return Array.isArray(tracks?.frames) && tracks.frames.every((frame) => Number.isFinite(frame?.t));
}

// rendered: what renderDone returned ({ index, jumper, player, analysis }). context: { sessionId, take }.
// deps (for tests): getTracks, requestAnimationFrame, cancelAnimationFrame, win, objectFitOf.
// Returns { onAnalysis(analysis), destroy() }, or null for a mic take (no video, no overlay, no tracks fetch).
export function mountOverlay(rendered, { sessionId, take }, deps = {}) {
  const { player, analysis, index, jumper } = rendered;
  const video = player.mediaElement;
  if (video.tagName !== 'VIDEO') return null;
  const {
    getTracks: fetchTracks = getTracks, win = window, fitOf = objectFitOf,
    requestAnimationFrame: raf = (fn) => globalThis.requestAnimationFrame(fn),
    cancelAnimationFrame: caf = (id) => globalThis.cancelAnimationFrame(id),
  } = deps;
  const flags = analysis.form ?? [];
  let tracks = null;
  let canvas = null;
  let ctx = null;
  let frameId = null;
  let requested = false;
  let destroyed = false;

  const controls = element('div', '', 'overlay-controls'); // the checkbox, or the note when the tracks failed
  const flagList = renderFlagList(flags, { index, jumper });
  player.formFlagSlot.append(controls);
  if (flagList) player.formFlagSlot.append(flagList);

  function clear() {
    ctx?.clearRect(0, 0, canvas.width, canvas.height);
  }

  function fitCanvasToVideo() {
    const { clientWidth: width, clientHeight: height } = video;
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    return { width, height };
  }

  function drawNow() {
    const box = fitCanvasToVideo();
    clear();
    const frame = nearestFrame(tracks.frames, video.currentTime);
    if (!frame || !box.width || !box.height) return;
    const intrinsic = video.videoWidth ? { width: video.videoWidth, height: video.videoHeight } : { width: tracks.width, height: tracks.height };
    drawOverlay(ctx, { frame, rect: contentRect(box, intrinsic, fitOf(video)), flags: activeFlags(flags, video.currentTime) });
  }

  function tick() {
    frameId = null;
    if (destroyed) return;
    if (!canvas.isConnected) { destroy(); return; } // the router replaced the screen
    drawNow();
    frameId = raf(tick);
  }

  function startLoop() {
    if (frameId === null && !destroyed) frameId = raf(tick);
  }

  function stopLoop() {
    if (frameId !== null) caf(frameId);
    frameId = null;
  }

  function showToggle() {
    const toggle = element('input', '', '', { type: 'checkbox', id: 'overlay-toggle' });
    toggle.checked = true;
    toggle.addEventListener('change', () => {
      if (toggle.checked) startLoop();
      else { stopLoop(); clear(); }
    });
    const label = element('label', '', 'overlay-toggle');
    label.append(toggle, element('span', ` ${TOGGLE_TEXT}`));
    controls.append(label);
  }

  function showUnavailable(err) {
    console.error('The body lines could not be loaded:', err);
    controls.append(element('span', UNAVAILABLE_TEXT, 'muted overlay-note', { role: 'status' }));
  }

  async function load() {
    requested = true;
    let loaded;
    try {
      loaded = await fetchTracks(sessionId, take);
      if (!validTracks(loaded)) throw new Error('The tracks answer has no frames list.');
    } catch (err) {
      if (!destroyed) showUnavailable(err);
      return;
    }
    if (destroyed) return;
    if (!video.isConnected) { destroy(); return; }
    tracks = loaded;
    canvas = element('canvas', '', 'overlay-canvas', { 'aria-hidden': 'true' });
    ctx = canvas.getContext('2d');
    player.stage.append(canvas);
    showToggle();
    startLoop();
  }

  function destroy() {
    destroyed = true;
    stopLoop();
    win.removeEventListener('hashchange', destroy);
    canvas?.remove();
  }

  win.addEventListener('hashchange', destroy);

  return {
    // Call with each analysis seen; the one fetch happens the first time form_status is 'done'.
    onAnalysis(latest) {
      if (!requested && !destroyed && latest.form_status === 'done') load();
    },
    destroy,
  };
}

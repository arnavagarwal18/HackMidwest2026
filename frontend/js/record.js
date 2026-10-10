// Recording for the take setup, loop trainer and calibration screens. See "Recording and metronome" in frontend/README.md.
// All timestamps come from the shared AudioContext clock (audio.js), never from setTimeout.
import { getAudioContext } from './audio.js';
import { scheduleClick, startMetronome } from './metronome.js';
import { MediaAccessError, toMediaAccessError } from './media_error.js';

export { MediaAccessError, renderMediaError, HELP_LINE } from './media_error.js';
export { getAudioContext } from './audio.js';

export const MAX_TAKE_SECONDS = 180;
export const COUNT_IN_LEAD_S = 0.5; // the first click comes this long after the recorder starts
const VIDEO_CONSTRAINTS = { width: { ideal: 1280 }, height: { ideal: 720 } };
const DEVICE_ERRORS = ['NotAllowedError', 'SecurityError', 'NotFoundError', 'OverconstrainedError', 'NotReadableError', 'AbortError'];

async function openAudio() {
  try {
    return await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    throw toMediaAccessError('mic', err);
  }
}

// Opens the mic (and the camera when video is true). Resolves { stream, hasVideo, cameraError }.
// If only the camera fails, the stream is mic-only and cameraError says why (show it as a notice).
// Throws MediaAccessError { device: 'mic' | 'camera', reason, message } when the mic itself fails.
// Never retries: the screen calls it again only when the learner presses Try again.
export async function openStream({ video = false } = {}) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    console.error('navigator.mediaDevices is unavailable (the page needs https or localhost).');
    throw new MediaAccessError('mic', 'unknown');
  }
  if (!video) {
    return { stream: await openAudio(), hasVideo: false, cameraError: null };
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: VIDEO_CONSTRAINTS });
    return { stream, hasVideo: true, cameraError: null };
  } catch (err) {
    if (!DEVICE_ERRORS.includes(err && err.name)) throw toMediaAccessError('mic', err);
    // The error does not say which device failed. If the mic alone opens, the camera was the problem.
    const stream = await openAudio();
    return { stream, hasVideo: false, cameraError: toMediaAccessError('camera', err) };
  }
}

export function stopStream(stream) {
  stream.getTracks().forEach((track) => track.stop());
}

function pickMimeType(stream) {
  const type = stream.getVideoTracks().length ? 'video/webm' : 'audio/webm';
  return MediaRecorder.isTypeSupported(type) ? type : '';
}

// Starts a MediaRecorder; resolves once its 'start' event fired, with recStart = audioCtx.currentTime when start() was called.
// stop() returns a promise of { blob, file, mimeType}; it rejects if the recorder failed or recorded nothing.
async function startRecorder(stream) {
  const audioCtx = await getAudioContext();
  const requestedType = pickMimeType(stream);
  const recorder = new MediaRecorder(stream, requestedType ? { mimeType: requestedType } : undefined);
  const chunks = [];
  recorder.addEventListener('dataavailable', (event) => event.data.size && chunks.push(event.data));

  const finished = new Promise((resolve, reject) => {
    recorder.addEventListener('error', (event) => {
      console.error('MediaRecorder failed:', event.error);
      reject(new Error('Recording stopped unexpectedly. Please try again.'));
    });
    recorder.addEventListener('stop', () => {
      const mimeType = recorder.mimeType || requestedType || 'audio/webm';
      const blob = new Blob(chunks, { type: mimeType });
      if (!blob.size) {
        console.error('MediaRecorder stopped with no data.');
        reject(new Error('Nothing was recorded. Check that the microphone works, then try again.'));
        return;
      }
      resolve({ blob, file: new File([blob], 'recording.webm', { type: mimeType }), mimeType });
    });
  });
  finished.catch(() => {}); // the caller handles it through stop(); this only avoids a duplicate unhandled report

  // recStart is read just before start(): in Chrome the file's time zero matches that moment (measured: the 'start'
  // event arrives about 60 ms later, so reading the clock there would put every click 60 ms off in the file).
  const recStart = audioCtx.currentTime;
  await new Promise((resolve, reject) => {
    recorder.addEventListener('start', resolve, { once: true });
    recorder.addEventListener('error', (event) => reject(event.error), { once: true });
    recorder.start();
  });
  const stop = () => {
    if (recorder.state !== 'inactive') recorder.stop();
    return finished;
  };
  return { audioCtx, recStart, stop };
}

// Records a take with a count-in. Resolves once recording has started, with a handle:
//   handle.recStart  AudioContext time when the recorder was started (time zero of the file)
//   handle.stop()    Promise of { blob, file, mimeType, downbeat_s, duration_s, autoStopped, message }; safe to call twice
// downbeat_s = seconds from the recording start to the first beat after the count-in
//            = COUNT_IN_LEAD_S + countInBeats * 60 / tempoBpm.
// metronomeOn keeps clicking after the count-in, in the same beat grid. maxSeconds caps the length (take 180, rep 60):
// at the cap the recording stops by itself and onAutoStop(result) runs (result.message says why, for the screen to show);
// if that stop fails, onAutoStop(null, error) runs.
// Keep result.blob in memory until the upload succeeded, so the Retry button can send it again.
export async function recordTake({ stream, tempoBpm, countInBeats = 4, metronomeOn = false, beatsPerBar = 4,
  maxSeconds = MAX_TAKE_SECONDS, onAutoStop = null }) {
  const { audioCtx, recStart, stop: stopRecorder } = await startRecorder(stream);
  const firstClick = recStart + COUNT_IN_LEAD_S;
  if (audioCtx.currentTime > firstClick) {
    await stopRecorder().catch(() => {});
    console.error(`The recorder took ${audioCtx.currentTime - recStart} s to start; too late to schedule the count-in.`);
    throw new Error('The microphone was slow to start, so the count-in could not play. Please try again.');
  }
  const downbeatS = firstClick + (countInBeats * 60) / tempoBpm - recStart;
  const clicks = (countInBeats > 0 || metronomeOn)
    ? startMetronome({ audioCtx, tempoBpm, startTime: firstClick, beatsPerBar, maxBeats: metronomeOn ? Infinity : countInBeats })
    : null;

  let autoStopped = false;
  let stopping = null;
  const handle = {
    recStart,
    stop() {
      if (!stopping) {
        stopping = stopRecorder().then((recorded) => ({
          ...recorded,
          downbeat_s: downbeatS,
          duration_s: audioCtx.currentTime - recStart,
          autoStopped,
          message: autoStopped ? `Recording stopped at the ${maxSeconds}-second limit.` : null,
        })).finally(() => {
          clearTimeout(capTimer);
          if (clicks) clicks.stop();
        });
      }
      return stopping;
    },
  };
  const capTimer = setTimeout(async () => {
    autoStopped = true;
    try {
      const result = await handle.stop();
      if (onAutoStop) onAutoStop(result);
    } catch (err) {
      console.error('Stopping at the time cap failed:', err);
      if (onAutoStop) onAutoStop(null, err);
    }
  }, maxSeconds * 1000);
  return handle;
}

// A short fixed-length clip (calibration: 3 s per note, or a 2 s clip with one click).
// clickAfterS (optional) schedules one click that long after the recording start.
// Resolves { blob, file, mimeType, click_at_s }: click_at_s = scheduled click time - recording start
// (both AudioContext time), or null when no click was asked for. The click plays through the speaker for the mic to hear.
export async function recordClip({ stream, durationS, clickAfterS = null }) {
  const { audioCtx, recStart, stop } = await startRecorder(stream);
  let clickAtS = null;
  if (clickAfterS !== null) {
    const clickTime = recStart + clickAfterS;
    scheduleClick(audioCtx, clickTime, true);
    clickAtS = clickTime - recStart;
  }
  await new Promise((resolve) => setTimeout(resolve, durationS * 1000));
  return { ...(await stop()), click_at_s: clickAtS };
}

// Input level meter. onLevel(level) gets 0..1 (RMS, scaled) once per animation frame until stop().
export async function createLevelMeter(stream, onLevel) {
  const audioCtx = await getAudioContext();
  const analyser = audioCtx.createAnalyser();
  analyser.fftSize = 1024;
  const source = audioCtx.createMediaStreamSource(stream);
  source.connect(analyser); // not connected to the speakers, so no feedback
  const samples = new Float32Array(analyser.fftSize);
  let frame = 0;
  const tick = () => {
    analyser.getFloatTimeDomainData(samples);
    const rms = Math.sqrt(samples.reduce((sum, v) => sum + v * v, 0) / samples.length);
    onLevel(Math.min(1, rms * 4));
    frame = requestAnimationFrame(tick);
  };
  tick();
  return {
    stop() {
      cancelAnimationFrame(frame);
      source.disconnect();
    },
  };
}

// A ready-made <meter> in `container`. Returns { stop }, which also removes the meter.
export async function renderLevelMeter(container, stream) {
  const meter = document.createElement('meter');
  meter.min = 0;
  meter.max = 1;
  meter.value = 0;
  meter.setAttribute('aria-label', 'Microphone level');
  container.append(meter);
  const running = await createLevelMeter(stream, (level) => { meter.value = level; });
  return { stop() { running.stop(); meter.remove(); } };
}

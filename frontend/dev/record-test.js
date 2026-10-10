// Dev-only page logic for recording checks. Not used by the app.
import { openStream, recordTake, recordClip, renderLevelMeter, renderMediaError, getAudioContext } from '../js/record.js';

const resultEl = document.getElementById('result');
const problemEl = document.getElementById('problem');
const show = (value) => { resultEl.textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2); };
const TEMPO = 60;
const COUNT_IN = 4;

// Onsets (seconds) of clicks in a decoded recording: a sample above 25% of the peak after 80 ms of quiet.
async function findOnsets(blob) {
  const audioCtx = await getAudioContext();
  const decoded = await audioCtx.decodeAudioData(await blob.arrayBuffer());
  const data = decoded.getChannelData(0);
  const peak = data.reduce((max, v) => Math.max(max, Math.abs(v)), 0);
  const onsets = [];
  let lastLoud = -Infinity;
  data.forEach((v, i) => {
    if (Math.abs(v) < peak * 0.25) return;
    if (i - lastLoud > decoded.sampleRate * 0.08) onsets.push(i / decoded.sampleRate);
    lastLoud = i;
  });
  return { onsets, duration: decoded.duration, peak };
}

// A stream of the page's own clicks (a copy of what goes to the speakers), so the check needs no speaker or mic.
async function loopbackStream() {
  const audioCtx = await getAudioContext();
  const tap = audioCtx.createMediaStreamDestination();
  const silence = audioCtx.createConstantSource(); // a recorder only starts once its stream carries audio
  silence.offset.value = 0;
  silence.connect(tap);
  silence.start();
  const connect = AudioNode.prototype.connect;
  AudioNode.prototype.connect = function patched(target, ...rest) {
    if (target === audioCtx.destination) connect.call(this, tap);
    return connect.call(this, target, ...rest);
  };
  return tap.stream;
}

async function runCountInCheck(stream) {
  const handle = await recordTake({ stream, tempoBpm: TEMPO, countInBeats: COUNT_IN, metronomeOn: true, maxSeconds: 60 });
  await new Promise((resolve) => setTimeout(resolve, 6200));
  const result = await handle.stop();
  const { onsets, duration } = await findOnsets(result.blob);
  const firstAfterCountIn = onsets.find((t) => t > result.downbeat_s - 0.25);
  return {
    downbeat_s: result.downbeat_s,
    onsets,
    first_click_after_count_in: firstAfterCountIn,
    error_ms: Math.round((firstAfterCountIn - result.downbeat_s) * 10000) / 10,
    mimeType: result.mimeType,
    blob_bytes: result.blob.size,
    decoded_duration_s: duration,
  };
}

async function runLoopback() {
  const stream = await loopbackStream();
  await new Promise((resolve) => setTimeout(resolve, 1000));
  show(await runCountInCheck(stream));
}

async function runClip() {
  const clip = await recordClip({ stream: await loopbackStream(), durationS: 2, clickAfterS: 0.5 });
  show({ click_at_s: clip.click_at_s, onsets: (await findOnsets(clip.blob)).onsets, bytes: clip.blob.size });
}

// Needs a real or fake device: opens mic + camera, shows the level meter, records 3 s with a 2 s cap.
async function runDevice() {
  const { stream, hasVideo, cameraError } = await openStream({ video: true });
  const meter = await renderLevelMeter(document.getElementById('meter'), stream);
  let level = 0;
  const sampler = setInterval(() => { level = Math.max(level, document.querySelector('#meter meter').value); }, 50);
  let autoStop = null;
  const handle = await recordTake({ stream, tempoBpm: 120, countInBeats: 2, maxSeconds: 2, onAutoStop: (r, err) => { autoStop = r ? r.message : `error ${err.message}`; } });
  await new Promise((resolve) => setTimeout(resolve, 3000));
  const result = await handle.stop();
  clearInterval(sampler);
  meter.stop();
  show({ hasVideo, cameraError, max_level: level, autoStop, downbeat_s: result.downbeat_s, mimeType: result.mimeType,
    duration_s: result.duration_s, autoStopped: result.autoStopped, message: result.message,
    file: `${result.file.name} ${result.file.size} bytes`, blobKept: result.blob.size > 0 });
}

async function runBlocked() {
  try {
    await openStream();
    show('unexpected: the mic opened');
  } catch (err) {
    renderMediaError(problemEl, err, { onTryAgain: () => show('Try again pressed'), onUpload: () => show('Upload chosen') });
    show({ device: err.device, reason: err.reason, message: err.message, block: problemEl.innerText });
  }
}

let takeHandle = null;
document.getElementById('mic-take').addEventListener('click', async () => {
  try {
    const { stream } = await openStream();
    await renderLevelMeter(document.getElementById('meter'), stream);
    takeHandle = await recordTake({ stream, tempoBpm: TEMPO, countInBeats: COUNT_IN, metronomeOn: true, onAutoStop: (r) => show(r.message) });
    document.getElementById('stop-take').disabled = false;
    show('recording...');
  } catch (err) {
    renderMediaError(problemEl, err, { onTryAgain: () => document.getElementById('mic-take').click() });
  }
});
document.getElementById('stop-take').addEventListener('click', async () => {
  const { blob, file, ...rest } = await takeHandle.stop();
  show({ ...rest, bytes: blob.size, onsets: (await findOnsets(blob)).onsets });
});
document.getElementById('loopback').addEventListener('click', () => runLoopback().catch((e) => show(`failed: ${e.message}`)));

document.getElementById('clip').addEventListener('click', () => runClip().catch((e) => show(`failed: ${e.message}`)));

const auto = new URLSearchParams(location.search).get('auto');
document.getElementById('device').addEventListener('click', () => runDevice().catch((e) => show(`failed: ${e.message}`)));
const checks = { loopback: runLoopback, clip: runClip, blocked: runBlocked };
if (checks[auto]) checks[auto]().catch((e) => show(`failed: ${e.message}`));

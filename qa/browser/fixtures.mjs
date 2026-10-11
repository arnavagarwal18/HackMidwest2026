// Builds real-mode test data through the real API (no AI: the server must run with AI_ENABLED unset or false):
// a confirmed session with one analysed take (transcribed from a synthetic recording), its fallback feedback and plan, and one take that failed.
import { mkdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { synthTakeWav } from './synth_take.mjs';

const SCRATCH_DIR = new URL('./.scratch/', import.meta.url).pathname;
const SILENT_TAKE = new URL('../../frontend/mock/take_media.wav', import.meta.url).pathname; // no notes in it: the take fails
const ANALYSIS_TIMEOUT_MS = 90000;
const POLL_MS = 1000;

async function call(origin, method, path, { json, form } = {}) {
  const response = await fetch(`${origin}${path}`, {
    method,
    headers: json ? { 'content-type': 'application/json' } : undefined,
    body: json ? JSON.stringify(json) : form,
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`Fixture step failed: ${method} ${path} -> HTTP ${response.status} ${text.slice(0, 300)}`);
  return JSON.parse(text);
}

const takeForm = (wavPath) => {
  const form = new FormData();
  form.set('file', new Blob([readFileSync(wavPath)], { type: 'audio/wav' }), 'take.wav');
  Object.entries({ kind: 'mic', source: 'uploaded', bar_from: '1', bar_to: '2', tempo_bpm: '100', count_in_beats: '0' }).forEach(([k, v]) => form.set(k, v));
  return form;
};

async function waitForAnalysis(origin, sessionId, takeId) {
  const deadline = Date.now() + ANALYSIS_TIMEOUT_MS;
  for (;;) {
    const analysis = await call(origin, 'GET', `/sessions/${sessionId}/takes/${takeId}/analysis`);
    if (analysis.status !== 'processing') return analysis;
    if (Date.now() > deadline) throw new Error(`Take ${takeId} was still processing after ${ANALYSIS_TIMEOUT_MS} ms.`);
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
}

async function newSession(origin) {
  return (await call(origin, 'POST', '/sessions', { json: { instrument: 'trumpet' } })).session_id;
}

async function confirmedSession(origin) {
  const sessionId = await newSession(origin);
  const [piece] = await call(origin, 'GET', '/builtins?instrument=trumpet');
  await call(origin, 'POST', `/sessions/${sessionId}/score/file`, { json: { builtin: piece.piece_id } });
  await call(origin, 'POST', `/sessions/${sessionId}/score/confirm`);
  await call(origin, 'POST', `/sessions/${sessionId}/calibration/skip`);
  return sessionId;
}

export async function buildRealFixtures(origin) {
  mkdirSync(SCRATCH_DIR, { recursive: true });
  const goodWav = join(SCRATCH_DIR, 'take.wav');
  synthTakeWav(goodWav);
  const unconfirmedSessionId = await newSession(origin);
  const sessionId = await confirmedSession(origin);
  const failedTake = await call(origin, 'POST', `/sessions/${sessionId}/takes`, { form: takeForm(SILENT_TAKE) });
  const goodTake = await call(origin, 'POST', `/sessions/${sessionId}/takes`, { form: takeForm(goodWav) });
  const failedAnalysis = await waitForAnalysis(origin, sessionId, failedTake.take_id);
  const goodAnalysis = await waitForAnalysis(origin, sessionId, goodTake.take_id);
  if (goodAnalysis.status !== 'done') throw new Error(`The synthetic take did not analyse: ${JSON.stringify(goodAnalysis.error)}`);
  const feedback = await call(origin, 'POST', `/sessions/${sessionId}/takes/${goodTake.take_id}/feedback`);
  const progress = await call(origin, 'GET', `/sessions/${sessionId}/progress`);
  return {
    unconfirmedSessionId,
    sessionId,
    goodTakeId: goodTake.take_id,
    failedTakeId: failedTake.take_id,
    failedTakeStatus: failedAnalysis.status,
    feedbackId: feedback.id,
    exerciseId: progress.exercises[0]?.id ?? 'ex_none',
  };
}

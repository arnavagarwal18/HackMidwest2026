// Every back-end call, as a named function. Screens import from here and never call fetch themselves.
// Each function takes the session id explicitly (state.session_id) and resolves to the parsed JSON body.
// On an HTTP 4xx/5xx it throws ApiError { code, message, status, details }; the screen shows
// err.message in the red banner (reportError in banner.js) and keeps the learner's inputs.
// If the server is unreachable the call waits for the learner to press Retry in the banner.
import { API_BASE, MOCK_MODE } from './config.js';
import { get, postForm, postJson } from './http.js';
import { MOCK_MEDIA_URL } from './mock.js';

import { ApiError } from './http.js';

export { ApiError };
export { MOCK_MODE };

// A 404 means there is nothing there yet (no trace, no progress): screens show an empty state instead of the error banner.
export const isNotFound = (err) => err instanceof ApiError && err.status === 404;

const sess = (id) => `/sessions/${encodeURIComponent(id)}`;
const withInstrument = (path, instrument) => (instrument ? `${path}?instrument=${encodeURIComponent(instrument)}` : path);

// ---- Session and score (LLD-1) ----
export const createSession = (instrument) => postJson('/sessions', { instrument });
export const getSession = (id) => get(sess(id));
export const getBuiltins = (instrument) => get(withInstrument('/builtins', instrument));
export const uploadScorePhoto = (id, file) => postForm(`${sess(id)}/score/photo`, { file });
export const getScoreStatus = (id) => get(`${sess(id)}/score/status`); // poll while score_status is 'scanning'
export const uploadScoreFile = (id, file) => postForm(`${sess(id)}/score/file`, { file });
export const chooseBuiltinScore = (id, pieceId) => postJson(`${sess(id)}/score/file`, { builtin: pieceId });
export const confirmScore = (id) => postJson(`${sess(id)}/score/confirm`);

// The score as JSON: { title, tempo_bpm, time_signature, bars: [...] }. Used to learn the bar count after a reload.
export const getScore = (id) => get(`${sess(id)}/score?format=json`);

// ---- Calibration (LLD-2) ----
export const getReferenceNotes = (instrument) => get(withInstrument('/reference-notes', instrument));
// files: { ref_0, ref_1, ref_2, click, inst_0?, inst_1?, inst_2? }; a 422 calibration_failed has err.details.notes.
export const submitCalibration = (id, files, clickAtS) => postForm(`${sess(id)}/calibration`, files, { click_at_s: clickAtS });
export const skipCalibration = (id) => postJson(`${sess(id)}/calibration/skip`);
export const getCalibration = (id) => get(`${sess(id)}/calibration`);

// ---- Takes and analysis (LLD-2, LLD-3) ----
// fields: { kind, source, bar_from, bar_to, tempo_bpm, count_in_beats, downbeat_s }; onProgress({ loaded, total }) is optional.
export const uploadTake = (id, file, fields, onProgress) => postForm(`${sess(id)}/takes`, { file }, fields, onProgress);
export const takeMediaUrl = (id, take) => (MOCK_MODE ? MOCK_MEDIA_URL : `${API_BASE}${sess(id)}/takes/${encodeURIComponent(take)}/media`);
export const getAnalysis = (id, take) => get(`${sess(id)}/takes/${encodeURIComponent(take)}/analysis`); // poll until status is 'done' or 'failed'
export const setTransposition = (id, semitones) => postJson(`${sess(id)}/transposition`, { semitones });

// ---- Form (LLD-4) ----
export const getTracks = (id, take) => get(`${sess(id)}/takes/${encodeURIComponent(take)}/tracks`);
// view: 'front' | 'left' | 'right' (the learner's pick in the camera panel); left out when there is none, so the server detects it.
export const checkCamera = (id, jpeg, view) => postForm(`${sess(id)}/camera-check`, { file: jpeg }, view ? { view } : {});

// ---- Feedback, trace and chat (LLD-5) ----
export const getFeedback = (id, take) => get(`${sess(id)}/takes/${encodeURIComponent(take)}/feedback`);
export const getTrace = (id, feedbackId) => get(`${sess(id)}/feedback/${encodeURIComponent(feedbackId)}/trace`);
export const getChat = (id) => get(`${sess(id)}/chat`);
export const sendChat = (id, message, takeId = null) => postJson(`${sess(id)}/chat`, { message, take_id: takeId });

// ---- Practice and progress (LLD-6) ----
export const getExercise = (id, ex) => get(`${sess(id)}/exercises/${encodeURIComponent(ex)}`);
// fields: { kind, source, downbeat_s }
export const uploadRep = (id, ex, file, fields) => postForm(`${sess(id)}/exercises/${encodeURIComponent(ex)}/reps`, { file }, fields);
export const getRep = (id, ex, rep) => get(`${sess(id)}/exercises/${encodeURIComponent(ex)}/reps/${encodeURIComponent(rep)}`); // poll while 'processing'
export const getProgress = (id) => get(`${sess(id)}/progress`);

// ---- Phone link ----
export const getLanAddress = () => get('/lan-address');

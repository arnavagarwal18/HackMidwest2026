// Mock mode (?mock=1): answers requests from frontend/mock/*.json instead of the back end.
//
// Each route below maps method + path pattern to one saved response, frontend/mock/<file>.json.
// Polled routes (poll) answer with <processingFile> (one file, or a list: one per poll) for their first `polls` requests, then with
// the final file, so screens can test their polling. A POST that starts the work (resets) restarts
// the count for that group. The mock only reads static files; nothing reaches a real route.
const MOCK_DELAY_MS = 150;

export const MOCK_MEDIA_URL = 'mock/take_media_long.wav'; // 12 s, so a jump to a few seconds in has somewhere to land

// Requests the mock has answered, oldest first: { method, path, body } (body only when it is JSON). Tests read this.
export const mockRequestLog = [];

const ROUTES = [
  { method: 'POST', pattern: '/sessions', file: 'post_sessions' },
  { method: 'GET', pattern: '/sessions/:id', file: 'get_session' },
  { method: 'GET', pattern: '/builtins', file: 'get_builtins' },
  { method: 'POST', pattern: '/sessions/:id/score/photo', file: 'post_score_photo', resets: 'score_status' },
  { method: 'GET', pattern: '/sessions/:id/score', file: 'get_score' },
  { method: 'GET', pattern: '/sessions/:id/score/status', file: 'get_score_status',
    poll: { group: 'score_status', processingFile: 'get_score_status_processing', polls: 2 } },
  { method: 'POST', pattern: '/sessions/:id/score/file', file: 'post_score_file' },
  { method: 'POST', pattern: '/sessions/:id/score/confirm', file: 'post_score_confirm' },
  { method: 'GET', pattern: '/reference-notes', file: 'get_reference_notes' },
  { method: 'POST', pattern: '/sessions/:id/calibration', file: 'post_calibration' },
  { method: 'POST', pattern: '/sessions/:id/calibration/skip', file: 'post_calibration_skip' },
  { method: 'GET', pattern: '/sessions/:id/calibration', file: 'get_calibration' },
  { method: 'POST', pattern: '/sessions/:id/takes', file: 'post_takes', resets: ['analysis', 'feedback'] },
  { method: 'GET', pattern: '/sessions/:id/takes/:take/analysis', file: 'get_analysis',
    poll: { group: 'analysis', processingFile: ['get_analysis_processing', 'get_analysis_transcribed'] } },
  { method: 'POST', pattern: '/sessions/:id/transposition', file: 'post_transposition', resets: ['analysis', 'feedback'] },
  { method: 'GET', pattern: '/sessions/:id/takes/:take/tracks', file: 'get_tracks' },
  { method: 'POST', pattern: '/sessions/:id/camera-check', file: 'post_camera_check_ok',
    poll: { group: 'camera', processingFile: 'post_camera_check', polls: 3 } },
  { method: 'GET', pattern: '/sessions/:id/takes/:take/feedback', file: 'get_feedback',
    poll: { group: 'feedback', processingFile: 'error_feedback_not_ready' } },
  { method: 'POST', pattern: '/sessions/:id/takes/:take/feedback', file: 'post_feedback' },
  { method: 'GET', pattern: '/sessions/:id/feedback/:fb/trace', file: 'get_trace' },
  { method: 'GET', pattern: '/sessions/:id/chat', file: 'get_chat' },
  { method: 'POST', pattern: '/sessions/:id/chat', file: 'post_chat' },
  { method: 'GET', pattern: '/sessions/:id/exercises/:ex', file: 'get_exercise' },
  { method: 'POST', pattern: '/sessions/:id/exercises/:ex/reps', file: 'post_exercise_reps', resets: 'rep' },
  { method: 'GET', pattern: '/sessions/:id/exercises/:ex/reps/:rep', file: 'get_rep',
    poll: { group: 'rep', processingFile: 'get_rep_processing', polls: 1 } },
  { method: 'GET', pattern: '/sessions/:id/progress', file: 'get_progress' },
  { method: 'GET', pattern: '/lan-address', file: 'get_lan_address' },
].map((route) => ({ ...route, regex: new RegExp(`^${route.pattern.replace(/:\w+/g, '([^/]+)')}$`) }));

// Fixed session ids that let the reload behaviour be tried in mock mode.
const SESSION_VARIANTS = {
  sess_gone: 'error_session_not_found',
  sess_unconfirmed: 'get_session_unconfirmed',
};

// Take ids that change what a route answers, so a screen can be tried in each state: { takeId: { routeFile: variantFile } }.
const TAKE_VARIANTS = {
  take_mic: { get_analysis: 'get_analysis_mic' }, // a mic take: no form check
  take_failed: { get_analysis: 'get_analysis_failed' },
  take_cant_tell: { get_analysis: 'get_analysis_cant_tell', get_feedback: 'get_feedback_cant_tell' },
  take_fallback: { get_feedback: 'get_feedback_fallback', post_chat: 'post_chat_fallback' }, // the chat POST names its take in the body
  take_stuck: { get_analysis: 'get_analysis_transcribed' }, // never finishes
};

// URL switches that change an answer: ?calibration=failed makes the first POST .../calibration answer 422 calibration_failed
// (then it succeeds, as after a Retry). Read when asked, so tests can change window.location.search.
const FAILED_CALIBRATION = { group: 'calibration', processingFile: 'error_calibration_failed', polls: 1 };
const calibrationVariant = () => new URLSearchParams(window.location.search).get('calibration');

// error_*.json files stand for a failed response; most are a 404, these have their own status.
const ERROR_STATUS = { error_calibration_failed: 422 };

// Exercise ids that change what the exercise routes answer, so the loop trainer can be tried in each state.
// ex_fail / ex_not_counted: the rep is a FAIL / does not count. ex_complete: one pass from the target, and the rep completes it.
// ex_done: already complete. ex_video: the pass mark has a form rule (video).
const EXERCISE_VARIANTS = {
  ex_fail: { get_rep: 'get_rep_fail' },
  ex_not_counted: { get_rep: 'get_rep_not_counted' },
  ex_complete: { get_exercise: 'get_exercise_last_rep', get_rep: 'get_rep_complete' },
  ex_done: { get_exercise: 'get_exercise_done' },
  ex_video: { get_exercise: 'get_exercise_video' },
};

const pollCounts = new Map(); // `${group}|${path}` -> polls answered so far

function resetPolls(groups) {
  [].concat(groups).forEach((group) => {
    [...pollCounts.keys()].filter((key) => key.startsWith(`${group}|`)).forEach((key) => pollCounts.delete(key));
  });
}

// The first answers are the processing files in order (one per poll), then finalFile.
function pollFile(route, pathOnly, finalFile) {
  const processing = [].concat(route.poll.processingFile);
  const polls = route.poll.polls ?? processing.length;
  const key = `${route.poll.group}|${pathOnly}`;
  const seen = pollCounts.get(key) ?? 0;
  if (seen >= polls) return finalFile;
  pollCounts.set(key, seen + 1);
  return processing[Math.min(seen, processing.length - 1)];
}

// Picks the mock file for this request (advancing poll counters), or null when no route matches.
export function mockFileFor(method, path, requestBody) {
  const pathOnly = path.split('?')[0];
  const route = ROUTES.find((r) => r.method === method && r.regex.test(pathOnly));
  if (!route) return null;
  if (route.resets) resetPolls(route.resets);
  const takeId = /\/takes\/([^/]+)\//.exec(pathOnly)?.[1] ?? requestBody?.take_id;
  const exerciseId = /\/exercises\/([^/]+)/.exec(pathOnly)?.[1];
  const finalFile = (TAKE_VARIANTS[takeId] ?? EXERCISE_VARIANTS[exerciseId])?.[route.file] ?? route.file;
  if (route.poll) return pollFile(route, pathOnly, finalFile);
  if (route.file === 'post_calibration' && calibrationVariant() === 'failed') {
    return pollFile({ poll: FAILED_CALIBRATION }, pathOnly, finalFile);
  }
  if (route.file === 'get_session') return SESSION_VARIANTS[pathOnly.split('/')[2]] ?? route.file;
  return finalFile;
}

// Returns the same { ok, status, body } shape as a real response, or null when no mock exists.
export async function mockResponse(method, path, requestBody) {
  mockRequestLog.push({ method, path, body: requestBody instanceof FormData ? undefined : requestBody });
  const file = mockFileFor(method, path, requestBody);
  if (!file) return null;
  await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS));
  const res = await fetch(`mock/${file}.json`);
  if (!res.ok) {
    console.error(`Mock file mock/${file}.json is missing (HTTP ${res.status}).`);
    return null;
  }
  const body = await res.json();
  const isError = file.startsWith('error_'); // error_*.json files stand for a failed (non-2xx) response
  return { ok: !isError, status: isError ? (ERROR_STATUS[file] ?? 404) : 200, body };
}

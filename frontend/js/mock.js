// Mock mode (?mock=1): answers requests from frontend/mock/*.json instead of the back end.
//
// Each route below maps method + path pattern to one saved response, frontend/mock/<file>.json.
// Polled routes (poll) answer with <processingFile> for their first `polls` requests, then with
// the final file, so screens can test their polling. A POST that starts the work (resets) restarts
// the count for that group. The mock only reads static files; nothing reaches a real route.
const MOCK_DELAY_MS = 150;

export const MOCK_MEDIA_URL = 'mock/take_media.wav';

const ROUTES = [
  { method: 'POST', pattern: '/sessions', file: 'post_sessions' },
  { method: 'GET', pattern: '/sessions/:id', file: 'get_session' },
  { method: 'GET', pattern: '/builtins', file: 'get_builtins' },
  { method: 'POST', pattern: '/sessions/:id/score/photo', file: 'post_score_photo', resets: 'score_status' },
  { method: 'GET', pattern: '/sessions/:id/score/status', file: 'get_score_status',
    poll: { group: 'score_status', processingFile: 'get_score_status_processing', polls: 2 } },
  { method: 'POST', pattern: '/sessions/:id/score/file', file: 'post_score_file' },
  { method: 'POST', pattern: '/sessions/:id/score/confirm', file: 'post_score_confirm' },
  { method: 'GET', pattern: '/reference-notes', file: 'get_reference_notes' },
  { method: 'POST', pattern: '/sessions/:id/calibration', file: 'post_calibration' },
  { method: 'POST', pattern: '/sessions/:id/calibration/skip', file: 'post_calibration_skip' },
  { method: 'GET', pattern: '/sessions/:id/calibration', file: 'get_calibration' },
  { method: 'POST', pattern: '/sessions/:id/takes', file: 'post_takes', resets: 'analysis' },
  { method: 'GET', pattern: '/sessions/:id/takes/:take/analysis', file: 'get_analysis',
    poll: { group: 'analysis', processingFile: 'get_analysis_processing', polls: 2 } },
  { method: 'POST', pattern: '/sessions/:id/transposition', file: 'post_transposition' },
  { method: 'GET', pattern: '/sessions/:id/takes/:take/tracks', file: 'get_tracks' },
  { method: 'POST', pattern: '/sessions/:id/camera-check', file: 'post_camera_check' },
  { method: 'GET', pattern: '/sessions/:id/takes/:take/feedback', file: 'get_feedback' },
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

const pollCounts = new Map(); // `${group}|${path}` -> polls answered so far

function resetPolls(group) {
  [...pollCounts.keys()].filter((key) => key.startsWith(`${group}|`)).forEach((key) => pollCounts.delete(key));
}

function pollFile(route, pathOnly) {
  const key = `${route.poll.group}|${pathOnly}`;
  const seen = pollCounts.get(key) ?? 0;
  if (seen >= route.poll.polls) return route.file;
  pollCounts.set(key, seen + 1);
  return route.poll.processingFile;
}

// Picks the mock file for this request (advancing poll counters), or null when no route matches.
export function mockFileFor(method, path) {
  const pathOnly = path.split('?')[0];
  const route = ROUTES.find((r) => r.method === method && r.regex.test(pathOnly));
  if (!route) return null;
  if (route.resets) resetPolls(route.resets);
  if (route.poll) return pollFile(route, pathOnly);
  if (route.file === 'get_session') return SESSION_VARIANTS[pathOnly.split('/')[2]] ?? route.file;
  return route.file;
}

// Returns the same { ok, status, body } shape as a real response, or null when no mock exists.
export async function mockResponse(method, path) {
  const file = mockFileFor(method, path);
  if (!file) return null;
  await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS));
  const res = await fetch(`mock/${file}.json`);
  if (!res.ok) {
    console.error(`Mock file mock/${file}.json is missing (HTTP ${res.status}).`);
    return null;
  }
  const body = await res.json();
  return { ok: !body.error, status: body.error ? 404 : 200, body };
}

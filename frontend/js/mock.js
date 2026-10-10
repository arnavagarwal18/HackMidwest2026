// Mock mode (?mock=1): answers requests from frontend/mock/*.json instead of the back end.
const MOCK_ROUTES = [
  ['POST', '/sessions', 'post_sessions'],
  ['GET', '/sessions/:id', 'get_session'],
  ['GET', '/builtins', 'get_builtins'],
  ['POST', '/sessions/:id/score/photo', 'post_score_photo'],
  ['GET', '/sessions/:id/score/status', 'get_score_status'],
  ['POST', '/sessions/:id/score/file', 'post_score_file'],
  ['POST', '/sessions/:id/score/confirm', 'post_score_confirm'],
  ['GET', '/reference-notes', 'get_reference_notes'],
  ['POST', '/sessions/:id/calibration', 'post_calibration'],
  ['POST', '/sessions/:id/calibration/skip', 'post_calibration_skip'],
  ['GET', '/sessions/:id/calibration', 'get_calibration'],
  ['POST', '/sessions/:id/takes', 'post_takes'],
  ['GET', '/sessions/:id/takes/:take/analysis', 'get_analysis'],
  ['GET', '/sessions/:id/takes/:take/media', 'get_media'],
  ['GET', '/sessions/:id/takes/:take/tracks', 'get_tracks'],
  ['GET', '/sessions/:id/takes/:take/feedback', 'get_feedback'],
  ['POST', '/sessions/:id/takes/:take/feedback', 'post_feedback'],
  ['GET', '/sessions/:id/feedback/:fb/trace', 'get_trace'],
  ['POST', '/sessions/:id/camera-check', 'post_camera_check'],
  ['GET', '/sessions/:id/exercises/:ex', 'get_exercise'],
  ['POST', '/sessions/:id/exercises/:ex/reps', 'post_exercise_reps'],
  ['GET', '/sessions/:id/reps/:rep', 'get_rep'],
  ['GET', '/sessions/:id/progress', 'get_progress'],
  ['GET', '/lan-address', 'get_lan_address'],
].map(([method, pattern, file]) => ({
  method,
  file,
  regex: new RegExp(`^${pattern.replace(/:\w+/g, '([^/]+)')}$`),
}));

// Fixed session ids that let the reload behaviour be tried in mock mode.
const SESSION_VARIANTS = {
  sess_gone: 'error_session_not_found',
  sess_unconfirmed: 'get_session_unconfirmed',
};

export function mockFileFor(method, path) {
  const pathOnly = path.split('?')[0];
  const route = MOCK_ROUTES.find((r) => r.method === method && r.regex.test(pathOnly));
  if (!route) return null;
  if (route.file === 'get_session') {
    const id = pathOnly.split('/')[2];
    return SESSION_VARIANTS[id] ?? route.file;
  }
  return route.file;
}

// Returns the same { ok, status, body } shape as a real response, or null when no mock exists.
export async function mockResponse(method, path) {
  const file = mockFileFor(method, path);
  if (!file) return null;
  const res = await fetch(`mock/${file}.json`);
  if (!res.ok) return null;
  const body = await res.json();
  return { ok: !body.error, status: body.error ? 404 : 200, body };
}

export function allMockFiles() {
  return [...MOCK_ROUTES.map((r) => r.file), ...Object.values(SESSION_VARIANTS)];
}

// Page reload: pick the session up again from localStorage and decide which screen to show.
import { getCalibration, getSession } from './api.js';
import { MOCK_MODE } from './config.js';
import { matchRoute } from './router.js';
import { clearSession, loadStoredSessionId, setSession, state } from './state.js';

const SESSION_GONE_NOTICE = 'Your earlier session was not found; starting fresh.';
const MOCK_SESSION_ID = 'sess_mock1'; // the confirmed session frontend/mock/get_session.json describes

// A link to one of the screens that come after choosing a score (#/calibrate, #/take, #/results/...). #/start and #/score are
// where a session begins, so reloading on them still goes wherever the session's progress says.
function isDeepLink(hash) {
  const match = hash ? matchRoute(hash) : null;
  return match !== null && match.screen !== 'start' && match.screen !== 'score';
}

// Returns { hash, notice, error } for the router to start on; the router shows the notice or error.
// #/demo always stays where it is. A confirmed session stays on a deep link; in mock mode a deep link with no stored session starts the mock session, so each screen can
// be opened directly.
export async function resumeSession(currentHash) {
  if (matchRoute(currentHash)?.screen === 'demo') return { hash: currentHash, notice: null, error: null }; // the demo opens its own session
  const sessionId = loadStoredSessionId() ?? (MOCK_MODE && isDeepLink(currentHash) ? MOCK_SESSION_ID : null);
  if (!sessionId) return { hash: '#/start', notice: null, error: null };

  try {
    const session = await getSession(sessionId);
    setSession(session.session_id, session.instrument);
    state.score.status = session.score_status;
    if (session.has_calibration) state.calibration = (await getCalibration(sessionId)).profile;
    const confirmed = session.score_status === 'confirmed';
    return { hash: confirmed ? (isDeepLink(currentHash) ? currentHash : '#/take') : '#/score', notice: null, error: null };
  } catch (err) {
    if (err.code === 'session_not_found') {
      clearSession();
      return { hash: '#/start', notice: SESSION_GONE_NOTICE, error: null };
    }
    // Any other failure: keep the stored session (it may be fine) and stay on the current screen.
    return { hash: currentHash && currentHash !== '#' ? currentHash : '#/start', notice: null, error: err };
  }
}

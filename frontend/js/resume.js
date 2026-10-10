// Page reload: pick the session up again from localStorage and decide which screen to show.
import { api } from './api.js';
import { clearSession, loadStoredSessionId, setSession, state } from './state.js';

const SESSION_GONE_NOTICE = 'Your earlier session was not found; starting fresh.';

// Returns { hash, notice, error } for the router to start on; the router shows the notice or error.
export async function resumeSession(currentHash) {
  const sessionId = loadStoredSessionId();
  if (!sessionId) return { hash: '#/start', notice: null, error: null };

  try {
    const session = await api.get(`/sessions/${encodeURIComponent(sessionId)}`);
    setSession(session.session_id, session.instrument);
    state.score.status = session.score_status;
    return { hash: session.score_status === 'confirmed' ? '#/take' : '#/score', notice: null, error: null };
  } catch (err) {
    if (err.code === 'session_not_found') {
      clearSession();
      return { hash: '#/start', notice: SESSION_GONE_NOTICE, error: null };
    }
    // Any other failure: keep the stored session (it may be fine) and stay on the current screen.
    return { hash: currentHash && currentHash !== '#' ? currentHash : '#/start', notice: null, error: err };
  }
}

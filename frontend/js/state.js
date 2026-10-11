// The one shared state object. Everything except session_id is lost on reload;
// session_id is also kept in localStorage so resume.js can rebuild the rest from the back end.
import { MOCK_MODE } from './config.js';

// Mock mode keeps its own key so a walk-through never overwrites a real session.
const SESSION_KEY = MOCK_MODE ? 'practice_coach_session_id_mock' : 'practice_coach_session_id';
const LAST_PIECE_KEY = MOCK_MODE ? 'practice_coach_last_piece_mock' : 'practice_coach_last_piece';

function freshState() {
  return {
    session_id: null,
    instrument: null,
    score: { status: 'none', bars: null, tempo_bpm: null, time_signature: null },
    calibration: null,
    take_setup: {
      bar_from: null,
      bar_to: null,
      tempo_bpm: null,
      kind: null,
      count_in_beats: null, // null until a take was sent: the take screen then defaults to one bar
      metronome_on: false,
    },
    current_take_id: null,
    last_take_upload: null, // { take_id, file, fields } of the last take sent: kept in memory only, so other bars can be tried
    current_feedback_id: null,
    current_exercise_id: null,
  };
}

export const state = freshState();

export function resetState() {
  Object.assign(state, freshState());
}

function storage(action, fallback) {
  try {
    return action(window.localStorage);
  } catch (err) {
    console.error('localStorage unavailable; the session will not survive a reload.', err);
    return fallback;
  }
}

export function loadStoredSessionId() {
  return storage((s) => s.getItem(SESSION_KEY), null);
}

export function setSession(sessionId, instrument) {
  state.session_id = sessionId;
  state.instrument = instrument ?? state.instrument;
  storage((s) => s.setItem(SESSION_KEY, sessionId));
}

export function clearSession() {
  resetState();
  storage((s) => s.removeItem(SESSION_KEY));
}

// The built-in piece chosen last: a new session starts on it again.
export function loadLastPieceId() {
  return storage((s) => s.getItem(LAST_PIECE_KEY), null);
}

export function rememberPieceId(pieceId) {
  storage((s) => s.setItem(LAST_PIECE_KEY, pieceId));
}

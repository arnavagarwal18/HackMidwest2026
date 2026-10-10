// The one shared state object. Everything except session_id is lost on reload.
const SESSION_KEY = 'practice_coach_session_id';

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
      count_in_beats: 4,
      metronome_on: false,
    },
    current_take_id: null,
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

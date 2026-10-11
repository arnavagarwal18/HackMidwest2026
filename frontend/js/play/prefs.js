// What the Play screen remembers between visits (localStorage): the tempo for the current piece and whether the camera was on.
import { MOCK_MODE } from '../config.js';
import { state } from '../state.js';

// Mock mode keeps its own key, like the session id, so a walk-through never overwrites real choices.
const PREFS_KEY = MOCK_MODE ? 'practice_coach_play_prefs_mock' : 'practice_coach_play_prefs';
const DEFAULT_PREFS = { tempo: null, camera: false }; // tempo: { key, bpm }

export function loadPrefs() {
  try {
    const raw = window.localStorage.getItem(PREFS_KEY);
    return raw ? { ...DEFAULT_PREFS, ...JSON.parse(raw) } : { ...DEFAULT_PREFS };
  } catch (err) {
    console.error('The saved Play choices could not be read; using the defaults.', err);
    return { ...DEFAULT_PREFS };
  }
}

function savePrefs(changes) {
  try {
    window.localStorage.setItem(PREFS_KEY, JSON.stringify({ ...loadPrefs(), ...changes }));
  } catch (err) {
    console.error('The Play choices could not be saved; they will not survive a reload.', err);
  }
}

// A tempo belongs to one piece, which is one session: a new session (another piece) starts from the score's own tempo.
export const rememberTempo = (bpm) => savePrefs({ tempo: { key: state.session_id, bpm } });

export const rememberCamera = (on) => savePrefs({ camera: on });

// The saved take setup (state.take_setup; null fields mean "not chosen") filled in from what was remembered.
export function setupWithPrefs(saved) {
  const prefs = loadPrefs();
  const tempoIsForThisPiece = prefs.tempo && prefs.tempo.key === state.session_id;
  return {
    ...saved,
    tempo_bpm: saved.tempo_bpm ?? (tempoIsForThisPiece ? prefs.tempo.bpm : null),
    kind: saved.kind ?? (prefs.camera ? 'video' : 'mic'),
  };
}

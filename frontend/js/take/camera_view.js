// Which way the learner stands to the camera: facing it, or with their left or right side to it.
// The choice is remembered in localStorage so it survives a reload and a "Record again".
export const VIEWS = [
  { id: 'front', label: 'Front' },
  { id: 'side-left', label: 'Side (left)', hint: 'The camera sees your left side' },
  { id: 'side-right', label: 'Side (right)', hint: 'The camera sees your right side' },
];
export const DEFAULT_VIEW = 'front';
export const SIDE_NOTE = 'Side view: form feedback is limited until the server supports it.';

const VIEW_KEY = 'practice_coach_camera_view';
const isKnownView = (view) => VIEWS.some((candidate) => candidate.id === view);

export const isSideView = (view) => view === 'side-left' || view === 'side-right';

// 'left' or 'right': the side of the body nearest the camera; null when facing the camera.
export const nearSideOf = (view) => (isSideView(view) ? view.slice('side-'.length) : null);

export function loadView() {
  try {
    const stored = window.localStorage.getItem(VIEW_KEY);
    return isKnownView(stored) ? stored : DEFAULT_VIEW;
  } catch (err) {
    console.error('localStorage unavailable; the camera view will not be remembered.', err);
    return DEFAULT_VIEW;
  }
}

export function saveView(view) {
  try {
    window.localStorage.setItem(VIEW_KEY, view);
  } catch (err) {
    console.error('localStorage unavailable; the camera view will not be remembered.', err);
  }
}

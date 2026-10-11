// Sending one take to the server, shared by the Play screen and the demo upload (#/demo).
import { uploadTake } from '../api.js';
import { state } from '../state.js';
import { takeFields } from './setup.js';

// Uploads `file` with the take setup's fields. onProgress({ loaded, total }) is optional. Resolves to the server's answer ({ take_id, ... }).
export function sendTakeFile(file, setup, { kind, source, downbeatS, onProgress }) {
  return uploadTake(state.session_id, file, takeFields(setup, { kind, source, downbeatS }), onProgress);
}

// Remembers an accepted take and returns the results hash to open, so the caller decides whether to navigate.
export function rememberSentTake(answer, setup) {
  state.current_take_id = answer.take_id;
  state.take_setup = { ...setup };
  return `#/results/${encodeURIComponent(answer.take_id)}`;
}

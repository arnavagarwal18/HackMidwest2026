// Reads the persona list once (GET /personas) and keeps it in state.personas. When it cannot be read the answer is null,
// and the screens then leave out the coach style controls and work as they did before personas existed.
import { getPersonas } from '../api.js';
import { state } from '../state.js';
import { orderPersonas } from './model.js';

let pending = null; // the read in flight, so two screens asking at once make one request

async function readPersonas() {
  try {
    const body = await getPersonas();
    if (!Array.isArray(body.personas) || body.personas.length === 0) throw new Error('GET /personas answered without any personas.');
    state.personas = orderPersonas(body.personas, body.default);
    return state.personas;
  } catch (err) {
    console.error('The coach styles could not be read, so the coach style controls are hidden.', err);
    return null;
  }
}

// Resolves to the ordered list ({ id, label, hint, tempo }), or null when there are none to show. Never rejects.
export function loadPersonas() {
  if (state.personas) return Promise.resolve(state.personas);
  pending ??= readPersonas().finally(() => { pending = null; });
  return pending;
}

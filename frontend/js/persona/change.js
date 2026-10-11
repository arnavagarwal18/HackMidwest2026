// Changes the session's coach style on the back end (PATCH /sessions/{id}) and, once it is saved, in state.persona.
// A failure throws (the caller shows it and puts its control back) and leaves state.persona as it was.
import { patchSession } from '../api.js';
import { state } from '../state.js';

export async function savePersona(sessionId, personaId, patch = patchSession) {
  const saved = await patch(sessionId, { persona: personaId });
  state.persona = saved.persona ?? personaId;
  return state.persona;
}

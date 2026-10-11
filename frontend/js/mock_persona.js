// Mock mode behaves like the back end for the coach style: PATCH /sessions/{id} stores it, GET /sessions/{id}, the feedback and the
// chat's instructor turns name it, and a POST .../feedback builds the take's feedback again (a new id).
import { DEFAULT_PERSONA } from './persona/model.js';

let persona = DEFAULT_PERSONA;

// A new session starts on the persona it was asked for (or the default); a PATCH changes it.
export function rememberMockPersona(method, path, requestBody) {
  const isNewSession = method === 'POST' && path === '/sessions';
  if (isNewSession || (method === 'PATCH' && typeof requestBody?.persona === 'string')) persona = requestBody?.persona ?? DEFAULT_PERSONA;
}

// The saved answer with the persona of this mock session on it.
export function withMockPersona(file, path, body) {
  if (file === 'patch_session') return { ...body, session_id: path.split('/')[2], persona };
  if (file.startsWith('get_session') || file.startsWith('get_feedback')) return { ...body, persona };
  if (file.startsWith('post_chat')) return { ...body, instructor_turn: { ...body.instructor_turn, persona } };
  return body;
}

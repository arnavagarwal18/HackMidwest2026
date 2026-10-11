// Session and piece steps shared by the Start screen (automatic) and the Score screen ("Change piece").
import { chooseBuiltinScore, confirmScore, createSession, getBuiltins } from '../api.js';
import { clearSession, loadLastPieceId, loadSessionPieceId, rememberPieceId, rememberSessionPiece, setSession, state } from '../state.js';

export const INSTRUMENT = 'trumpet'; // the app is trumpet only

export async function startFreshSession(instrument = state.instrument ?? INSTRUMENT) {
  const session = await createSession(instrument);
  clearSession();
  setSession(session.session_id, session.instrument);
  return session.session_id;
}

// A confirmed score is locked (409 wrong_state), so a new score needs a new session on the same instrument.
export async function openSession() {
  if (state.session_id && state.score.status !== 'confirmed') return state.session_id;
  return startFreshSession();
}

// The piece a new session starts on: the last built-in the learner chose, else the first one.
export function pickStartPiece(pieces, lastPieceId = loadLastPieceId()) {
  if (!pieces.length) throw new Error('There are no built-in pieces for this instrument yet. Choose a piece from a file or a photo.');
  return pieces.find((piece) => piece.piece_id === lastPieceId) ?? pieces[0];
}

// A built-in piece needs no review: choose it and confirm it in one go.
export async function chooseAndConfirmBuiltin(sessionId, piece) {
  await chooseBuiltinScore(sessionId, piece.piece_id);
  const confirmed = await confirmScore(sessionId);
  state.score = {
    status: 'confirmed',
    title: piece.title,
    bars: confirmed.bars,
    tempo_bpm: confirmed.tempo_bpm,
    time_signature: confirmed.time_signature,
  };
  rememberPieceId(piece.piece_id);
  rememberSessionPiece(sessionId, piece.piece_id);
  return confirmed;
}

// Makes `piece` ({ piece_id, title }) the piece of the current practice. The session already confirmed on that piece is kept, so its tempo and other
// remembered settings stay; anything else gets a session of its own (a confirmed score is locked).
export async function useBuiltinPiece(piece) {
  const { session_id: sessionId } = state;
  if (sessionId && state.score.status === 'confirmed' && loadSessionPieceId(sessionId) === piece.piece_id) return;
  await chooseAndConfirmBuiltin(await openSession(), piece);
}

// Starts on the last-used (else first) built-in piece. Throws on any failure.
export async function startOnDefaultPiece() {
  const piece = pickStartPiece(await getBuiltins(state.instrument ?? INSTRUMENT));
  await useBuiltinPiece(piece);
}

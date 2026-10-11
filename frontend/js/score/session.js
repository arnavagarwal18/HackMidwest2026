// Session and piece steps shared by the Start screen (automatic) and the Score screen ("Change piece").
import { chooseBuiltinScore, confirmScore, createSession, getBuiltins } from '../api.js';
import { clearSession, loadLastPieceId, rememberPieceId, setSession, state } from '../state.js';

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
export async function chooseAndConfirmBuiltin(sessionId, pieceId) {
  await chooseBuiltinScore(sessionId, pieceId);
  const confirmed = await confirmScore(sessionId);
  state.score = {
    status: 'confirmed',
    bars: confirmed.bars,
    tempo_bpm: confirmed.tempo_bpm,
    time_signature: confirmed.time_signature,
  };
  rememberPieceId(pieceId);
  return confirmed;
}

// Creates the session and starts it on the last-used (else first) built-in piece. Throws on any failure.
export async function startOnDefaultPiece() {
  const sessionId = await startFreshSession(INSTRUMENT);
  const piece = pickStartPiece(await getBuiltins(INSTRUMENT));
  await chooseAndConfirmBuiltin(sessionId, piece.piece_id);
}

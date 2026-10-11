// Mock mode keeps the transposition the page last set, so a take can answer differently under different keys.
// take_autokey is can't-tell (low_match) in every key except AUTOKEY_RIGHT_SEMITONES, where it is a normal take;
// take_nokey is can't-tell (low_match) in every key.
export const AUTOKEY_TAKE = 'take_autokey';
export const NOKEY_TAKE = 'take_nokey';
export const AUTOKEY_RIGHT_SEMITONES = -4;

let chosen = null; // { semitones, source } after a POST .../transposition

export function rememberMockTransposition(requestBody) {
  if (Number.isInteger(requestBody?.semitones)) chosen = { semitones: requestBody.semitones, source: 'user' };
}

// The analysis file to answer with: take_autokey is good only under its right key.
export function analysisVariant(takeId, file) {
  if (takeId === AUTOKEY_TAKE && chosen?.semitones === AUTOKEY_RIGHT_SEMITONES) return 'get_analysis';
  return file;
}

// A finished analysis body that shows the key the page set (a back end's rerun leaves the take 'done' and changes its key).
export function withChosenTransposition(body) {
  return chosen && body.status === 'done' ? { ...body, transposition: chosen } : body;
}

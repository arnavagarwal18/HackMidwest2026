// Mock mode behaves like the back end after POST .../transposition: the analysis shows the key the page set (source 'user'),
// and the take's feedback is rebuilt, so it comes back with a new id.
let chosen = null; // { semitones, source } after a POST .../transposition
let rebuilds = 0;

export function rememberMockTransposition(requestBody) {
  if (!Number.isInteger(requestBody?.semitones)) return;
  chosen = { semitones: requestBody.semitones, source: 'user' };
  rebuilds += 1;
}

// A finished analysis body that shows the key the page set (a back end's rerun leaves the take 'done' and changes its key).
export function withChosenTransposition(body) {
  return chosen && body.status === 'done' ? { ...body, transposition: chosen } : body;
}

// A feedback body after a key change carries the id of the rebuilt feedback.
export function withRebuiltFeedback(file, body) {
  return rebuilds && file.startsWith('get_feedback') ? { ...body, id: `${body.id}_rebuilt_${rebuilds}` } : body;
}

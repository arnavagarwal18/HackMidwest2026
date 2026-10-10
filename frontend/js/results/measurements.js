// Lookup from a measurement id (note 'n:t1:12:3', extra 'x:t1:2', bar 'b:t1:12', problem 'p:t1:1',
// form flag 'f:t1:1') to where it is in the take: { bar, time_s, lead_s }. Sentences and chips use it to jump.
export const SENTENCE_LEAD_S = 1; // a jump starts this long before the problem so the learner hears the run-up
const FLAG_LEAD_S = 0; // a form flag jumps to its peak

export function buildMeasurementIndex(analysis) {
  const index = new Map();
  const firstTimeInBar = new Map();
  const put = (id, bar, time_s, lead_s = SENTENCE_LEAD_S) => index.set(id, { bar: bar ?? null, time_s: time_s ?? null, lead_s });

  (analysis.notes ?? []).forEach((note) => {
    put(note.id, note.bar, note.expected_onset_s);
    const known = firstTimeInBar.get(note.bar);
    if (known === undefined || note.expected_onset_s < known) firstTimeInBar.set(note.bar, note.expected_onset_s);
  });
  (analysis.extras ?? []).forEach((extra) => put(extra.id, extra.bar, extra.onset_s));
  (analysis.bars ?? []).forEach((bar) => put(bar.id, bar.bar, firstTimeInBar.get(bar.bar)));
  (analysis.problems ?? []).forEach((problem) => put(problem.id, problem.bars?.[0], problem.first_time_s));
  (analysis.form ?? []).forEach((flag) => put(flag.id, flag.bars?.[0], flag.peak_s, FLAG_LEAD_S));
  return { places: index, firstTimeInBar };
}

// A sentence's jump {bar, time_s} (either may be null) as a place to go to, or null when it has neither.
export function resolveJump(jump, index) {
  const bar = jump?.bar ?? null;
  const time_s = jump?.time_s ?? (bar === null ? null : index.firstTimeInBar.get(bar) ?? null);
  if (bar === null && time_s === null) return null;
  return { bar, time_s, lead_s: SENTENCE_LEAD_S };
}

// A cited measurement id as a place to go to, or null when the id isn't in this take's results.
export function resolveId(id, index) {
  return index.places.get(id) ?? null;
}

export function chipLabel(id, place) {
  if (id.startsWith('f:') && place.time_s !== null) return `${place.time_s.toFixed(1)} s`;
  if (place.bar !== null) return `bar ${place.bar}`;
  if (place.time_s !== null) return `${place.time_s.toFixed(1)} s`;
  return id;
}

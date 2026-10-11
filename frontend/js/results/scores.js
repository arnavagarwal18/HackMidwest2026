// The two scores shown on top of the results, worked out from the analysis the back end already sends.
// Pitch: the share of the expected notes played right (analysis.bars). Rhythm: the share of timed notes within ON_TIME_MS
// of the beat (analysis.notes[].timing_ms), where the back end calls a note late or early beyond LATE_EARLY_MS (diagnosis/config.py).
export const ON_TIME_MS = 80;
export const STRONG_PITCH = 0.85;
export const STRONG_RHYTHM = 0.75;

const sum = (bars, field) => bars.reduce((total, bar) => total + (bar[field] ?? 0), 0);

// { right, expected, share } or null when the analysis has no expected notes.
export function pitchScore(analysis) {
  const bars = analysis.bars ?? [];
  const expected = sum(bars, 'expected');
  if (!expected) return null;
  const right = sum(bars, 'ok');
  return { right, expected, share: right / expected };
}

// { onTime, timed, share } or null when no note has a timing.
export function rhythmScore(analysis) {
  const timings = (analysis.notes ?? []).map((note) => note.timing_ms).filter((ms) => typeof ms === 'number');
  if (!timings.length) return null;
  const onTime = timings.filter((ms) => Math.abs(ms) <= ON_TIME_MS).length;
  return { onTime, timed: timings.length, share: onTime / timings.length };
}

// { steady, measured, share } for the bars the back end gave a drift to, or null when none has one. Steady bars kept the tempo.
export function tempoScore(analysis) {
  const drifts = (analysis.bars ?? []).map((bar) => bar.drift).filter(Boolean);
  if (!drifts.length) return null;
  const steady = drifts.filter((drift) => drift === 'steady').length;
  return { steady, measured: drifts.length, share: steady / drifts.length };
}

export const percent = (share) => `${Math.round(share * 100)}%`;

// What to check after an otherwise solid take: the form flags when only form flags are there, else the flagged bars.
function checkNote(counts) {
  if (!counts?.total) return '';
  const formOnly = counts.form === counts.total;
  return formOnly ? ' - check the form flags below.' : ' - check the flagged bars below.';
}

// "Solid take: ..." with its closing full stop moved after the check note when form, extra-note or timing flags still list bars.
function solid(text, counts) {
  const note = checkNote(counts);
  return note ? `${text}${note}` : `${text}.`;
}

// One sentence: what to take from the take, before any numbers. `counts` (problemBarCounts) qualifies a solid take that still has bars to work on.
export function headline(pitch, rhythm, counts = null) {
  if (!pitch) return null;
  const notesStrong = pitch.share >= STRONG_PITCH;
  if (!rhythm) return notesStrong ? solid('Solid take: the notes held up', counts) : 'Some notes were off - slow down and check the bars below.';
  const timingStrong = rhythm.share >= STRONG_RHYTHM;
  if (notesStrong && timingStrong) return solid('Solid take: the notes and the timing both held up', counts);
  if (notesStrong) return 'Right notes, but the timing drifted - lean on the beat.';
  if (timingStrong) return 'Steady timing, but some notes were off - slow down and check the bars below.';
  return 'A rough one - slow it down and take the bars below one at a time.';
}

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

export const percent = (share) => `${Math.round(share * 100)}%`;

// One sentence: what to take from the take, before any numbers.
export function headline(pitch, rhythm) {
  if (!pitch) return null;
  const notesStrong = pitch.share >= STRONG_PITCH;
  if (!rhythm) return notesStrong ? 'Solid take: the notes held up.' : 'Some notes were off - slow down and check the bars below.';
  const timingStrong = rhythm.share >= STRONG_RHYTHM;
  if (notesStrong && timingStrong) return 'Solid take: the notes and the timing both held up.';
  if (notesStrong) return 'Right notes, but the timing drifted - lean on the beat.';
  if (timingStrong) return 'Steady timing, but some notes were off - slow down and check the bars below.';
  return 'A rough one - slow it down and take the bars below one at a time.';
}

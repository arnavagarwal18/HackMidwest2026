// What one bar of the take sounded like, as a tone plus glyphs and words, so the bar strip never relies on colour alone.
// Pitch comes from the wrong notes in the bar (cents_off > 0 is sharp); timing from the bar's mean timing,
// called late or early beyond LATE_EARLY_MS like the back end does (diagnosis/config.py).
export const LATE_EARLY_MS = 80;

export const GLYPHS = { ok: '✓', sharp: '↑', flat: '↓', late: '→', early: '←', unclear: '!' };
export const WORDS = { ok: 'clean', sharp: 'sharp', flat: 'flat', late: 'late', early: 'early', unclear: 'needs work' };

function pitchDirection(bar, notes) {
  const cents = notes
    .filter((note) => note.bar === bar.bar && note.status === 'wrong' && typeof note.cents_off === 'number')
    .reduce((total, note) => total + note.cents_off, 0);
  if (cents > 0) return 'sharp';
  return cents < 0 ? 'flat' : null;
}

function timingDirection(bar) {
  const ms = bar.mean_timing_ms;
  if (typeof ms !== 'number' || Math.abs(ms) <= LATE_EARLY_MS) return null;
  return ms > 0 ? 'late' : 'early';
}

// { tone, kinds, glyph, words }: kinds are the pitch and timing results found (or 'unclear' / 'ok'); tone is the one that tints the cell
// (pitch first). A flagged bar with no direction (a missed note, say) is 'unclear'; a bar that is neither flagged nor off is 'ok'.
export function barVerdict(bar, notes, flagged) {
  const kinds = [pitchDirection(bar, notes), timingDirection(bar)].filter(Boolean);
  if (!kinds.length) kinds.push(flagged ? 'unclear' : 'ok');
  return {
    tone: kinds[0],
    kinds,
    glyph: kinds.map((kind) => GLYPHS[kind]).join(' '),
    words: kinds.map((kind) => WORDS[kind]).join(', '),
  };
}

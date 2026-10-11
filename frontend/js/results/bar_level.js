// One plain word for each bar in the Bar by bar grid (Good, Okay or Needs work), from the bar's verdict (bar_verdict.js) and its counts.
// Good: nothing off. Needs work: under three quarters of the notes right, or pitch and timing both off. Okay: any other slip.
export const LEVELS = ['good', 'okay', 'needs-work']; // least to most work
export const LEVEL_WORDS = { good: 'Good', okay: 'Okay', 'needs-work': 'Needs work' };
export const LEVEL_MEANINGS = {
  good: 'right notes, on the beat',
  okay: 'a small slip in notes, timing or form',
  'needs-work': 'several notes off, or notes and timing both off',
};
export const NEEDS_WORK_RIGHT_SHARE = 0.75;

const rightShare = (bar) => (bar.expected ? bar.ok / bar.expected : 1);

export function barLevel(bar, verdict) {
  if (verdict.tone === 'ok') return 'good';
  return rightShare(bar) < NEEDS_WORK_RIGHT_SHARE || verdict.kinds.length > 1 ? 'needs-work' : 'okay';
}

// The index of the bar to show first: the one with the most work, and on a tie the one ranked worse in `problemOrder`
// (bar numbers, worst problem first; see problemBars), else the earlier bar.
export function worstBarIndex(bars, levels, problemOrder) {
  const rank = (i) => {
    const at = problemOrder.indexOf(bars[i].bar);
    return at < 0 ? Infinity : at;
  };
  const severity = (i) => LEVELS.indexOf(levels[i]);
  return bars.reduce((worst, _bar, i) => (severity(i) > severity(worst) || (severity(i) === severity(worst) && rank(i) < rank(worst)) ? i : worst), 0);
}

// What the results say first: one word and one number for the whole take, and which of Pitch, Rhythm and Tempo was weakest.
import { pitchScore, rhythmScore, tempoScore } from './scores.js';

export const SCORE_NAMES = ['Pitch', 'Rhythm', 'Tempo'];
const VERDICT_WORDS = [[0.85, 'Great take'], [0.7, 'Good take'], [0.5, 'Getting there'], [0, 'Keep at it']];
export const NO_SCORE_WORD = 'Take checked';
export const NO_SCORE_SUGGESTION = 'There were no notes to score in this take.';
export const STEADY_SUGGESTION = 'Nicely done. Play it once more to make it stick.';
const SUGGESTIONS = {
  Pitch: 'Slow down and take the wrong notes one bar at a time.',
  Rhythm: 'Lean on the beat: count out loud while you play.',
  Tempo: 'Keep the pace steady from the first bar to the last.',
};
const NOTHING_TO_FIX_SHARE = 0.9;

// { Pitch, Rhythm, Tempo } as score objects ({ share, ... }), each null when the take has nothing to measure it by.
export function scoresOf(analysis) {
  return { Pitch: pitchScore(analysis), Rhythm: rhythmScore(analysis), Tempo: tempoScore(analysis) };
}

// The name of the lowest score (the first one on a tie); null unless at least two scores can be compared.
export function weakestName(scores) {
  const present = SCORE_NAMES.filter((name) => scores[name]);
  if (present.length < 2) return null;
  return present.reduce((weakest, name) => (scores[name].share < scores[weakest].share ? name : weakest));
}

// The whole take as one share: the mean of the scores there are; null with none.
export function overallShare(scores) {
  const shares = SCORE_NAMES.filter((name) => scores[name]).map((name) => scores[name].share);
  return shares.length ? shares.reduce((total, share) => total + share, 0) / shares.length : null;
}

export function verdictWord(share) {
  return share === null ? NO_SCORE_WORD : VERDICT_WORDS.find(([least]) => share >= least)[1];
}

// One sentence on what to do next: about the weakest score (the only one there is, if just one), or praise when that one is strong.
export function suggestionFor(scores) {
  const focus = weakestName(scores) ?? SCORE_NAMES.find((name) => scores[name]);
  if (!focus) return NO_SCORE_SUGGESTION;
  return scores[focus].share >= NOTHING_TO_FIX_SHARE ? STEADY_SUGGESTION : SUGGESTIONS[focus];
}

// What kind of problem put each bar on the "Bars to work on" list: wrong or extra notes, timing, or form (posture).
// Each listed bar counts once, under its most basic problem (notes before timing before form), so the kinds add up to the list.
import { hasMistakes } from './problem_reasons.js';
import { problemBars } from './bars.js';

const GROUP_BY_KIND = { notes: 'note', late: 'timing', early: 'timing', rushing: 'timing', dragging: 'timing', form: 'form' };
const GROUPS = ['note', 'timing', 'form', 'other'];
const DETAIL_LABELS = { note: (n) => (n === 1 ? 'note' : 'notes'), timing: () => 'timing', form: () => 'form', other: () => 'other' };

function covers(problem, barNumber) {
  const [from, to = from] = problem.bars ?? [];
  return barNumber >= from && barNumber <= to;
}

function barGroup(analysis, bar) {
  if (hasMistakes(bar)) return 'note';
  const groups = (analysis.problems ?? []).filter((problem) => covers(problem, bar.bar)).map((problem) => GROUP_BY_KIND[problem.kind] ?? 'other');
  return GROUPS.find((group) => groups.includes(group)) ?? 'other';
}

// { note, timing, form, other, total }: how many listed bars each kind of problem accounts for.
export function problemBarCounts(analysis) {
  const counts = { note: 0, timing: 0, form: 0, other: 0, total: 0 };
  problemBars(analysis).forEach((bar) => {
    counts[barGroup(analysis, bar)] += 1;
    counts.total += 1;
  });
  return counts;
}

// "1 note, 4 form": the kinds that have bars, in the order above; '' when there are none.
export function countsDetail(counts) {
  return GROUPS.filter((group) => counts[group] > 0).map((group) => `${counts[group]} ${DETAIL_LABELS[group](counts[group])}`).join(', ');
}

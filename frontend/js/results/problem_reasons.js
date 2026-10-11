// Why a bar is on the "Bars to work on" list, in words, so a row never reads as clean while still being counted under "Bars to work on".
// A reason comes from each analysis.problems entry that covers the bar (notes, late, early, rushing, dragging, form).

const REASON_BY_KIND = {
  late: (numbers) => `Playing late${msText(numbers)}`,
  early: (numbers) => `Playing early${msText(numbers)}`,
  rushing: () => 'Rushing the tempo',
  dragging: () => 'Dragging the tempo',
  form: (numbers) => `Posture: ${numbers.label ?? 'form flag'}`,
  notes: () => 'Note problems',
};

export function hasMistakes(bar) {
  return bar.wrong + bar.missed + bar.extra + bar.uncertain > 0;
}

function msText(numbers) {
  return typeof numbers.mean_ms === 'number' ? ` (${Math.round(numbers.mean_ms)} ms)` : '';
}

function reasonText(problem) {
  const describe = REASON_BY_KIND[problem.kind];
  if (!describe) {
    console.warn(`A problem of kind "${problem.kind}" has no description; showing its kind.`);
    return String(problem.kind ?? 'Problem');
  }
  return describe(problem.numbers ?? {});
}

function covers(problem, barNumber) {
  const [from, to = from] = problem.bars ?? [];
  return barNumber >= from && barNumber <= to;
}

// The distinct reasons for `bar`, worst problem first. The notes reason is left out when the bar's own counts already show note mistakes.
export function reasonsForBar(analysis, bar) {
  const noteMistakes = hasMistakes(bar);
  const covering = (analysis.problems ?? [])
    .filter((problem) => covers(problem, bar.bar) && !(problem.kind === 'notes' && noteMistakes))
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  return [...new Set(covering.map(reasonText))];
}

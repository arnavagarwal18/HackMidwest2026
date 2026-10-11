import { getProgress, isNotFound } from '../api.js';
import { state } from '../state.js';
import { badge, emptyState, pageHeader, skeleton } from '../ui/components.js';
import { loadStylesheet } from '../ui/styles.js';
import { element } from './placeholder.js';

// Progress screen (#/progress): the first take against the latest one, then each exercise's standing.

const SOURCE_LABELS = { take: 'Take', rep: 'Practice rep' };

const percent = (rate) => (rate == null ? 'none yet' : `${Math.round(rate * 100)}%`); // the server sends null when no rate could be worked out
const bpm = (value) => (value == null ? 'none yet' : `${value} bpm`);

// One row of the comparison table: how to show that metric for a snapshot.
const METRICS = [
  { label: 'Where', value: (s) => `${SOURCE_LABELS[s.source] ?? s.source}, bars ${s.bar_from} to ${s.bar_to}` },
  { label: 'Errors', value: (s) => String(s.errors) },
  { label: 'Error rate', value: (s) => percent(s.error_rate) },
  { label: 'Played tempo', value: (s) => bpm(s.played_bpm) },
  { label: 'Clean tempo', value: (s) => bpm(s.clean_bpm) },
  { label: 'Form flags', value: (s) => (s.form_checked ? String(s.form_flags) : 'Not checked (no camera)') },
];

function snapshotCell(snapshot, metric) {
  const cell = element('td', snapshot ? metric.value(snapshot) : 'No data yet');
  if (!snapshot) cell.className = 'muted';
  return cell;
}

function comparisonTable({ before, after }) {
  const table = element('table', '', 'progress-table');
  const head = table.createTHead().insertRow();
  head.append(element('th', ''), element('th', 'Before'), element('th', 'After'));
  const body = table.createTBody();
  for (const metric of METRICS) {
    const row = body.insertRow();
    const label = element('th', metric.label);
    label.scope = 'row';
    row.append(label, snapshotCell(before, metric), snapshotCell(after, metric));
  }
  return table;
}

// How far the best passed tempo has come from the start tempo toward the target, 0 to 1.
export function tempoShare({ start_bpm: start, target_bpm: target, best_passed_bpm: best }) {
  if (best == null || target <= start) return best == null || best < target ? 0 : 1;
  return Math.min(1, Math.max(0, (best - start) / (target - start)));
}

// A bar from the start tempo to the target, filled up to the best passed tempo. The words under it say the same.
function tempoMeter(exercise) {
  const meter = element('div', '', 'meter tempo-meter', {
    role: 'progressbar',
    'aria-label': `Tempo reached in ${exercise.title}`,
    'aria-valuemin': String(exercise.start_bpm),
    'aria-valuemax': String(exercise.target_bpm),
    'aria-valuenow': String(exercise.best_passed_bpm ?? exercise.start_bpm),
  });
  meter.append(element('i', '', '', { style: `width: ${Math.round(tempoShare(exercise) * 100)}%` }));
  const scale = element('p', '', 'tempo-scale muted');
  scale.append(element('span', `${exercise.start_bpm} bpm`), element('span', `${exercise.target_bpm} bpm`));
  const box = element('div', '', 'tempo');
  box.append(meter, scale);
  return box;
}

function exerciseItem(exercise) {
  const item = element('li', '', 'exercise-item card');
  const link = element('a', exercise.title);
  link.href = `#/exercise/${encodeURIComponent(exercise.id)}`;
  const heading = element('h3');
  heading.append(link);
  const header = element('div', '', 'card-header');
  header.append(heading, exercise.complete ? badge('Complete', 'ok') : badge('In progress', 'warn'));
  const best = exercise.best_passed_bpm == null ? 'No pass yet' : `Best passed: ${exercise.best_passed_bpm} bpm`;
  const detail = `${best} (from ${exercise.start_bpm} toward ${exercise.target_bpm} bpm). `
    + `${exercise.passes} of ${exercise.reps} reps passed.`;
  const body = element('div', '', 'card-body');
  body.append(tempoMeter(exercise), element('p', detail, 'muted'));
  item.append(header, body);
  return item;
}

// Pure view of one progress response; exported so it can be tried with any saved response.
export function renderProgress(root, progress) {
  root.replaceChildren(pageHeader({ title: 'Progress', subtitle: 'Your first take against your latest one, and how far each exercise has come.' }));
  const hasSnapshots = progress.before || progress.after;
  if (!hasSnapshots && !progress.exercises.length) {
    root.append(emptyState('Nothing to compare yet', 'Record a take, then practice an exercise, and your before and after will show up here.'));
    return;
  }
  root.append(element('h2', 'Before and after'));
  if (hasSnapshots) root.append(comparisonTable(progress));
  else root.append(element('p', 'No take has been analysed yet.', 'muted'));
  root.append(element('h2', 'Exercises'));
  if (!progress.exercises.length) {
    root.append(element('p', 'No exercises yet. Ask for feedback on a take to get some.', 'muted'));
    return;
  }
  const list = element('ul', '', 'exercise-list');
  list.append(...progress.exercises.map(exerciseItem));
  root.append(list);
}

export const NO_PROGRESS_TEXT = 'No progress yet: record a take first.';

export async function render(root, _params, isCurrent = () => true) {
  loadStylesheet('css/progress.css');
  root.replaceChildren(pageHeader({ title: 'Progress' }), skeleton(4));
  let progress;
  try {
    progress = await getProgress(state.session_id ?? 'no-session');
  } catch (err) {
    if (isCurrent()) root.replaceChildren(pageHeader({ title: 'Progress' })); // the placeholders must not stay up after a failure
    if (!isNotFound(err)) throw err; // other errors reach the banner
    if (!isCurrent()) return;
    console.warn(`No progress for this session (${err.code}).`);
    root.replaceChildren(pageHeader({ title: 'Progress' }), emptyState(NO_PROGRESS_TEXT));
    return;
  }
  if (!isCurrent()) return; // the learner already moved to another screen
  renderProgress(root, progress);
}

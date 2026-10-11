import { getProgress, isNotFound } from '../api.js';
import { state } from '../state.js';
import { emptyState, pageHeader, skeleton } from '../ui/components.js';
import { loadStylesheet } from '../ui/styles.js';
import { element } from '../dom.js';

// Progress screen (#/progress): each exercise's standing in one plain list; the first take against the latest one sits behind "Before and after".

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

// One quiet status line: how far the best passed tempo has come, or Done.
export function statusText({ target_bpm: target, best_passed_bpm: best, complete }) {
  if (complete) return 'Done';
  return best == null ? 'Not started yet' : `${best} of ${target} BPM`;
}

function exerciseItem(exercise) {
  const item = element('li', '', 'exercise-item');
  const link = element('a', '', 'exercise-link', { href: `#/exercise/${encodeURIComponent(exercise.id)}` });
  link.append(element('span', exercise.title, 'exercise-title'), element('span', statusText(exercise), 'exercise-status'));
  item.append(link);
  return item;
}

// Pure view of one progress response; exported so it can be tried with any saved response.
export function renderProgress(root, progress) {
  root.replaceChildren(pageHeader({ title: 'Progress' }));
  const hasSnapshots = progress.before || progress.after;
  if (!hasSnapshots && !progress.exercises.length) {
    root.append(emptyState('Nothing to compare yet', 'Record a take, then practice an exercise, and your before and after will show up here.'));
    return;
  }
  if (progress.exercises.length) {
    const list = element('ul', '', 'exercise-list');
    list.append(...progress.exercises.map(exerciseItem));
    root.append(list);
  } else {
    root.append(element('p', 'No exercises yet. Ask for feedback on a take to get some.', 'muted'));
  }
  if (!hasSnapshots) return;
  const comparison = element('details', '', 'disclosure progress-compare');
  comparison.append(element('summary', 'Before and after'), comparisonTable(progress));
  root.append(comparison);
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

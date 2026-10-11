// The parts of the trainer screen that show where the learner stands: page header, tempo card and rep history.
import { element } from '../dom.js';
import { emptyState, badge, pageHeader, stat } from '../ui/components.js';
import { barsText, ladderView, passMarkText, streakDots, streakLabel, tempoProgressPercent } from './model.js';

const capitalized = (text) => text.charAt(0).toUpperCase() + text.slice(1);

export function renderHeader(exercise) {
  return pageHeader({ title: exercise.title, subtitle: `${capitalized(barsText(exercise))}, from ${exercise.start_bpm} to ${exercise.target_bpm} BPM` });
}

function renderStreakDots(exercise, xstate) {
  const label = streakLabel(xstate.streak, exercise.reps_to_pass);
  const dots = element('ul', '', 'streak-dots', { 'aria-label': label });
  streakDots(xstate.streak, exercise.reps_to_pass).forEach((filled) => {
    dots.append(element('li', filled ? '●' : '○', filled ? 'dot filled' : 'dot'));
  });
  return dots;
}

function renderLadder(exercise, xstate) {
  const ladder = element('ol', '', 'ladder', { 'aria-label': 'Tempo ladder, from start to target' });
  ladderView(exercise, xstate).forEach(({ bpm, status }) => {
    ladder.append(element('li', String(bpm), `step ${status}`));
  });
  return ladder;
}

// A thin bar from the start tempo to the target; the stats and the ladder say the same in words.
function renderProgress(exercise, xstate) {
  const bar = element('div', '', 'tempo-progress', { 'aria-hidden': 'true' });
  bar.append(element('span', '', 'tempo-progress-fill', { style: `width: ${tempoProgressPercent(exercise, xstate)}%` }));
  return bar;
}

function renderStats(exercise, xstate) {
  const row = element('div', '', 'trainer-stats');
  row.append(
    stat(xstate.current_bpm, 'BPM now'),
    stat(exercise.target_bpm, 'Target BPM'),
    stat(`${xstate.streak} / ${exercise.reps_to_pass}`, 'Passes in a row'),
  );
  return row;
}

// The tempo card: the stats row, the progress bar, the streak dots, the ladder and the pass mark.
export function renderTempoCard(exercise, xstate) {
  const card = element('section', '', 'card exercise-card', { 'aria-label': 'Tempo' });
  const body = element('div', '', 'card-body');
  const dotsRow = element('div', '', 'streak');
  dotsRow.append(renderStreakDots(exercise, xstate), element('span', `${Math.max(0, exercise.reps_to_pass - xstate.streak)} to go`, 'muted streak-label'));
  body.append(
    element('p', exercise.text, 'exercise-text'),
    renderStats(exercise, xstate),
    renderProgress(exercise, xstate),
    element('p', `Current tempo: ${xstate.current_bpm} BPM`, 'current-tempo'),
    renderLadder(exercise, xstate),
    dotsRow,
  );
  const footer = element('div', '', 'card-footer');
  footer.append(element('p', `To pass a rep: ${passMarkText(exercise.pass_mark)}.`, 'pass-mark'));
  card.append(body, footer);
  return card;
}

// The reps scored since the screen opened, newest first.
export function renderHistory(history) {
  const card = element('section', '', 'card rep-history-card', { 'aria-label': 'Rep history' });
  const header = element('div', '', 'card-header');
  header.append(element('h2', 'Reps this visit'));
  card.append(header);
  const body = element('div', '', 'card-body');
  if (history.length === 0) {
    body.append(emptyState('No reps yet', 'Record a rep and its result shows up here.'));
  } else {
    const list = element('ol', '', 'rep-history');
    history.forEach(({ tempo_bpm: bpm, passed }) => {
      const item = element('li', '', 'rep-history-item');
      item.append(element('span', `${bpm} BPM`, 'rep-history-tempo'), passed ? badge('Pass', 'ok') : badge('Fail', 'error'));
      list.append(item);
    });
    body.append(list);
  }
  card.append(body);
  return card;
}

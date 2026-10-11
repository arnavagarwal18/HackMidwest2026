// The parts of the trainer screen that show where the learner stands: the title, the tempo with its streak, and the rep history.
import { element } from '../dom.js';
import { pageHeader } from '../ui/components.js';
import { streakDots, streakLabel } from './model.js';

// The title, with the exercise's own instruction as the quiet line under it.
export function renderHeader(exercise) {
  return pageHeader({ title: exercise.title, subtitle: exercise.text });
}

function renderStreakDots(exercise, xstate) {
  const dots = element('ul', '', 'streak-dots', { 'aria-label': streakLabel(xstate.streak, exercise.reps_to_pass) });
  streakDots(xstate.streak, exercise.reps_to_pass).forEach((filled) => {
    dots.append(element('li', filled ? '●' : '○', filled ? 'dot filled' : 'dot'));
  });
  return dots;
}

// First glance: the current tempo as one big number, the target in a quiet line, and the streak dots with what is left.
export function renderTempo(exercise, xstate) {
  const section = element('section', '', 'tempo', { 'aria-label': 'Tempo' });
  const now = element('p', '', 'current-tempo');
  now.append(element('span', String(xstate.current_bpm), 'tempo-value'), element('span', ' BPM now', 'visually-hidden'));
  section.append(now, element('p', `of ${exercise.target_bpm} BPM`, 'muted tempo-target'));
  if (xstate.complete) return section; // the streak is spent: the Done line says the rest
  const streak = element('div', '', 'streak');
  streak.append(renderStreakDots(exercise, xstate), element('span', `${Math.max(0, exercise.reps_to_pass - xstate.streak)} to go`, 'muted streak-label'));
  section.append(streak);
  return section;
}

// The reps scored since the screen opened, newest first, behind a "History" disclosure; nothing shows before the first rep.
export function renderHistory(history) {
  if (history.length === 0) return null;
  const disclosure = element('details', '', 'disclosure rep-history-card');
  const list = element('ol', '', 'rep-history');
  history.forEach(({ tempo_bpm: bpm, passed }) => {
    list.append(element('li', `${bpm} BPM · ${passed ? 'Pass' : 'Not yet'}`, 'rep-history-item'));
  });
  disclosure.append(element('summary', 'History'), list);
  return disclosure;
}

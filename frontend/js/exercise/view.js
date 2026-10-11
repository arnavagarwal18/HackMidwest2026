// Draws the loop trainer from a plain model; every call rebuilds the screen, so it never holds state of its own.
// model: { exercise, xstate, phase, rep, slow, mediaError }
// handlers: { onPrimary, onRecordAgain, onCheckAgain, onSendAgain, onFullTake, onTryAgain, onUpload, onFile }
import { button, element } from '../dom.js';
import { renderMediaError } from '../media_error.js';
import {
  STILL_WORKING_TEXT, TOO_LONG_TEXT, barsText, firstRepText, ladderView, nextRepText, notCountedMessages,
  passMarkText, streakDots, streakLabel, tempoChangeText, tempoProgressPercent,
} from './model.js';

// A read-only dial: the current tempo, and how far along the way to the target it is. The text of the card says the same in words.
function renderTempoDial(exercise, xstate) {
  const dial = element('div', '', 'tempo-dial', { 'aria-hidden': 'true', style: `--dial-progress: ${tempoProgressPercent(exercise, xstate)}%` });
  const face = element('div');
  face.append(
    element('span', String(xstate.current_bpm), 'bpm'),
    element('span', 'BPM now', 'unit'),
    element('span', `of ${exercise.target_bpm}`, 'dial-target'),
  );
  dial.append(face);
  return dial;
}

function renderCard(exercise, xstate) {
  const card = element('section', '', 'exercise-card');
  card.append(
    element('h1', exercise.title),
    element('p', exercise.text),
    element('p', `${barsText(exercise)}, from ${exercise.start_bpm} to ${exercise.target_bpm} BPM`, 'muted'),
    element('p', `To pass a rep: ${passMarkText(exercise.pass_mark)}.`, 'pass-mark'),
    renderTempoDial(exercise, xstate),
  );
  return card;
}

function renderStreak(exercise, xstate) {
  const box = element('div', '', 'streak');
  box.append(element('p', `Current tempo: ${xstate.current_bpm} BPM`, 'current-tempo'));
  const dots = element('ul', '', 'streak-dots', { 'aria-label': streakLabel(xstate.streak, exercise.reps_to_pass) });
  streakDots(xstate.streak, exercise.reps_to_pass).forEach((filled) => {
    dots.append(element('li', filled ? '●' : '○', filled ? 'dot filled' : 'dot'));
  });
  box.append(dots, element('p', streakLabel(xstate.streak, exercise.reps_to_pass), 'muted streak-label'));
  return box;
}

function renderLadder(exercise, xstate) {
  const ladder = element('ol', '', 'ladder', { 'aria-label': 'Tempo ladder, from start to target' });
  ladderView(exercise, xstate).forEach(({ bpm, status }) => {
    ladder.append(element('li', String(bpm), `step ${status}`));
  });
  return ladder;
}

const statusPanel = (className = '') => element('div', '', `trainer-status ${className}`.trim(), { role: 'status' });

function actions(...buttons) {
  const row = element('p', '', 'actions');
  row.append(...buttons);
  return row;
}

function renderVerdict(model, handlers) {
  const { rep } = model;
  const panel = statusPanel(rep.passed ? 'result-pass' : 'result-fail');
  panel.append(element('p', rep.passed ? 'PASS' : 'FAIL', `verdict ${rep.passed ? 'pass' : 'fail'}`));
  if (rep.reasons?.length) {
    const reasons = element('ul', '', 'reasons');
    rep.reasons.forEach((reason) => reasons.append(element('li', reason)));
    panel.append(reasons);
  }
  panel.append(element('p', tempoChangeText(rep.tempo_bpm, rep), 'tempo-change'));
  if (rep.exercise_complete) return panel; // the Done panel is added by the caller
  panel.append(element('p', nextRepText(rep.next_bpm), 'next-rep'), actions(button('Record rep', handlers.onPrimary, 'primary')));
  return panel;
}

function renderDone(exercise, handlers) {
  const panel = statusPanel('done');
  panel.append(
    element('p', 'Done', 'verdict done'),
    element('p', `You passed ${exercise.target_bpm} BPM.`),
    actions(button('Record a full take', handlers.onFullTake, 'primary')),
  );
  return panel;
}

function renderUpload(handlers) {
  const panel = statusPanel('upload');
  const input = element('input', '', '', { type: 'file', accept: 'audio/*,video/*', 'aria-label': 'Recording file' });
  input.addEventListener('change', () => handlers.onFile(input.files?.[0]));
  panel.append(element('p', 'Choose a recording of your rep (at most 60 seconds).'), input);
  return panel;
}

// Everything the panel under the ladder can show, by phase.
function renderPanel(model, handlers) {
  const { exercise, xstate, phase, rep } = model;
  const text = (message, className = 'stage') => { const p = statusPanel(); p.append(element('p', message, className)); return p; };
  switch (phase) {
    case 'loading': return text('Loading the exercise...');
    case 'ready': {
      const panel = text(firstRepText(xstate.current_bpm), 'next-rep');
      panel.append(actions(button('Record rep', handlers.onPrimary, 'primary')));
      return panel;
    }
    case 'recording': {
      const panel = text('Recording: the count-in plays, then play the rep. Press space to stop.', 'stage recording');
      panel.append(actions(button('Stop', handlers.onPrimary, 'primary')));
      return panel;
    }
    case 'sending': return text('Sending your rep...');
    case 'scoring': {
      const panel = text('Checking your rep...');
      if (model.slow) panel.append(element('p', STILL_WORKING_TEXT, 'muted slow-note'));
      return panel;
    }
    case 'result': return rep.exercise_complete ? renderVerdictWithDone(model, handlers) : renderVerdict(model, handlers);
    case 'not_counted': {
      const panel = statusPanel('not-counted');
      panel.append(element('p', 'This rep did not count', 'stage'));
      const reasons = element('ul', '', 'reasons');
      notCountedMessages(rep).forEach((message) => reasons.append(element('li', message)));
      panel.append(reasons, actions(button('Record again', handlers.onRecordAgain, 'primary')));
      return panel;
    }
    case 'send_failed': {
      const panel = text('Your rep was not sent. The recording is kept.');
      panel.append(actions(button('Send again', handlers.onSendAgain, 'primary'), button('Record again', handlers.onRecordAgain)));
      return panel;
    }
    case 'too_long': {
      const panel = statusPanel('too-long');
      panel.append(element('p', TOO_LONG_TEXT, 'stage'), actions(button('Check again', handlers.onCheckAgain, 'primary'), button('Record again', handlers.onRecordAgain)));
      return panel;
    }
    case 'check_failed': {
      const panel = text('The result could not be loaded.');
      panel.append(actions(button('Check again', handlers.onCheckAgain, 'primary'), button('Record again', handlers.onRecordAgain)));
      return panel;
    }
    case 'media_error': {
      const panel = statusPanel();
      renderMediaError(panel, model.mediaError, { onTryAgain: handlers.onTryAgain, onUpload: handlers.onUpload });
      return panel;
    }
    case 'load_failed': {
      const panel = text('The exercise could not be loaded.');
      panel.append(actions(button('Try again', handlers.onTryAgain, 'primary')));
      return panel;
    }
    case 'upload': return renderUpload(handlers);
    case 'complete': return renderDone(exercise, handlers);
    default: throw new Error(`Unknown trainer phase: ${phase}`);
  }
}

function renderVerdictWithDone(model, handlers) {
  const panel = renderVerdict(model, handlers);
  panel.append(renderDone(model.exercise, handlers));
  return panel;
}

export function renderTrainer(root, model, handlers) {
  const view = element('section', '', 'trainer');
  if (model.exercise) {
    view.append(renderCard(model.exercise, model.xstate), renderStreak(model.exercise, model.xstate), renderLadder(model.exercise, model.xstate));
  }
  view.append(renderPanel(model, handlers));
  root.replaceChildren(view);
  return view;
}

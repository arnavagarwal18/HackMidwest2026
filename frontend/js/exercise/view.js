// Draws the loop trainer from a plain model; every call rebuilds the screen, so it never holds state of its own.
// model: { exercise, xstate, phase, rep, slow, mediaError, history }
// handlers: { onPrimary, onRecordAgain, onCheckAgain, onSendAgain, onFullTake, onTryAgain, onUpload, onFile }
import { button, element } from '../dom.js';
import { renderMediaError } from '../media_error.js';
import {
  STILL_WORKING_TEXT, TOO_LONG_TEXT, formFlagsText, notCountedMessages, passMarkText, repFactsText, resultLine,
} from './model.js';
import { renderHeader, renderHistory, renderTempo } from './overview.js';

const statusPanel = (className = '') => element('div', '', `trainer-status ${className}`.trim(), { role: 'status' });

// The one large control of the screen (Record rep, Stop) and the quieter buttons next to it.
const primaryButton = (label, onClick, className = '') => button(label, onClick, `btn btn-primary btn-lg trainer-primary ${className}`.trim());
const secondaryButton = (label, onClick) => button(label, onClick, 'btn btn-secondary');

function actions(...buttons) {
  const row = element('p', '', 'actions');
  row.append(...buttons);
  return row;
}

// Everything about the rep behind one "Details" disclosure: why it passed or not, the counts, the form flags and the pass mark.
function renderDetails(exercise, rep) {
  const disclosure = element('details', '', 'disclosure rep-details');
  disclosure.append(element('summary', 'Details'));
  if (rep.reasons?.length) {
    const reasons = element('ul', '', 'reasons');
    rep.reasons.forEach((reason) => reasons.append(element('li', reason)));
    disclosure.append(reasons);
  }
  const { errors, timing } = repFactsText(rep);
  const flags = formFlagsText(exercise, rep);
  [errors && `${errors.label}: ${errors.value}`, timing && `${timing.label}: ${timing.value}`, flags].filter(Boolean)
    .forEach((fact) => disclosure.append(element('p', fact, 'rep-fact')));
  disclosure.append(element('p', `To pass a rep: ${passMarkText(exercise.pass_mark)}.`, 'pass-mark'));
  return disclosure;
}

function renderResult(model, handlers) {
  const { rep, exercise } = model;
  const tone = rep.exercise_complete ? 'done' : (rep.passed ? 'pass' : 'fail');
  const panel = statusPanel(`result-${tone}`);
  const next = rep.exercise_complete
    ? primaryButton('Record a full take', handlers.onFullTake)
    : primaryButton('Record rep', handlers.onPrimary);
  panel.append(element('p', resultLine(rep.tempo_bpm, exercise, rep), `verdict ${tone}`), actions(next), renderDetails(exercise, rep));
  return panel;
}

function renderDone(exercise, handlers) {
  const panel = statusPanel('result-done');
  panel.append(element('p', `Done — you passed ${exercise.target_bpm} BPM`, 'verdict done'), actions(primaryButton('Record a full take', handlers.onFullTake)));
  return panel;
}

function renderUpload(handlers) {
  const panel = statusPanel('upload');
  const input = element('input', '', '', { type: 'file', accept: 'audio/*,video/*', 'aria-label': 'Recording file' });
  input.addEventListener('change', () => handlers.onFile(input.files?.[0]));
  panel.append(element('p', 'Choose a recording of your rep (at most 60 seconds).'), input);
  return panel;
}

// Everything the panel under the tempo can show, by phase.
function renderPanel(model, handlers) {
  const { exercise, phase, rep } = model;
  const text = (message, className = 'stage') => { const p = statusPanel(); p.append(element('p', message, className)); return p; };
  switch (phase) {
    case 'loading': return text('Loading the exercise...');
    case 'ready': {
      const panel = statusPanel();
      panel.append(actions(primaryButton('Record rep', handlers.onPrimary)));
      return panel;
    }
    case 'recording': {
      const panel = statusPanel('is-recording');
      panel.append(element('p', 'Recording: the count-in plays, then play the rep.', 'stage recording'), actions(primaryButton('Stop', handlers.onPrimary, 'is-stop')));
      return panel;
    }
    case 'sending': return text('Sending your rep...');
    case 'scoring': {
      const panel = text('Checking your rep...');
      if (model.slow) panel.append(element('p', STILL_WORKING_TEXT, 'muted slow-note'));
      return panel;
    }
    case 'result': return renderResult(model, handlers);
    case 'not_counted': {
      const panel = statusPanel('not-counted');
      panel.append(element('p', 'This rep did not count', 'stage'));
      const reasons = element('ul', '', 'reasons');
      notCountedMessages(rep).forEach((message) => reasons.append(element('li', message)));
      panel.append(reasons, actions(primaryButton('Record again', handlers.onRecordAgain)));
      return panel;
    }
    case 'send_failed': {
      const panel = text('Your rep was not sent. The recording is kept.');
      panel.append(actions(primaryButton('Send again', handlers.onSendAgain), secondaryButton('Record again', handlers.onRecordAgain)));
      return panel;
    }
    case 'too_long': {
      const panel = statusPanel('too-long');
      panel.append(element('p', TOO_LONG_TEXT, 'stage'), actions(primaryButton('Check again', handlers.onCheckAgain), secondaryButton('Record again', handlers.onRecordAgain)));
      return panel;
    }
    case 'check_failed': {
      const panel = text('The result could not be loaded.');
      panel.append(actions(primaryButton('Check again', handlers.onCheckAgain), secondaryButton('Record again', handlers.onRecordAgain)));
      return panel;
    }
    case 'media_error': {
      const panel = statusPanel();
      renderMediaError(panel, model.mediaError, { onTryAgain: handlers.onTryAgain, onUpload: handlers.onUpload });
      return panel;
    }
    case 'load_failed': {
      const panel = text('The exercise could not be loaded.');
      panel.append(actions(primaryButton('Try again', handlers.onTryAgain)));
      return panel;
    }
    case 'upload': return renderUpload(handlers);
    case 'complete': return renderDone(exercise, handlers);
    default: throw new Error(`Unknown trainer phase: ${phase}`);
  }
}

export function renderTrainer(root, model, handlers) {
  const view = element('section', '', 'trainer');
  if (model.exercise) view.append(renderHeader(model.exercise), renderTempo(model.exercise, model.xstate));
  view.append(renderPanel(model, handlers));
  if (model.exercise) {
    const history = renderHistory(model.history);
    if (history) view.append(history);
  }
  root.replaceChildren(view);
  return view;
}

// Draws the loop trainer from a plain model; every call rebuilds the screen, so it never holds state of its own.
// model: { exercise, xstate, phase, rep, slow, mediaError, history }
// handlers: { onPrimary, onRecordAgain, onCheckAgain, onSendAgain, onFullTake, onTryAgain, onUpload, onFile }
import { button, element } from '../dom.js';
import { renderMediaError } from '../media_error.js';
import { badge, skeleton, stat } from '../ui/components.js';
import {
  STILL_WORKING_TEXT, TOO_LONG_TEXT, firstRepText, formFlagsText, nextRepText, notCountedMessages,
  repFactsText, tempoChangeText,
} from './model.js';
import { renderHeader, renderHistory, renderTempoCard } from './overview.js';

const statusPanel = (className = '') => element('div', '', `trainer-status ${className}`.trim(), { role: 'status' });

// The one large control of the screen (Record rep, Stop) and the quieter buttons next to it.
const primaryButton = (label, onClick, className = '') => button(label, onClick, `btn btn-primary btn-lg trainer-primary ${className}`.trim());
const secondaryButton = (label, onClick) => button(label, onClick, 'btn btn-secondary');

function actions(...buttons) {
  const row = element('p', '', 'actions');
  row.append(...buttons);
  return row;
}

function renderRepFacts(exercise, rep) {
  const row = element('div', '', 'rep-facts');
  const { errors, timing } = repFactsText(rep);
  if (errors) row.append(stat(errors.value, errors.label));
  if (timing) row.append(stat(timing.value, timing.label));
  const flags = formFlagsText(exercise, rep);
  if (flags) row.append(badge(flags.text, flags.tone));
  return row;
}

function renderVerdict(model, handlers) {
  const { rep, exercise } = model;
  const panel = statusPanel(rep.passed ? 'result-pass' : 'result-fail');
  const heading = element('div', '', 'verdict-row');
  heading.append(element('p', rep.passed ? 'PASS' : 'FAIL', `verdict ${rep.passed ? 'pass' : 'fail'}`), element('p', tempoChangeText(rep.tempo_bpm, rep), 'tempo-change'));
  panel.append(heading, renderRepFacts(exercise, rep));
  if (rep.reasons?.length) {
    const reasons = element('ul', '', 'reasons');
    rep.reasons.forEach((reason) => reasons.append(element('li', reason)));
    panel.append(reasons);
  }
  if (rep.exercise_complete) return panel; // the Done panel is added by the caller
  panel.append(element('p', nextRepText(rep.next_bpm), 'next-rep'), actions(primaryButton('Record rep', handlers.onPrimary)));
  return panel;
}

function renderDone(exercise, handlers) {
  const panel = statusPanel('done');
  panel.append(
    element('p', 'Done', 'verdict done'),
    element('p', `You passed ${exercise.target_bpm} BPM.`),
    actions(primaryButton('Record a full take', handlers.onFullTake)),
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

function renderVerdictWithDone(model, handlers) {
  const panel = renderVerdict(model, handlers);
  panel.append(renderDone(model.exercise, handlers));
  return panel;
}

// Everything the panel under the tempo card can show, by phase.
function renderPanel(model, handlers) {
  const { exercise, xstate, phase, rep } = model;
  const text = (message, className = 'stage') => { const p = statusPanel(); p.append(element('p', message, className)); return p; };
  switch (phase) {
    case 'loading': {
      const panel = text('Loading the exercise...');
      panel.append(skeleton(2));
      return panel;
    }
    case 'ready': {
      const panel = text(firstRepText(xstate.current_bpm), 'next-rep');
      panel.append(actions(primaryButton('Record rep', handlers.onPrimary)));
      return panel;
    }
    case 'recording': {
      const panel = statusPanel('is-recording');
      panel.append(element('p', 'Recording: the count-in plays, then play the rep. Press space to stop.', 'stage recording'), actions(primaryButton('Stop', handlers.onPrimary, 'is-stop')));
      return panel;
    }
    case 'sending': return text('Sending your rep...');
    case 'scoring': {
      const panel = text('Checking your rep...');
      panel.append(skeleton(2));
      if (model.slow) panel.append(element('p', STILL_WORKING_TEXT, 'muted slow-note'));
      return panel;
    }
    case 'result': return rep.exercise_complete ? renderVerdictWithDone(model, handlers) : renderVerdict(model, handlers);
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
  if (model.exercise) view.append(renderHeader(model.exercise), renderTempoCard(model.exercise, model.xstate));
  view.append(renderPanel(model, handlers));
  if (model.exercise) view.append(renderHistory(model.history));
  root.replaceChildren(view);
  return view;
}

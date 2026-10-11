import { reportError, showNotice } from '../banner.js';
import { state } from '../state.js';
import { element } from '../dom.js';
import { fetchResultsOnce, stageLabel, STAGES, unwrapFeedback } from '../results/load.js';
import { pollUntilDone } from '../results/polling.js';
import { refreshAfterKeyChange } from '../results/rerun.js';
import { mountOverlay } from '../results/overlay.js';
import { renderRequestFailed, renderTooLong, renderWorking } from '../results/status.js';
import { renderDone, renderFailed } from '../results/view.js';
import { render as renderChat } from './chat.js';

// Results for one take: poll the analysis, then show the hero and its rows (see results/view.js).
// The coach sheet is mounted into #coach-root; it stays closed until the 'Ask coach' button (or anything else) fires 'coach:open'.
export async function render(root, params) {
  const { take } = params;
  const sessionId = state.session_id ?? 'no-session';
  state.current_take_id = take;
  const view = element('section', '', 'results');
  const coachRoot = element('div', '', '', { id: 'coach-root' });
  root.append(view, coachRoot);
  let shown = null; // the analysis, feedback and plan on screen, so a new coach style can redraw them with its feedback
  const chat = renderChat(coachRoot, { take, onFeedback: redrawWithFeedback });

  // The coach style changed and the feedback was built again: draw the results again with it (nothing to redraw before they are shown).
  function redrawWithFeedback(body) {
    if (isActive() && shown) show({ ...shown, ...unwrapFeedback(body) });
  }

  const isActive = () => view.isConnected; // false once the router has moved to another screen
  let overlay = null; // the body-lines overlay of the finished take on screen (none for mic takes)
  const show = (result) => {
    shown = result;
    overlay?.destroy();
    overlay = null;
    if (result.analysis.status === 'failed') {
      chat.setResults({});
      return renderFailed(view, result.analysis);
    }
    const rendered = renderDone(view, result, { sessionId, take, rerun: restartAfterTransposition });
    overlay = rendered?.player ? mountOverlay(rendered, { sessionId, take }) : null; // a can't-tell take has no player
    overlay?.onAnalysis(result.analysis);
    chat.setResults({ jumpContext: rendered ? { index: rendered.index, jumper: rendered.jumper } : null, feedback: result.feedback });
  };

  function failRequest(err) {
    if (!isActive()) return;
    reportError(err);
    renderRequestFailed(view, checkAgain);
  }

  async function checkAgain() {
    try {
      const result = await fetchResultsOnce(sessionId, take);
      if (!isActive()) return;
      if (result.done) show(result);
      else renderTooLong(view, stageLabel(result.analysis), checkAgain);
    } catch (err) {
      failRequest(err);
    }
  }

  // The user chose a key by hand: wait for the back end to check the take again and rebuild its feedback, and show them.
  async function restartAfterTransposition(semitones) {
    const previousFeedbackId = state.current_feedback_id;
    const setTo = `Transposition set to ${semitones > 0 ? '+' : ''}${semitones}`;
    showNotice(`${setTo}; checking your take again.`);
    renderWorking(view, STAGES.processing, false);
    try {
      const refreshed = await refreshAfterKeyChange({ sessionId, take, semitones, previousFeedbackId, isActive });
      if (!isActive()) return;
      if (refreshed.outcome === 'done') {
        showNotice(`${setTo}; your take was checked again.`); // the 'checking' notice must not outlive the check
        show(refreshed.result);
      } else if (refreshed.outcome === 'timeout') {
        renderTooLong(view, STAGES.transcribed, checkAgain);
      }
    } catch (err) {
      failRequest(err);
    }
  }

  async function start() {
    renderWorking(view, STAGES.processing, false);
    try {
      const polled = await pollUntilDone({
        fetchOnce: () => fetchResultsOnce(sessionId, take),
        isActive,
        onTick: ({ result, slow }) => renderWorking(view, stageLabel(result.analysis), slow),
      });
      if (polled.outcome === 'done') {
        if (isActive()) show(polled.result);
      } else if (polled.outcome === 'timeout') renderTooLong(view, stageLabel(polled.result.analysis), checkAgain);
    } catch (err) {
      failRequest(err);
    }
  }

  await start();
}

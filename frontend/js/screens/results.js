import { reportError, showNotice } from '../banner.js';
import { state } from '../state.js';
import { element } from '../dom.js';
import { fetchResultsOnce, stageLabel, STAGES } from '../results/load.js';
import { pollUntilDone } from '../results/polling.js';
import { shouldAutoKey } from '../results/autokey.js';
import { claimAutoKey, runAutoKey } from '../results/autokey_run.js';
import { refreshAfterKeyChange } from '../results/rerun.js';
import { mountOverlay } from '../results/overlay.js';
import { renderRequestFailed, renderTooLong, renderWorking } from '../results/status.js';
import { renderDone, renderFailed } from '../results/view.js';
import { render as renderChat } from './chat.js';

// Results for one take: poll the analysis, then show the six parts (see results/view.js).
// The Instructor chat panel sits beside the results; chat.js owns its own panel element.
export async function render(root, { take }) {
  const sessionId = state.session_id ?? 'no-session';
  state.current_take_id = take;
  const view = element('section', '', 'results');
  const chatPanel = element('aside', '', 'chat-panel');
  root.className = 'with-chat';
  root.append(view, chatPanel);
  const chat = renderChat(chatPanel, { take });

  const isActive = () => view.isConnected; // false once the router has moved to another screen
  let overlay = null; // the body-lines overlay of the finished take on screen (none for mic takes)
  const show = (result, note = null) => {
    overlay?.destroy();
    overlay = null;
    if (result.analysis.status === 'failed') {
      chat.setResults({});
      return renderFailed(view, result.analysis);
    }
    const rendered = renderDone(view, result, { sessionId, take, rerun: restartAfterTransposition, note });
    overlay = rendered?.player ? mountOverlay(rendered, { sessionId, take }) : null; // a can't-tell take has no player
    overlay?.onAnalysis(result.analysis);
    chat.setResults({ jumpContext: rendered ? { index: rendered.index, jumper: rendered.jumper } : null, feedback: result.feedback });
  };

  // A can't-tell take whose notes hardly matched is tried in other keys once; anything else is shown as it is.
  async function showOrFindKey(result) {
    if (!shouldAutoKey(result.analysis) || !claimAutoKey(sessionId, take)) return show(result);
    const original = result.analysis.transposition?.semitones ?? 0;
    const found = await runAutoKey({ view, sessionId, take, original, isActive });
    if (!isActive()) return;
    if (found.outcome === 'found') show(found.result, found.note);
    else show(result, found.note);
  }

  function failRequest(err) {
    if (!isActive()) return;
    reportError(err);
    renderRequestFailed(view, checkAgain);
  }

  async function checkAgain() {
    try {
      const result = await fetchResultsOnce(sessionId, take);
      if (!isActive()) return;
      if (result.done) await showOrFindKey(result);
      else renderTooLong(view, stageLabel(result.analysis), checkAgain);
    } catch (err) {
      failRequest(err);
    }
  }

  // The user chose a key by hand: wait for the re-check, write the feedback again, and show it (no automatic search on top).
  async function restartAfterTransposition(semitones) {
    claimAutoKey(sessionId, take);
    const setTo = `Transposition set to ${semitones > 0 ? '+' : ''}${semitones}`;
    showNotice(`${setTo}; checking your take again.`);
    renderWorking(view, STAGES.processing, false);
    try {
      const refreshed = await refreshAfterKeyChange({ sessionId, take, semitones, isActive });
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
      if (polled.outcome === 'done') await showOrFindKey(polled.result);
      else if (polled.outcome === 'timeout') renderTooLong(view, stageLabel(polled.result.analysis), checkAgain);
    } catch (err) {
      failRequest(err);
    }
  }

  await start();
}

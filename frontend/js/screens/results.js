import { reportError, showNotice } from '../banner.js';
import { state } from '../state.js';
import { element } from '../dom.js';
import { fetchResultsOnce, stageLabel, STAGES } from '../results/load.js';
import { pollUntilDone } from '../results/polling.js';
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
  const show = (result) => {
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

  function restartAfterTransposition(semitones) {
    showNotice(`Transposition set to ${semitones > 0 ? '+' : ''}${semitones}; checking your take again.`);
    return start();
  }

  async function start() {
    renderWorking(view, STAGES.processing, false);
    try {
      const polled = await pollUntilDone({
        fetchOnce: () => fetchResultsOnce(sessionId, take),
        isActive,
        onTick: ({ result, slow }) => renderWorking(view, stageLabel(result.analysis), slow),
      });
      if (polled.outcome === 'done') show(polled.result);
      else if (polled.outcome === 'timeout') renderTooLong(view, stageLabel(polled.result.analysis), checkAgain);
    } catch (err) {
      failRequest(err);
    }
  }

  await start();
}

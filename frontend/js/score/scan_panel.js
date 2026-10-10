// The area under the score tabs: spinner while a photo is read, the plain error when a scan fails,
// and the check-your-scan list with Confirm and Rescan once the score is read.
import { confirmScore, getScoreStatus } from '../api.js';
import { reportError } from '../banner.js';
import { state } from '../state.js';
import { formatDoubtfulBar, scanErrorMessage, SLOW_MESSAGE, TOO_LONG_MESSAGE } from './format.js';
import { pollScoreStatus } from './poll.js';
import { button, el, runGuarded } from './ui.js';

// onConfirmed() runs after the score is confirmed; onRescan() sends the learner back to the photo tab.
// pollOptions lets a test shorten the waits.
export function createScanPanel({ onConfirmed, onRescan, onChooseFile, pollOptions = {} }) {
  const root = el('section', { className: 'scan-panel', attrs: { 'aria-live': 'polite' } });
  let generation = 0; // a newer result or a clear() makes older polling stop

  const clear = () => {
    generation += 1;
    root.replaceChildren();
  };

  // Shows what a status or a score upload answered. `source` is 'photo', 'file' or 'builtin'.
  async function show(status, source) {
    clear();
    if (status.score_error) return showScanError(status);
    if (status.score_status === 'scanning') return poll(source);
    if (status.score_status === 'scanned') return showReview(status, source);
  }

  function showScanError(status) {
    root.append(
      el('p', { text: scanErrorMessage(status), className: 'scan-error' }),
      el('p', { children: [button('Try another photo', onRescan), ' ', button('Choose a file', onChooseFile)] }),
    );
  }

  async function poll(source) {
    const mine = generation;
    const message = el('p', { text: 'Reading your photo...' });
    root.append(el('div', { className: 'spinner', attrs: { role: 'status', 'aria-label': 'Reading your photo' } }), message);
    try {
      const result = await pollScoreStatus({
        fetchStatus: () => getScoreStatus(state.session_id),
        isActive: () => mine === generation && root.isConnected,
        onSlow: () => { message.textContent = SLOW_MESSAGE; },
        ...pollOptions,
      });
      if (result.outcome === 'done') return show(result.status, source);
      if (result.outcome === 'timeout') return showTimeout(source, TOO_LONG_MESSAGE);
    } catch (err) {
      if (mine !== generation) return;
      reportError(err);
      showTimeout(source, "We couldn't check the scan.");
    }
  }

  function showTimeout(source, text) {
    clear();
    const check = button('Check again', () => checkOnce(check, source));
    root.append(el('p', { text }), check);
  }

  // One more poll: show the answer, or the same message again if the scan is still running.
  async function checkOnce(checkButton, source) {
    const status = await runGuarded([checkButton], () => getScoreStatus(state.session_id));
    if (!status || !root.isConnected) return;
    if (status.score_status === 'scanning') return showTimeout(source, TOO_LONG_MESSAGE);
    show(status, source);
  }

  function showReview(status, source) {
    const confirm = button('Confirm', () => confirmReviewed(confirm), 'primary');
    const rescan = button('Rescan', () => { clear(); onRescan(); });
    root.append(el('h2', { text: 'Check your score' }), el('p', { text: `${status.bars} bars found.`, className: 'bar-count' }));
    if (source === 'photo' && !status.double_checked) {
      root.append(el('p', { text: 'This scan was not double-checked, so look at every bar against your paper.', className: 'muted' }));
    }
    root.append(...listSection('Warnings', status.warnings, (warning) => warning));
    root.append(...listSection('Check these bars against your paper', status.doubtful_bars, formatDoubtfulBar));
    root.append(el('p', { children: [confirm, ' ', rescan] }));
  }

  async function confirmReviewed(confirm) {
    const confirmed = await runGuarded([confirm], () => confirmScore(state.session_id));
    if (!confirmed) return;
    state.score = {
      status: 'confirmed',
      bars: confirmed.bars,
      tempo_bpm: confirmed.tempo_bpm,
      time_signature: confirmed.time_signature,
    };
    onConfirmed();
  }

  return { element: root, show, clear };
}

function listSection(heading, items, format) {
  if (!items || items.length === 0) return [];
  return [el('h3', { text: heading }), el('ul', { children: items.map((item) => el('li', { text: format(item) })) })];
}

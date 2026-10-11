// The area under the score tabs: spinner while a photo is read, the plain error when a scan fails,
// and the check-your-scan list with Confirm and Rescan once the score is read.
import { confirmScore, getScoreStatus } from '../api.js';
import { reportError } from '../banner.js';
import { state } from '../state.js';
import { doubtfulBarReadings, scanErrorMessage, SLOW_MESSAGE, TOO_LONG_MESSAGE } from './format.js';
import { pollScoreStatus } from './poll.js';
import { button, el, runGuarded } from './ui.js';

const actionRow = (buttons) => el('p', { className: 'scan-actions', children: buttons });

// onConfirmed() runs after the score is confirmed; onRescan() sends the learner back to the photo tab.
// pollOptions lets a test shorten the waits. The demo upload passes onScanFailure(status) to take over a scan that failed or
// came back with no bars (instead of the "Try another photo" buttons).
export function createScanPanel({ onConfirmed, onRescan, onChooseFile, onScanFailure, pollOptions = {} }) {
  const root = el('section', { className: 'scan-panel', attrs: { 'aria-live': 'polite' } });
  let generation = 0; // a newer result or a clear() makes older polling stop

  // A scanned photo with no bars is only a failure for a caller that handles failures itself (the demo upload).
  const scanFailed = (status) => status.score_error || (onScanFailure && status.score_status === 'scanned' && !status.bars);

  const clear = () => {
    generation += 1;
    root.replaceChildren();
  };

  // Shows what a status or a score upload answered. `source` is 'photo', 'file' or 'builtin'.
  async function show(status, source) {
    clear();
    if (scanFailed(status)) return (onScanFailure ?? showScanError)(status);
    if (status.score_status === 'scanning') return poll(source);
    if (status.score_status === 'scanned') return showReview(status, source);
  }

  function showScanError(status) {
    root.append(
      el('p', { text: scanErrorMessage(status), className: 'scan-error' }),
      actionRow([button('Try another photo', onRescan, 'btn btn-primary primary'), button('Choose a file', onChooseFile, 'btn btn-ghost')]),
    );
  }

  async function poll(source) {
    const mine = generation;
    const message = el('p', { text: 'Reading your photo...' });
    root.append(el('div', { className: 'scan-reading', children: [el('div', { className: 'spinner', attrs: { role: 'status', 'aria-label': 'Reading your photo' } }), message] }));
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
    const check = button('Check again', () => checkOnce(check, source), 'btn btn-secondary');
    root.append(el('p', { text }), actionRow([check]));
  }

  // One more poll: show the answer, or the same message again if the scan is still running.
  async function checkOnce(checkButton, source) {
    const status = await runGuarded([checkButton], () => getScoreStatus(state.session_id));
    if (!status || !root.isConnected) return;
    if (status.score_status === 'scanning') return showTimeout(source, TOO_LONG_MESSAGE);
    show(status, source);
  }

  function showReview(status, source) {
    state.score.status = 'scanned';
    const confirm = button('Confirm', () => confirmReviewed(confirm), 'btn btn-primary primary');
    const rescan = button('Rescan', () => { clear(); onRescan(); }, 'btn btn-ghost');
    root.append(el('p', { text: `${status.bars} bars found.`, className: 'bar-count' }));
    if (source === 'photo' && !status.double_checked) {
      root.append(el('p', { text: 'This scan was not double-checked, so look at every bar against your paper.', className: 'muted' }));
    }
    root.append(...warningsList(status.warnings ?? []), ...doubtfulBarsSection(status.doubtful_bars ?? []), actionRow([confirm, rescan]));
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

function warningsList(warnings) {
  if (warnings.length === 0) return [];
  return [el('ul', { className: 'scan-warnings', children: warnings.map((warning) => el('li', { text: warning })) })];
}

// One plain row per doubtful bar, so each can be checked against the paper on its own.
function doubtfulBarsSection(doubtfulBars) {
  if (doubtfulBars.length === 0) return [];
  return [
    el('h3', { text: 'Check these bars against your paper' }),
    el('ul', { className: 'doubtful-list', children: doubtfulBars.map(doubtfulBarRow) }),
  ];
}

function doubtfulBarRow(doubtful) {
  const { bar, scan, second } = doubtfulBarReadings(doubtful);
  return el('li', { children: [
    el('strong', { text: `Bar ${bar}` }),
    el('dl', { children: [el('dt', { text: 'Scan read' }), el('dd', { text: scan }), el('dt', { text: 'Second reading' }), el('dd', { text: second })] }),
  ] });
}

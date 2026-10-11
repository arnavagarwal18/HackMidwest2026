// What the demo upload shows: a status line, the scan check (the normal one), the video progress and a place for failures.
import { createBuiltinTab } from '../score/builtin_tab.js';
import { createScanPanel } from '../score/scan_panel.js';
import { el, button } from '../score/ui.js';
import { createUploadProgress } from './progress.js';

const RESCAN_TEXT = 'You chose to rescan, so this photo was not used.';
const FALLBACK_HINT = 'Read the photo again, or pick a built-in score and carry on with the same video.';

// What went wrong with a photo read, in words for the dev (the normal score screen's "choose a file" advice does not apply here).
export function photoFailureText(status) {
  if (status.score_error) return status.score_error_message || `The photo could not be read (${status.score_error}).`;
  return 'The photo was read but no bars were found in it.';
}

export function createDemoView() {
  const status = el('p', { className: 'muted', attrs: { role: 'status' } });
  const progress = createUploadProgress();
  const prompt = el('div', { className: 'demo-prompt' });
  let settleScan = () => {};
  const panel = createScanPanel({
    onConfirmed: () => { panel.clear(); settleScan({ ok: true }); },
    onRescan: () => settleScan({ ok: false, message: RESCAN_TEXT }),
    onScanFailure: (scan) => settleScan({ ok: false, message: photoFailureText(scan) }),
  });

  const failureLine = (message) => el('p', { text: message, className: 'scan-error', attrs: { role: 'alert' } });

  // Shows a failure with its choices; resolves to the id of the one pressed.
  function ask(message, choices) {
    return new Promise((resolve) => {
      const answer = (id) => { prompt.replaceChildren(); resolve(id); };
      const buttons = choices.map(({ id, label }, index) => button(label, () => answer(id), index === 0 ? 'primary' : undefined));
      prompt.replaceChildren(failureLine(message), el('p', { children: buttons }));
    });
  }

  // The photo did not work: resolves to { action: 'retry' } or { action: 'builtin', piece }.
  function chooseFallback(message) {
    return new Promise((resolve) => {
      const done = (choice) => { prompt.replaceChildren(); resolve(choice); };
      const builtins = createBuiltinTab({ choose: async (piece) => done({ action: 'builtin', piece }) });
      prompt.replaceChildren(
        failureLine(`${message} ${FALLBACK_HINT}`),
        el('p', { children: [button('Read the photo again', () => done({ action: 'retry' }), 'primary')] }),
        el('h3', { text: 'Built-in scores' }),
        builtins,
      );
    });
  }

  // Shows the normal scan check for what POST .../score/photo answered; resolves { ok: true } once the dev confirms,
  // or { ok: false, message } when the read failed, found no bars or was sent back with Rescan.
  function reviewScan(answer) {
    return new Promise((resolve) => {
      settleScan = resolve;
      panel.show(answer, 'photo').catch((err) => {
        console.error('Showing the scan check failed:', err);
        resolve({ ok: false, message: `The scan check could not be shown: ${err.message}` });
      });
    });
  }

  return {
    element: el('div', { children: [status, progress.element, panel.element, prompt] }),
    setStatus: (text) => { status.textContent = text; },
    progress,
    ask,
    chooseFallback,
    reviewScan,
  };
}

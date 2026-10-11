// Change piece: a built-in piece (default; one tap, no review), a file or a photo (check the scan, then confirm). All end on Play.
import { getScoreStatus } from '../api.js';
import { clearBanner, reportError } from '../banner.js';
import { state } from '../state.js';
import { createBuiltinTab } from '../score/builtin_tab.js';
import { createFileTab } from '../score/file_tab.js';
import { createPhotoTab } from '../score/photo_tab.js';
import { createScanPanel } from '../score/scan_panel.js';
import { openSession, useBuiltinPiece } from '../score/session.js';
import { button, el, loadScoreStyles } from '../score/ui.js';

const CONFIRMED_NOTICE = 'Choosing another piece starts a new practice session.';
const PLAY_HASH = '#/take';

export async function render(root) {
  loadScoreStyles();
  const panel = createScanPanel({
    onConfirmed: () => { window.location.hash = PLAY_HASH; },
    onRescan: () => selectTab('photo'),
    onChooseFile: () => selectTab('file'),
  });

  // call(sessionId) is an api.js upload; errors reach the tab's guarded button and the red banner.
  async function submit(call, source) {
    const sessionId = await openSession();
    const answer = await call(sessionId);
    clearBanner();
    state.score.status = answer.score_status;
    await panel.show(answer, source);
  }

  async function chooseBuiltin(pieceId) {
    await useBuiltinPiece(pieceId);
    clearBanner();
    window.location.hash = PLAY_HASH;
  }

  const tabs = [
    { id: 'builtin', label: 'Built-in', body: createBuiltinTab({ choose: chooseBuiltin }) },
    { id: 'file', label: 'File', body: createFileTab({ submit }) },
    { id: 'photo', label: 'Photo', body: createPhotoTab({ submit }) },
  ];
  const tabButtons = tabs.map((tab) => {
    const node = button(tab.label, () => selectTab(tab.id), 'tab');
    node.setAttribute('role', 'tab');
    node.dataset.tab = tab.id;
    return node;
  });
  tabs.forEach((tab) => { tab.body.className = 'tab-body'; tab.body.dataset.tab = tab.id; });

  function selectTab(id) {
    tabButtons.forEach((node) => node.setAttribute('aria-selected', String(node.dataset.tab === id)));
    tabs.forEach((tab) => { tab.body.hidden = tab.id !== id; });
  }

  root.append(el('h1', { text: 'Change piece' }));
  if (state.score.status === 'confirmed') root.append(el('p', { text: CONFIRMED_NOTICE, className: 'muted' }));
  root.append(
    el('div', { className: 'tabs', attrs: { role: 'tablist' }, children: tabButtons }),
    ...tabs.map((tab) => tab.body),
    panel.element,
  );
  selectTab(hasScanInProgress() ? 'photo' : 'builtin');
  await showExistingScan(panel);
}

// Arriving mid-scan or with an unconfirmed scan (after a reload): pick up where it left off.
const hasScanInProgress = () => ['scanning', 'scanned'].includes(state.score.status);

async function showExistingScan(panel) {
  if (!hasScanInProgress()) return;
  try {
    await panel.show(await getScoreStatus(state.session_id), 'photo');
  } catch (err) {
    reportError(err);
  }
}

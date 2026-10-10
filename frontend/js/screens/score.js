// Score: three ways to give the app the piece (photo, file, built-in), then check the scan and confirm it.
import { createSession, getScoreStatus } from '../api.js';
import { clearBanner, reportError } from '../banner.js';
import { clearSession, setSession, state } from '../state.js';
import { createBuiltinTab } from '../score/builtin_tab.js';
import { createFileTab } from '../score/file_tab.js';
import { createPhotoTab } from '../score/photo_tab.js';
import { createScanPanel } from '../score/scan_panel.js';
import { button, el, loadScoreStyles } from '../score/ui.js';

const CONFIRMED_NOTICE = 'This session already has a confirmed score. Choosing another score starts a new session.';

// A confirmed score is locked (409 wrong_state), so a new score needs a new session on the same instrument.
async function openSession() {
  if (state.score.status !== 'confirmed') return state.session_id;
  const session = await createSession(state.instrument);
  clearSession();
  setSession(session.session_id, session.instrument);
  return session.session_id;
}

export async function render(root) {
  if (!state.session_id) {
    window.location.hash = '#/start';
    return;
  }
  loadScoreStyles();
  const panel = createScanPanel({
    onConfirmed: () => { window.location.hash = '#/calibrate'; },
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

  const tabs = [
    { id: 'photo', label: 'Photo', body: createPhotoTab({ submit }) },
    { id: 'file', label: 'File', body: createFileTab({ submit }) },
    { id: 'builtin', label: 'Built-in', body: createBuiltinTab({ submit }) },
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

  root.append(el('h1', { text: 'Your score' }));
  if (state.score.status === 'confirmed') root.append(el('p', { text: CONFIRMED_NOTICE, className: 'muted' }));
  root.append(
    el('div', { className: 'tabs', attrs: { role: 'tablist' }, children: tabButtons }),
    ...tabs.map((tab) => tab.body),
    panel.element,
  );
  selectTab('photo');
  await showExistingScan(panel);
}

// Arriving mid-scan or with an unconfirmed scan (after a reload): pick up where it left off.
async function showExistingScan(panel) {
  if (!['scanning', 'scanned'].includes(state.score.status)) return;
  try {
    await panel.show(await getScoreStatus(state.session_id), 'photo');
  } catch (err) {
    reportError(err);
  }
}

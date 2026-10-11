// Node tests for the review part of the scan panel (js/score/scan_panel.js): what a finished scan shows.
import assert from 'node:assert/strict';
import test from 'node:test';
import { installFakeBrowser } from './fake_env.mjs';

installFakeBrowser();
const { createScanPanel } = await import('../js/score/scan_panel.js');
const { CHECK_EVERY_BAR_MESSAGE } = await import('../js/score/format.js');

const SCANNED = { score_status: 'scanned', bars: 16, doubtful_bars: [], double_checked: false, warnings: [] };

async function panelAfter(status, source) {
  const panel = createScanPanel({ onConfirmed() {}, onRescan() {}, onChooseFile() {} });
  await panel.show(status, source);
  return panel.element;
}

test('a photo scan shows the bar count and one plain line to check every bar', async () => {
  const root = await panelAfter(SCANNED, 'photo');
  assert.ok(root.hasText('16 bars found.'));
  assert.equal(CHECK_EVERY_BAR_MESSAGE, 'Check every bar against your paper before you confirm.');
  assert.equal(root.find((n) => n.textContent === CHECK_EVERY_BAR_MESSAGE).length > 0, true);
  assert.equal(root.hasText('double-checked'), false);
  assert.equal(root.hasText('disagree'), false);
  assert.ok(root.button('Confirm') && root.button('Rescan'));
});

test('a score from a file or a built-in piece shows no check-every-bar line', async () => {
  for (const source of ['file', 'builtin']) {
    const root = await panelAfter(SCANNED, source);
    assert.equal(root.hasText(CHECK_EVERY_BAR_MESSAGE), false);
  }
});

test('warnings the back end sends are still listed', async () => {
  const root = await panelAfter({ ...SCANNED, warnings: ['Bar 3 has no notes.'] }, 'photo');
  assert.ok(root.hasText('Bar 3 has no notes.'));
});

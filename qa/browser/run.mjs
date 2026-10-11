// Checks every screen of the web front end in headless Chrome, in mock mode and in real mode, one page at a time in ONE Chrome.
//   node qa/browser/run.mjs [origin]      (default http://127.0.0.1:8120; start the back end there first, with AI off)
// Writes qa/browser/results.json and prints the summary table and the problem list. Chrome is stopped when the run ends, however it ends.
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { buildRealFixtures } from './fixtures.mjs';
import { checkScreen } from './check_screen.mjs';
import { NAV_HASHES, MOCK_SCREENS, realScreens } from './routes.mjs';
import { rapidNavigation } from './rapid_nav.mjs';
import { attachProbe } from './page_probe.mjs';
import { countOutcomes, problemList, summaryTable } from './report.mjs';

const origin = process.argv[2] ?? 'http://127.0.0.1:8120';
const here = new URL('.', import.meta.url).pathname;
const RESULTS_FILE = `${here}results.json`;

if (new URL(origin).port === '8000' || new URL(origin).port === '8001') throw new Error('Ports 8000 and 8001 are the owner\'s live servers; use another port.');

// The wrapper adds the fake microphone and camera; frontend/tests/browser.mjs adds --mute-audio and cleans up the profile.
process.env.REAL_CHROME ??= ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome'].find(existsSync);
process.env.CHROME = `${here}chrome_fake_media.sh`;
const { launchChrome, openPage } = await import('../../frontend/tests/browser.mjs');

async function requireServer() {
  try {
    const response = await fetch(`${origin}/builtins`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  } catch (err) {
    throw new Error(`No back end answering at ${origin} (${err.message}). Start it: backend/.venv/bin/python -m uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 8120`);
  }
}

await requireServer();
console.log('Building real-mode test data through the API...');
const fixtures = await buildRealFixtures(origin);
console.log('Fixtures:', JSON.stringify(fixtures));

const chrome = await launchChrome();
let page;
let probe;
const stopChrome = () => { probe?.close(); page?.close(); chrome.stop(); };
process.on('SIGINT', () => { stopChrome(); process.exit(130); });
process.on('uncaughtException', (err) => { // an error inside a DevTools event handler must not leave Chrome running
  console.error(`The check run crashed: ${err.stack}`);
  stopChrome();
  process.exit(1);
});
const records = [];
const rapid = [];
try {
  page = await openPage(chrome.browserWsUrl);
  probe = await attachProbe(chrome.browserWsUrl, page);
  for (const [mode, specs] of [['mock', MOCK_SCREENS], ['real', realScreens(fixtures)]]) {
    for (const spec of specs) {
      const record = await checkScreen({ page, probe, origin, mode, spec });
      records.push(record);
      console.log(`${mode} ${spec.name}: ${record.hash} heading=${JSON.stringify(record.heading)}`);
    }
  }
  rapid.push(await rapidNavigation({ page, probe, origin, mode: 'mock', hashes: NAV_HASHES.mock, stored: null }));
  rapid.push(await rapidNavigation({ page, probe, origin, mode: 'real', hashes: NAV_HASHES.real(fixtures), stored: fixtures.sessionId }));
} catch (err) {
  console.error(`The check run failed: ${err.stack}`);
  process.exitCode = 1;
} finally {
  stopChrome();
}

mkdirSync(here, { recursive: true });
writeFileSync(RESULTS_FILE, JSON.stringify({ origin, fixtures, records, rapid }, null, 2));
console.log(`\n${summaryTable(records)}\n\n${JSON.stringify(countOutcomes(records))}\n\nProblems:\n${problemList(records)}`);
console.log(`\nRapid navigation:\n${JSON.stringify(rapid, null, 2)}\nFull data: ${RESULTS_FILE}`);

// Takes the visual-check screenshots of the design system (start, score, calibrate, take, results; light and dark) into dev/screens/.
// Run: CHROME=<path to chrome> node frontend/dev/screenshots.mjs        (mock mode, nothing else needs to run)
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { launchChrome, openPage, startServer } from '../tests/browser.mjs';

const OUT_DIR = join(dirname(fileURLToPath(import.meta.url)), 'screens');
const SESSION_KEY = 'practice_coach_session_id_mock';
const VIEWPORT = { width: 1200, height: 800, deviceScaleFactor: 1, mobile: false };
const SCREENS = [
  { name: 'start', hash: '#/start', ready: `location.hash === '#/start' && document.querySelector('main').children.length > 0`, session: false },
  { name: 'score', hash: '#/take', ready: `document.querySelector('.piece-line') !== null`, session: true, then: { run: `location.hash = '#/score'`, ready: `document.querySelectorAll('.piece-card').length > 0` } },
  { name: 'score-scan', hash: '#/score', ready: `document.querySelectorAll('.doubtful-card').length > 0`, session: 'sess_unconfirmed' },
  { name: 'calibrate', hash: '#/calibrate', ready: `document.querySelector('.calibrate-stepper') !== null && document.querySelector('.calibrate-qr svg') !== null`, session: true },
  { name: 'take', hash: '#/take', ready: `document.querySelector('main').children.length > 0`, session: true },
  { name: 'results', hash: '#/results/take_1', ready: `document.querySelector('.chat-panel') !== null`, session: true },
];

mkdirSync(OUT_DIR, { recursive: true });
const { server, origin } = await startServer();
const { stop: stopChrome, browserWsUrl } = await launchChrome();
process.on('exit', () => { stopChrome(); server.close(); });

async function shoot({ name, hash, ready, session, then }, scheme) {
  const page = await openPage(browserWsUrl);
  await page.send('Emulation.setDeviceMetricsOverride', VIEWPORT);
  await page.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: scheme }] });
  await page.goto(`${origin}/?mock=1#/start`);
  await page.eval(session ? `localStorage.setItem('${SESSION_KEY}', '${session === true ? 'sess_mock1' : session}')` : `localStorage.removeItem('${SESSION_KEY}')`);
  await page.goto(`${origin}/?mock=1&poll_ms=100${hash}`);
  if (session) await page.eval(`location.hash = '${hash}'`);
  await page.waitFor(ready);
  if (then) { await page.eval(then.run); await page.waitFor(then.ready); }
  await new Promise((resolve) => setTimeout(resolve, 800)); // let fonts, fades and polling settle
  const { data } = await page.send('Page.captureScreenshot', { format: 'png' });
  const file = join(OUT_DIR, `${name}-${scheme}.png`);
  writeFileSync(file, Buffer.from(data, 'base64'));
  console.log(`${file} (console errors: ${page.errors.length})`);
  page.close();
}

try {
  for (const scheme of ['light', 'dark']) for (const screen of SCREENS) await shoot(screen, scheme);
} finally {
  stopChrome();
  server.close();
}

// Takes the visual-check screenshots of the design system (start, score, calibrate, take, results, the trainer; light and dark) into dev/screens/.
// Run: CHROME=<path to chrome> node frontend/dev/screenshots.mjs [name-prefix]        (mock mode, nothing else needs to run)
// With a prefix (e.g. "trainer") only the screens whose name starts with it are taken.
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { launchChrome, openPage, startServer } from '../tests/browser.mjs';

const OUT_DIR = join(dirname(fileURLToPath(import.meta.url)), 'screens');
const SESSION_KEY = 'practice_coach_session_id_mock';
const VIEWPORT = { width: 1200, height: 800, deviceScaleFactor: 1, mobile: false };
const MOBILE = { width: 390, height: 844, deviceScaleFactor: 1, mobile: true };
const TRAINER_HEIGHT = 1300; // tall enough for the result card and the history under it
const TRAINER_READY = `document.querySelector('.trainer-primary') !== null`;
// Headless Chrome has no microphone: getUserMedia answers with a stream from a silent oscillator (a recorder only starts on a live source).
const FAKE_MICROPHONE = `navigator.mediaDevices.getUserMedia = async () => {
  const context = new AudioContext(); const sink = context.createMediaStreamDestination(); const tone = context.createOscillator();
  const silence = context.createGain(); silence.gain.value = 0.0001; tone.connect(silence).connect(sink); tone.start(); return sink.stream;
};`;
// Presses Record rep, waits until recording, presses space to stop, then waits for the verdict.
const RECORD_A_REP = async (page) => {
  await page.eval(`document.querySelector('.trainer-primary').click()`);
  await page.waitFor(`document.querySelector('.is-recording') !== null`);
  await page.eval(`document.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space' }))`);
  await page.waitFor(`document.querySelector('.verdict') !== null`);
};
// Opens the coach sheet the way the Results button does, once the panel has drawn its opening line and chips.
const OPEN_COACH = async (page) => {
  await page.waitFor(`document.querySelector('.chat-transcript .chat-turn') !== null && document.querySelector('.coach-menu-button') !== null`);
  await page.eval(`document.dispatchEvent(new CustomEvent('coach:open'))`);
  await page.waitFor(`document.querySelector('.coach-sheet') !== null && !document.querySelector('.coach-sheet').hidden`);
};
// A conversation that has not started: the mock chat history is empty, so the sheet shows its opening line and chips.
const FRESH_CHAT = `const realFetch = window.fetch; window.fetch = (url, ...rest) => String(url).includes('get_chat')
  ? Promise.resolve(new Response('{"turns":[]}', { status: 200, headers: { 'content-type': 'application/json' } })) : realFetch(url, ...rest);`;
const COACH_READY = `document.querySelector('.results .bar-strip-section') !== null`;
const SCREENS = [
  { name: 'start', hash: '#/start', ready: `location.hash === '#/start' && document.querySelector('main').children.length > 0`, session: false },
  { name: 'score', hash: '#/take', ready: `document.querySelector('.take-form') !== null`, session: true, then: { run: `location.hash = '#/score'`, ready: `document.querySelectorAll('.piece-row').length > 0` } },
  { name: 'score-scan', hash: '#/score', ready: `document.querySelectorAll('.doubtful-list li').length > 0`, session: 'sess_unconfirmed' },
  { name: 'calibrate', hash: '#/calibrate', ready: `document.querySelector('.calibrate-steps') !== null && document.querySelector('.calibrate-qr svg') !== null`, session: true },
  { name: 'take', hash: '#/take', ready: `document.querySelector('main').children.length > 0`, session: true },
  { name: 'results', hash: '#/results/take_1', ready: `document.querySelector('.results .bar-strip-section') !== null`, session: true, full: true },
  { name: 'results-details', hash: '#/results/take_1', ready: `document.querySelector('.results .bar-strip-section') !== null`, session: true, full: true, prepare: `document.querySelectorAll('.results details').forEach((d) => { d.open = true; })` },
  { name: 'results-mobile', hash: '#/results/take_1', ready: `document.querySelector('.results .bar-strip-section') !== null`, session: true, full: true, viewport: MOBILE },
  { name: 'results-details-mobile', hash: '#/results/take_1', ready: `document.querySelector('.results .bar-strip-section') !== null`, session: true, full: true, viewport: MOBILE, prepare: `document.querySelectorAll('.results details').forEach((d) => { d.open = true; })` },
  { name: 'coach-sheet', hash: '#/results/take_1', ready: COACH_READY, session: true, script: FRESH_CHAT, act: OPEN_COACH },
  { name: 'coach-history', hash: '#/results/take_1', ready: COACH_READY, session: true, act: OPEN_COACH },
  { name: 'coach-menu', hash: '#/results/take_1', ready: COACH_READY, session: true, script: FRESH_CHAT, act: async (page) => { await OPEN_COACH(page); await page.eval(`document.querySelector('.coach-menu-button').click()`); } },
  { name: 'coach-sheet-mobile', hash: '#/results/take_1', ready: COACH_READY, session: true, script: FRESH_CHAT, act: OPEN_COACH, viewport: { width: 390, height: 844, deviceScaleFactor: 1, mobile: true } },
  { name: 'progress', hash: '#/progress', ready: `document.querySelector('.exercise-item') !== null`, session: true, full: true },
  { name: 'trace', hash: '#/trace/fb_1', ready: `document.querySelector('.trace-event') !== null`, session: true, full: true },
  { name: 'demo', hash: '#/demo', ready: `document.querySelector('.demo .demo-picks') !== null`, session: true },
  { name: 'play-more', hash: '#/take', ready: `document.querySelector('.take-more') !== null`, session: true, prepare: `document.querySelector('.take-more').open = true` },
  { name: 'play-mobile', hash: '#/take', ready: `document.querySelector('.take-more') !== null`, session: true, viewport: { width: 390, height: 844, deviceScaleFactor: 1, mobile: true } },
  { name: 'trainer-ready', hash: '#/exercise/ex1', ready: TRAINER_READY, session: true, height: TRAINER_HEIGHT },
  { name: 'trainer-pass', hash: '#/exercise/ex1', ready: TRAINER_READY, session: true, act: RECORD_A_REP, height: TRAINER_HEIGHT },
  { name: 'trainer-fail', hash: '#/exercise/ex_fail', ready: TRAINER_READY, session: true, act: RECORD_A_REP, height: TRAINER_HEIGHT },
  { name: 'trainer-fail-details', hash: '#/exercise/ex_fail', ready: TRAINER_READY, session: true, act: RECORD_A_REP, prepare: `document.querySelectorAll('.trainer details').forEach((d) => { d.open = true; })`, height: TRAINER_HEIGHT },
];

mkdirSync(OUT_DIR, { recursive: true });
const { server, origin } = await startServer();
const { stop: stopChrome, browserWsUrl } = await launchChrome();
process.on('exit', () => { stopChrome(); server.close(); });

async function shoot({ name, hash, ready, session, script, then, act, prepare, viewport = {}, height = VIEWPORT.height, full = false }, scheme) {
  const page = await openPage(browserWsUrl);
  await page.send('Emulation.setDeviceMetricsOverride', { ...VIEWPORT, height, ...viewport });
  await page.send('Page.addScriptToEvaluateOnNewDocument', { source: FAKE_MICROPHONE });
  if (script) await page.send('Page.addScriptToEvaluateOnNewDocument', { source: script });
  await page.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: scheme }] });
  await page.goto(`${origin}/?mock=1#/start`);
  await page.eval(session ? `localStorage.setItem('${SESSION_KEY}', '${session === true ? 'sess_mock1' : session}')` : `localStorage.removeItem('${SESSION_KEY}')`);
  await page.goto(`${origin}/?mock=1&poll_ms=100${hash}`);
  if (session) await page.eval(`location.hash = '${hash}'`);
  await page.waitFor(ready);
  if (then) { await page.eval(then.run); await page.waitFor(then.ready); }
  if (act) await act(page);
  if (prepare) await page.eval(prepare);
  await new Promise((resolve) => setTimeout(resolve, 800)); // let fonts, fades and polling settle
  if (full) await page.send('Emulation.setDeviceMetricsOverride', { ...VIEWPORT, ...viewport, height: await page.eval('document.documentElement.scrollHeight') }); // a tall page is shot whole
  const { data } = await page.send('Page.captureScreenshot', { format: 'png' });
  const file = join(OUT_DIR, `${name}-${scheme}.png`);
  writeFileSync(file, Buffer.from(data, 'base64'));
  console.log(`${file} (console errors: ${page.errors.length})`);
  page.close();
}

try {
  const prefix = process.argv[2] ?? '';
  for (const scheme of ['light', 'dark']) for (const screen of SCREENS.filter(({ name }) => name.startsWith(prefix))) await shoot(screen, scheme);
} finally {
  stopChrome();
  server.close();
}

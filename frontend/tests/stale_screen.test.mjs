// Browser test: a screen that answers after the learner moved on must not write into the new screen.
// Run: node frontend/tests/stale_screen.test.mjs  (mock mode, headless Chrome; the mock answers after 150 ms)
import assert from 'node:assert/strict';
import { launchChrome, openPage, startServer } from './browser.mjs';

const SESSION_KEY = 'practice_coach_session_id_mock';
const SLOW_MS = 800;
const SETTLE_MS = SLOW_MS + 400; // long enough for the slow Progress answer to have arrived

const { server, origin } = await startServer();
const { stop: stopChrome, browserWsUrl } = await launchChrome();
process.on('exit', () => { stopChrome(); server.close(); });

const page = await openPage(browserWsUrl);
let failure = null;
try {
  await page.goto(`${origin}/?mock=1#/start`);
  await page.eval(`localStorage.setItem('${SESSION_KEY}', 'sess_mock1')`);
  await page.goto(`${origin}/?mock=1&reload=1#/start`); // a new query makes it a real reload, so resume.js runs
  await page.waitFor(`location.hash === '#/take'`); // resume.js sends a confirmed session to the take screen

  // Make the mock answer Progress slowly (800 ms) so that its answer lands after Trace's (150 ms), as a slow server would.
  await page.eval(`(() => {
    const realSetTimeout = window.setTimeout;
    window.setTimeout = (fn, ms, ...args) => realSetTimeout(fn, location.hash === '#/progress' ? ${SLOW_MS} : ms, ...args);
  })()`);
  // Progress is still waiting for the server when the learner clicks on to Trace.
  await page.eval(`location.hash = '#/progress'`);
  await page.waitFor(`import('/js/mock.js').then((m) => m.mockRequestLog.some((r) => r.path.endsWith('/progress')))`);
  await page.eval(`location.hash = '#/trace/fb_1'`);
  await page.waitFor(`document.querySelector('.trace-mode')`);
  await new Promise((resolve) => setTimeout(resolve, SETTLE_MS));

  assert.deepEqual(await page.eval(`[...document.querySelectorAll('#screen h1')].map((h) => h.textContent)`), ['Trace'], 'only the Trace screen is shown');
  assert.equal(await page.eval(`document.querySelectorAll('#screen .exercise-list, #screen table').length`), 0, 'no Progress content in the Trace screen');
  assert.deepEqual(page.errors, [], 'console errors');
} catch (err) {
  failure = err;
}
page.close();
stopChrome();
server.close();
console.log(failure ? `FAIL  a late Progress answer does not overwrite Trace\n      ${failure.stack ?? failure}` : 'PASS  a late Progress answer does not overwrite Trace');
process.exit(failure ? 1 : 0);

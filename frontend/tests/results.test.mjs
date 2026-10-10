// Browser tests for the results screen, in mock mode, in headless Chrome.  Run: node frontend/tests/results.test.mjs
import assert from 'node:assert/strict';
import { launchChrome, openPage, startServer } from './browser.mjs';

const SESSION_KEY = 'practice_coach_session_id_mock';
const FAST = 'poll_ms=100';
const results = [];

const { server, origin } = await startServer();
const { stop: stopChrome, browserWsUrl } = await launchChrome();
let cleanedUp = false;
function cleanUp() { // also runs if the script crashes, so Chrome never outlives it
  if (cleanedUp) return;
  cleanedUp = true;
  stopChrome();
  server.close();
}
process.on('exit', cleanUp);

// A fresh tab on the results screen for `take`, with a session stored the way resume.js expects.
async function openResults(take, query = FAST) {
  const page = await openPage(browserWsUrl);
  await page.goto(`${origin}/?mock=1#/start`);
  await page.eval(`localStorage.setItem('${SESSION_KEY}', 'sess_mock1')`);
  await page.goto(`${origin}/?mock=1&${query}#/start`);
  await page.waitFor(`location.hash === '#/take'`); // resume.js sends a confirmed session to the take screen
  await page.eval(`(() => {
    window.__stages = [];
    new MutationObserver(() => document.querySelectorAll('.stage').forEach((s) => { if (!window.__stages.includes(s.textContent)) window.__stages.push(s.textContent); }))
      .observe(document.getElementById('screen'), { subtree: true, childList: true, characterData: true });
    location.hash = '#/results/${take}';
  })()`);
  return page;
}

const text = (page, selector) => page.eval(`[...document.querySelectorAll(${JSON.stringify(selector)})].map((e) => e.textContent.trim())`);
const count = (page, selector) => page.eval(`document.querySelectorAll(${JSON.stringify(selector)}).length`);
const click = (page, selector, index = 0) => page.eval(`document.querySelectorAll(${JSON.stringify(selector)})[${index}].click()`);
const analysisRequests = (page) => page.eval(`import('/js/mock.js').then((m) => m.mockRequestLog.filter((r) => r.method === 'GET' && r.path.endsWith('/analysis')).length)`);
const mediaTime = (page, tag) => page.eval(`document.querySelector('${tag}').currentTime`);
const rowInView = (page, bar) => page.eval(`(() => { const r = document.getElementById('bar-row-${bar}').getBoundingClientRect(); return r.top >= 0 && r.bottom <= window.innerHeight; })()`);

async function test(name, run) {
  const pages = [];
  const open = async (...args) => { const page = await openResults(...args); pages.push(page); return page; };
  try {
    await run(open);
    for (const page of pages) assert.deepEqual(page.errors, [], 'console errors');
    results.push({ name, ok: true });
  } catch (err) {
    results.push({ name, ok: false, err });
  } finally {
    pages.forEach((page) => page.close());
  }
}

await test('video take renders all six parts and the stages', async (open) => {
  const page = await open('take_1');
  await page.waitFor(`document.querySelector('.results .tier1')`);
  assert.deepEqual((await page.eval('window.__stages')).slice(0, 2), ['Hearing notes...', 'Checking against the score...']);
  assert.ok((await page.eval('window.__stages')).includes('Writing feedback...'), 'feedback-not-ready shows the Writing feedback stage');
  assert.equal(await count(page, '.slow-note'), 0);
  assert.equal(await count(page, '.tier1 .sentence'), 2);
  assert.deepEqual(await text(page, '.coach .badge-checked'), ['checked', 'checked']);
  assert.deepEqual(await page.eval(`[...document.querySelectorAll('.bar-row')].map((r) => r.dataset.bar)`), ['3', '4']);
  assert.match((await text(page, '#bar-row-3'))[0], /Bar 3.*1 wrong.*1 missed.*1 extra.*steady \(\+?0\.5%\)/);
  assert.match((await text(page, '#bar-row-4'))[0], /dragging \(-8%\)/);
  assert.equal(await count(page, '.video-stage video[controls]'), 1);
  assert.equal(await count(page, '#form-flag-slot'), 1);
  assert.equal(await page.eval(`document.querySelector('.exercise a').getAttribute('href')`), '#/exercise/ex1');
  assert.deepEqual(await text(page, '.exercise a'), ['Practise']);
  assert.equal(await page.eval(`document.querySelector('a.trace-link').getAttribute('href')`), '#/trace/fb_1');
  assert.deepEqual(await text(page, 'a.trace-link'), ['How the AI worked']);
  assert.equal(await count(page, '.fallback-notice'), 0);
});

await test('clicking a sentence or chip seeks 1 s earlier, highlights and scrolls to the bar row', async (open) => {
  const page = await open('take_1', `${FAST}`);
  await page.waitFor(`document.querySelector('.results .tier1')`);
  await page.eval(`document.querySelector('.results').style.paddingBottom = '2000px'; document.getElementById('bar-row-3').scrollIntoView({ block: 'start' }); window.scrollTo(0, 0)`);
  await click(page, '.tier1 .sentence-text', 1); // bar 4 at 6.0 s
  await page.waitFor(`document.querySelector('video').currentTime >= 5 && document.querySelector('video').currentTime < 6`);
  assert.deepEqual(await page.eval(`[...document.querySelectorAll('.bar-row.highlighted')].map((r) => r.dataset.bar)`), ['4']);
  assert.ok(await rowInView(page, 4), 'bar 4 row scrolled into view');
  await click(page, '.coach .sentence:nth-child(1) .chip'); // n:t1:3:2 -> bar 3 at 4.5 s
  await page.waitFor(`document.querySelector('video').currentTime >= 3.5 && document.querySelector('video').currentTime < 4.5`);
  assert.deepEqual(await page.eval(`[...document.querySelectorAll('.bar-row.highlighted')].map((r) => r.dataset.bar)`), ['3']);
  assert.deepEqual(await text(page, '.coach .sentence:nth-child(2) .chip'), ['bar 4']);
  assert.equal(await page.eval(`document.querySelector('video').paused`), false);
});

await test('a mic take shows an audio player and jumps in it', async (open) => {
  const page = await open('take_mic');
  await page.waitFor(`document.querySelector('.results .tier1')`);
  assert.equal(await count(page, 'video'), 0);
  assert.equal(await count(page, '#form-flag-slot'), 0);
  await click(page, '.tier1 .sentence-text', 0); // bar 3 at 4.5 s
  await page.waitFor(`document.querySelector('audio').currentTime >= 3.5 && document.querySelector('audio').currentTime < 4.5`);
  assert.deepEqual(await page.eval(`[...document.querySelectorAll('.bar-row.highlighted')].map((r) => r.dataset.bar)`), ['3']);
});

await test('fallback mode says the AI coach is unavailable', async (open) => {
  const page = await open('take_fallback');
  await page.waitFor(`document.querySelector('.fallback-notice')`);
  assert.deepEqual(await text(page, '.fallback-notice'), ['AI coach unavailable; showing measured results.']);
  assert.equal(await count(page, '.tier1 .sentence'), 2);
  assert.equal(await count(page, '.coach'), 0, 'fallback sentences repeat tier 1 and are not shown twice');
  assert.equal(await count(page, '.exercise'), 1);
});

await test('a failed analysis shows the back end message and Record again', async (open) => {
  const page = await open('take_failed');
  await page.waitFor(`document.querySelector('.stopped-message')`);
  assert.deepEqual(await text(page, '.stopped-message'), ['There was no sound in that recording. Check the microphone and record again.']);
  assert.equal(await count(page, 'select'), 0);
  await click(page, 'button.record-again');
  await page.waitFor(`location.hash === '#/take'`);
});

await test("a can't-tell take shows the message, the transposition control and Record again, and re-checks after a change", async (open) => {
  const page = await open('take_cant_tell');
  await page.waitFor(`document.querySelector('.stopped-message')`);
  assert.match((await text(page, '.stopped-message'))[0], /couldn't tell/);
  assert.deepEqual(await page.eval(`(() => { const o = [...document.querySelectorAll('#transposition-select option')]; return [o.length, o[0].value, o.at(-1).value]; })()`), [25, '-12', '12']);
  assert.equal(await count(page, 'button.record-again'), 1);
  assert.equal(await count(page, '.bar-list'), 0);
  assert.equal(await count(page, '.exercise'), 1, 'the plan is still shown');
  await page.eval(`(() => { const s = document.getElementById('transposition-select'); s.value = '3'; })()`);
  await page.eval(`[...document.querySelectorAll('button')].find((b) => b.textContent === 'Change transposition').click()`);
  await page.waitFor(`import('/js/mock.js').then((m) => m.mockRequestLog.some((r) => r.method === 'POST' && r.path === '/sessions/sess_mock1/transposition' && r.body?.semitones === 3))`);
  await page.waitFor(`window.__stages.filter((s) => s === 'Hearing notes...').length >= 1 && document.querySelector('#banner').textContent.includes('Transposition set to +3')`);
  await page.waitFor(`document.querySelector('.stopped-message')`); // still can't tell in the mock, so the control is back
});

await test('a mock analysis that never finishes shows Still working, then stops at the limit', async (open) => {
  const page = await open('take_stuck', 'poll_ms=100&slow_after_s=1&give_up_after_s=3');
  await page.waitFor(`document.querySelector('.slow-note')`, 5000);
  assert.deepEqual(await text(page, '.slow-note'), ['Still working - this can take a while for long takes']);
  await page.waitFor(`document.querySelector('.too-long')`, 8000);
  assert.deepEqual(await text(page, '.too-long .stage'), ['This is taking too long']);
  assert.deepEqual(await text(page, '.too-long button'), ['Check again', 'Record again']);
  const polled = await analysisRequests(page);
  await new Promise((resolve) => setTimeout(resolve, 1000));
  assert.equal(await analysisRequests(page), polled, 'no polling after the limit');
  await click(page, 'button.check-again');
  await page.waitFor(`import('/js/mock.js').then((m) => m.mockRequestLog.filter((r) => r.path.endsWith('/analysis')).length === ${polled + 1})`);
  await new Promise((resolve) => setTimeout(resolve, 600));
  assert.equal(await analysisRequests(page), polled + 1, 'Check again polls exactly once');
  assert.equal(await count(page, '.too-long'), 1);
});

cleanUp();
for (const { name, ok, err } of results) console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : `\n      ${err.stack ?? err}`}`);
process.exit(results.every((r) => r.ok) ? 0 : 1);

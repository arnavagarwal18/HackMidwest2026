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
const boxInView = (page, bar) => page.eval(`(() => { const r = document.querySelector('.bar-box[data-bar="${bar}"]').getBoundingClientRect(); return r.top >= 0 && r.bottom <= window.innerHeight; })()`);
const selectedBars = (page) => page.eval(`[...document.querySelectorAll('.bar-box[aria-pressed="true"]')].map((b) => b.dataset.bar)`);

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

await test('video take renders the recording, verdict, bars, plan and detail rows, and the stages', async (open) => {
  const page = await open('take_1');
  await page.waitFor(`document.querySelector('.results .tier1')`);
  assert.deepEqual((await page.eval('window.__stages')).slice(0, 2), ['Hearing notes...', 'Checking against the score...']);
  assert.ok((await page.eval('window.__stages')).includes('Writing feedback...'), 'feedback-not-ready shows the Writing feedback stage');
  assert.equal(await count(page, '.slow-note'), 0);
  assert.equal(await count(page, '.tier1 .sentence'), 2);
  assert.equal(await count(page, '.coach .sentence'), 2);
  assert.equal(await count(page, '.results .badge, .results .card'), 0, 'no badges or cards on the results');
  assert.deepEqual(await page.eval(`[...document.querySelectorAll('.bar-box')].map((b) => b.dataset.bar)`), ['3', '4']);
  assert.match((await text(page, '#bar-detail'))[0], /Bar 3.*1 wrong.*1 missed.*1 extra.*steady \(\+?0\.5%\)/);
  await click(page, '.bar-box', 1);
  assert.match((await text(page, '#bar-detail'))[0], /dragging \(-8%\)/);
  assert.equal(await count(page, '.video-stage video[controls]'), 1);
  assert.equal(await count(page, '#overlay-controls-slot'), 1);
  await page.waitFor(`document.querySelector('#overlay-toggle')`); // the overlay has loaded its tracks
  assert.equal(await count(page, '.form-flags, .form-flag'), 0, 'no list of form flags under the video');
  assert.equal(await count(page, '#overlay-controls-slot .sentence-text'), 0);
  assert.equal(await page.eval(`document.querySelector('.exercise a').getAttribute('href')`), '#/exercise/ex1');
  assert.deepEqual(await text(page, '.exercise a'), ['Practice this']);
  assert.equal(await page.eval(`document.querySelector('a.trace-link').getAttribute('href')`), '#/trace/fb_1');
  assert.deepEqual(await text(page, 'a.trace-link'), ['How the AI worked']);
  assert.equal(await count(page, '.fallback-notice'), 0);
  assert.match((await text(page, '.headline'))[0], /\w/, 'a headline sentence leads the summary');
  assert.deepEqual(await text(page, '.score-strip .lbl:not(.detail)'), ['Pitch', 'Rhythm', 'Bars to work on']);
  assert.deepEqual(await text(page, '.detect-text'), ['Key: 0, instrument default · bars 3–4']);
  assert.equal(await page.eval(`document.getElementById('detect-panel').hidden`), true);
  await click(page, '.detect-change');
  assert.equal(await page.eval(`document.getElementById('detect-panel').hidden`), false);
  assert.equal(await count(page, '#detect-panel #transposition-select'), 1, 'Change opens the existing key override');
  assert.deepEqual(await text(page, 'button.primary'), ['Ask coach'], 'one filled button on the results');
});

await test('the recording comes first, then a verdict naming the weak spot, three labelled scores with Focus here on the weakest, one sentence and the buttons', async (open) => {
  const page = await open('take_1');
  await page.waitFor(`document.querySelector('.hero')`);
  assert.equal(await page.eval(`document.querySelector('.results').firstElementChild.id`), 'results-media', 'the recording renders first');
  assert.equal(await page.eval(`document.querySelector('.results').children[1].className`), 'hero');
  assert.match((await text(page, '.verdict-title'))[0], / — (pitch|rhythm|tempo) is your weak spot$/);
  assert.equal(await count(page, '.hero-word, .hero-number'), 0);
  assert.deepEqual(await page.eval(`[...document.querySelectorAll('.score-name')].map((e) => e.firstChild.textContent)`), ['Pitch', 'Rhythm', 'Tempo']);
  assert.ok((await text(page, '.score-measure')).every((measure) => /notes|bars|Not measured/.test(measure)), 'each score says what it measures');
  assert.equal(await count(page, '.score-item.is-focus'), 1, 'only one score is marked');
  assert.deepEqual(await text(page, '.score-item.is-focus .focus-tag'), ['Focus here'], 'the mark is a word, not colour alone');
  const weakest = (await page.eval(`document.querySelector('.is-focus .score-name').firstChild.textContent`)).toLowerCase();
  assert.ok((await text(page, '.verdict-title'))[0].includes(weakest), 'the headline names the marked score');
  assert.equal(await count(page, '.suggestion'), 1);
  assert.deepEqual(await text(page, '.hero .actions button'), ['Ask coach', 'Try again']);
  assert.deepEqual(await page.eval(`[...document.querySelectorAll('.results details.disclosure')].map((d) => [d.querySelector('summary').textContent, d.open])`), [['The numbers', false], ['Detailed feedback', false]], 'the remaining detail starts closed');
  assert.ok(await page.eval(`[...document.querySelectorAll('.hero button, .results summary, .bar-box, .practice-step .btn, .play-bar')].every((e) => e.getBoundingClientRect().height >= 44 && e.getBoundingClientRect().width >= 44)`), 'tap targets are at least 44px');
});

await test('from 901px the coach gets a 360px column only while a docked panel shows; otherwise the results take the full width', async (open) => {
  const page = await open('take_1');
  await page.send('Emulation.setDeviceMetricsOverride', { width: 1200, height: 800, deviceScaleFactor: 1, mobile: false });
  await page.waitFor(`document.querySelector('.hero')`);
  await page.waitFor(`[...document.querySelectorAll('.coach-close')].some((b) => b.textContent === 'Collapse')`);
  await page.eval(`document.querySelector('.coach-close').click()`); // the real coach panel is docked and open from the start; collapse it so only the fake one below counts
  const widths = () => page.eval(`[document.querySelector('.results-layout'), document.querySelector('.results')].map((e) => Math.round(e.getBoundingClientRect().width))`);
  const [layoutWidth, resultsWidth] = await widths();
  assert.equal(resultsWidth, layoutWidth, 'no docked panel: no blank column');
  await page.eval(`(() => { const docked = document.createElement('div'); docked.className = 'coach-sheet is-docked'; docked.id = 'fake-docked'; document.getElementById('coach-root').append(docked); })()`);
  assert.equal(await page.eval(`Math.round(document.getElementById('coach-root').getBoundingClientRect().width)`), 360);
  assert.equal(await page.eval(`getComputedStyle(document.getElementById('coach-root')).position`), 'sticky');
  await page.eval(`document.getElementById('fake-docked').hidden = true`);
  assert.deepEqual(await widths(), [layoutWidth, layoutWidth], 'a collapsed panel gives the width back');
});

await test('the coach panel is not on the page while the take is processed, and appears with the results', async (open) => {
  const page = await open('take_1', 'poll_ms=400');
  await page.waitFor(`document.querySelector('.wait-steps')`);
  assert.equal(await count(page, '#coach-root, .coach-sheet'), 0, 'no coach panel while processing');
  await page.waitFor(`document.querySelector('.hero')`);
  assert.equal(await count(page, '#coach-root .coach-sheet'), 1, 'the coach panel is mounted with the results');
  assert.equal(await count(page, '#coach-root'), 1);
});

await test('Ask coach opens the coach sheet through the coach:open event, and Try again goes to the take screen', async (open) => {
  const page = await open('take_1');
  await page.waitFor(`document.getElementById('ask-coach')`);
  assert.equal(await count(page, '#coach-root'), 1);
  assert.equal(await count(page, 'aside.chat-panel, main.with-chat'), 0, 'the old side panel is gone');
  await page.eval(`window.__opened = 0; document.addEventListener('coach:open', () => { window.__opened += 1; })`);
  await click(page, '#ask-coach');
  assert.equal(await page.eval('window.__opened'), 1, 'the click dispatches coach:open');
  assert.equal(await page.eval(`document.querySelector('#coach-root .coach-sheet').hidden`), false, 'the sheet in #coach-root opens');
  await page.eval(`document.querySelector('#coach-root .coach-close').click()`);
  await click(page, '.hero .try-again');
  await page.waitFor(`location.hash === '#/take'`);
});

await test('Bar by bar: Good / Okay / Needs work boxes, the worst selected at first; a click shows that bar, arrows move, Play this bar seeks', async (open) => {
  const page = await open('take_1');
  await page.waitFor(`document.querySelector('.bar-box')`);
  assert.deepEqual(await text(page, '.bar-box-word'), ['Needs work', 'Needs work'], 'a word, not only a colour (bar 4 has 1 of 2 notes right)');
  assert.deepEqual(await page.eval(`[...document.querySelectorAll('.bar-box')].map((b) => b.getAttribute('aria-label'))`), ['Bar 3, needs work', 'Bar 4, needs work']);
  assert.deepEqual(await selectedBars(page), ['3'], 'the worst bar is selected at first');
  assert.equal(await page.eval(`document.querySelector('video').currentTime`), 0, 'nothing plays on its own');
  assert.equal(await count(page, '.bar-legend li'), 3);
  await click(page, '.bar-box', 1);
  assert.deepEqual(await selectedBars(page), ['4']);
  assert.match((await text(page, '#bar-detail'))[0], /Bar 4 · Needs work.*late.*Bar 4.*dragging/);
  assert.notEqual(await page.eval(`getComputedStyle(document.querySelector('.bar-box.selected')).outlineStyle`), 'none', 'the selected box is outlined');
  assert.deepEqual(await text(page, '#bar-detail .loop-bar'), ['Loop this bar']);
  await page.eval(`document.querySelector('.bar-box[data-bar="4"]').focus()`);
  await page.eval(`document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'Home', bubbles: true }))`);
  assert.equal(await page.eval(`document.activeElement.dataset.bar`), '3', 'Home moves to the first box');
  assert.deepEqual(await selectedBars(page), ['3']);
  await page.eval(`document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }))`);
  assert.equal(await page.eval(`document.activeElement.dataset.bar`), '4', 'ArrowRight moves to the next box');
  await click(page, '#bar-detail .play-bar');
  await page.waitFor(`document.querySelector('video').currentTime >= 5 && document.querySelector('video').currentTime < 6`);
  assert.deepEqual(await text(page, 'button.primary'), ['Ask coach'], 'the bar buttons are not filled');
});

await test('Practice next lists the plan as steps that go to their bar or open the exercise', async (open) => {
  const page = await open('take_1');
  await page.waitFor(`document.querySelector('.practice-next')`);
  const steps = await count(page, '.practice-step');
  assert.ok(steps >= 1 && steps <= 3, `${steps} steps`);
  assert.equal(await page.eval(`document.querySelector('.practice-step a').getAttribute('href')`), '#/exercise/ex1');
  const goTo = await page.eval(`document.querySelector('.practice-step .go-to-bar')?.textContent ?? ''`);
  if (goTo) {
    await click(page, '.practice-step .go-to-bar');
    assert.deepEqual(await selectedBars(page), [goTo.replace('Go to bar ', '')]);
  }
});

await test('Loop this bar opens the plan exercise with the bars and about 75% of the take tempo as a hint; Play again goes to the take screen', async (open) => {
  const page = await open('take_1');
  await page.waitFor(`document.querySelector('#bar-detail .loop-bar')`);
  assert.deepEqual(await page.eval(`[...document.querySelectorAll('#bar-detail .loop-bar')].map((a) => a.dataset.bar + a.getAttribute('href'))`), ['3#/exercise/ex1']);
  await click(page, '.bar-box', 1);
  assert.deepEqual(await page.eval(`[...document.querySelectorAll('#bar-detail .loop-bar')].map((a) => a.dataset.bar + a.getAttribute('href'))`), ['4#/exercise/ex1']);
  await click(page, '#bar-detail .loop-bar');
  await page.waitFor(`location.hash === '#/exercise/ex1'`);
  await page.waitFor(`document.querySelector('.loop-hint')?.textContent`);
  assert.match((await text(page, '.loop-hint'))[0], /Looping bar 4.*start near 66 BPM/);
  await page.eval(`location.hash = '#/results/take_1'`);
  await page.waitFor(`document.querySelector('#bar-detail .play-again-bar')`);
  await click(page, '#bar-detail .play-again-bar');
  await page.waitFor(`location.hash === '#/take'`);
});

await test('clicking a sentence or chip seeks 1 s earlier, selects the bar box and scrolls it into view', async (open) => {
  const page = await open('take_1', `${FAST}`);
  await page.waitFor(`document.querySelector('.results .tier1')`);
  await page.eval(`document.querySelector('.results').style.paddingBottom = '2000px'; window.scrollTo(0, document.documentElement.scrollHeight)`);
  await click(page, '.tier1 .sentence-text', 1); // bar 4 at 6.0 s
  await page.waitFor(`document.querySelector('video').currentTime >= 5 && document.querySelector('video').currentTime < 6`);
  assert.deepEqual(await selectedBars(page), ['4']);
  assert.ok(await boxInView(page, 4), 'bar 4 box scrolled into view');
  assert.match((await text(page, '#bar-detail'))[0], /Bar 4/, 'the detail shows the bar jumped to');
  await click(page, '.coach .sentence:nth-child(1) .chip'); // n:t1:3:2 -> bar 3 at 4.5 s
  await page.waitFor(`document.querySelector('video').currentTime >= 3.5 && document.querySelector('video').currentTime < 4.5`);
  assert.deepEqual(await selectedBars(page), ['3']);
  assert.deepEqual(await text(page, '.coach .sentence:nth-child(2) .chip'), ['bar 4']);
  assert.equal(await page.eval(`document.querySelector('video').paused`), false);
});

await test('a mic take shows an audio player and jumps in it', async (open) => {
  const page = await open('take_mic');
  await page.waitFor(`document.querySelector('.results .tier1')`);
  assert.equal(await count(page, 'video'), 0);
  assert.equal(await count(page, '#overlay-controls-slot'), 0);
  await click(page, '.tier1 .sentence-text', 0); // bar 3 at 4.5 s
  await page.waitFor(`document.querySelector('audio').currentTime >= 3.5 && document.querySelector('audio').currentTime < 4.5`);
  await click(page, '.bar-box', 1);
  await click(page, '.tier1 .sentence-text', 0);
  assert.deepEqual(await selectedBars(page), ['3']);
});

await test('fallback mode says the AI coach is unavailable', async (open) => {
  const page = await open('take_fallback');
  await page.waitFor(`document.querySelector('.results .fallback-notice')`); // the chat panel has its own notice
  assert.deepEqual(await text(page, '.results .fallback-notice'), ['AI coach unavailable; showing measured results.']);
  assert.equal(await count(page, '.tier1 .sentence'), 2);
  assert.equal(await count(page, '.coach'), 0, 'fallback sentences repeat tier 1 and are not shown twice');
  assert.equal(await count(page, '.exercise'), 1);
});

await test('a failed analysis shows the back end message and Record again', async (open) => {
  const page = await open('take_failed');
  await page.waitFor(`document.querySelector('.stopped-message')`);
  assert.deepEqual(await text(page, '.stopped-message'), ['There was no sound in that recording. Check the microphone and record again.']);
  assert.equal(await count(page, 'select'), 0);
  assert.equal(await count(page, '#coach-root, .coach-sheet'), 0, 'no coach panel after a failed analysis');
  await click(page, 'button.record-again');
  await page.waitFor(`location.hash === '#/take'`);
});

await test("a can't-tell take shows the message, the transposition control and Record again, and re-checks after a change", async (open) => {
  const page = await open('take_cant_tell');
  await page.waitFor(`document.querySelector('.stopped-message')`);
  assert.match((await text(page, '.stopped-message'))[0], /couldn't tell/);
  assert.deepEqual(await page.eval(`(() => { const o = [...document.querySelectorAll('#transposition-select option')]; return [o.length, o[0].value, o.at(-1).value]; })()`), [25, '-12', '12']);
  assert.equal(await count(page, 'button.record-again'), 1);
  assert.deepEqual(await text(page, '.key-summary'), ['Key: 0, instrument default']);
  assert.deepEqual(await text(page, '.heard-summary'), ['What I heard: best match to the score 21%.']);
  assert.match((await text(page, '.next-action'))[0], /closer to the microphone/); // the mock take is few_pairs
  assert.deepEqual(await text(page, 'button.primary'), ['Record again'], 'one next action, filled');
  assert.equal(await count(page, '.bar-strip-section'), 0);
  assert.equal(await count(page, '.exercise'), 1, 'the plan is still shown');
  await page.eval(`(() => { const s = document.getElementById('transposition-select'); s.value = '3'; })()`);
  await page.eval(`[...document.querySelectorAll('button')].find((b) => b.textContent === 'Change transposition').click()`);
  await page.waitFor(`import('/js/mock.js').then((m) => m.mockRequestLog.some((r) => r.method === 'POST' && r.path === '/sessions/sess_mock1/transposition' && r.body?.semitones === 3))`);
  await page.waitFor(`window.__stages.filter((s) => s === 'Hearing notes...').length >= 1 && document.querySelector('#banner').textContent.includes('Transposition set to +3')`);
  await page.waitFor(`document.querySelector('.stopped-message')`); // still can't tell in the mock, so the control is back
  assert.deepEqual(await text(page, '.key-summary'), ['Key: +3, set by you'], 'the analysis after the change names the key and who set it');
});

await test('the wait screen lists the steps with Cancel, which goes back to recording', async (open) => {
  const page = await open('take_stuck', 'poll_ms=100&slow_after_s=60&give_up_after_s=120');
  await page.waitFor(`document.querySelector('.wait-steps')`);
  assert.deepEqual(await text(page, '.wait-step'), ['Uploading', 'Finding notes', 'Matching key and bars', 'Writing feedback']);
  assert.equal(await count(page, '.wait-step.current[aria-current="step"]'), 1);
  await click(page, 'button.cancel-wait');
  await page.waitFor(`location.hash === '#/take'`);
});

await test('a mock analysis that never finishes shows Still working, then stops at the limit', async (open) => {
  const page = await open('take_stuck', 'poll_ms=100&slow_after_s=1&give_up_after_s=3');
  await page.waitFor(`document.querySelector('.slow-note')`, 5000);
  assert.deepEqual(await text(page, '.slow-note'), ['Still working - this can take a while for long takes']);
  await page.waitFor(`document.querySelector('.too-long')`, 8000);
  assert.deepEqual(await text(page, '.too-long .stage'), ['This is taking too long']);
  assert.deepEqual(await text(page, '.too-long button'), ['Try again', 'Record again']);
  assert.equal(await count(page, '#coach-root, .coach-sheet'), 0, 'no coach panel when processing gave up');
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

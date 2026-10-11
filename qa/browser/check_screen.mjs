// Loads one screen from scratch and records what happened: console output, failed requests, what rendered, whether it is blank.
import { storageKey } from './routes.mjs';

const RENDER_TIMEOUT_MS = 8000;
const SETTLE_MS = 2500; // lets polls (the mock answers after 150 ms, some screens poll) and late errors show up
export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// A document of the same origin as the app, to read and write its localStorage without loading the app.
const STORAGE_DOC = '/css/app.css';

export async function prepareStorage(page, origin, mode, stored) {
  await page.goto(`${origin}${STORAGE_DOC}`);
  const key = storageKey(mode);
  await page.eval(stored ? `localStorage.clear(); localStorage.setItem(${JSON.stringify(key)}, ${JSON.stringify(stored)})` : 'localStorage.clear()');
}

const readRenderedState = (root) => `(() => {
  const root = document.querySelector(${JSON.stringify(root)});
  const banner = document.getElementById('banner');
  const heading = root?.querySelector('h1, h2, h3');
  return {
    hash: location.hash,
    heading: heading ? heading.textContent.trim() : null,
    textSnippet: (root?.innerText ?? '').replace(/\\s+/g, ' ').trim().slice(0, 100),
    textLength: (root?.innerText ?? '').trim().length,
    elementCount: root ? root.querySelectorAll('*').length : 0,
    bannerText: banner && !banner.hidden ? banner.innerText.trim() : null,
  };
})()`;

const matchesAny = (patterns, text) => patterns.some((pattern) => pattern.test(text));

// Splits log lines into the ones the screen is meant to produce here (see `expected` in routes.mjs) and the rest.
export function splitExpected(lines, expectedPatterns) {
  const expected = lines.filter((line) => matchesAny(expectedPatterns, line));
  return { unexpected: lines.filter((line) => !expected.includes(line)), expected };
}

export async function checkScreen({ page, probe, origin, mode, spec }) {
  await prepareStorage(page, origin, mode, spec.stored);
  probe.reset();
  let loadError = null;
  try {
    await page.goto(`${origin}${spec.url}`);
    await page.waitFor(
      `(() => { const r = document.querySelector(${JSON.stringify(spec.root)}); const b = document.getElementById('banner'); return (r && r.children.length > 0) || (b && !b.hidden); })()`,
      RENDER_TIMEOUT_MS,
    );
  } catch (err) {
    loadError = err.message;
  }
  await sleep(SETTLE_MS);
  const rendered = await page.eval(readRenderedState(spec.root));
  const seen = probe.seen();
  const failures = splitExpected(seen.failedRequests, spec.expected);
  const errors = splitExpected(seen.consoleErrors, spec.expected);
  const blank = rendered.elementCount === 0 && rendered.bannerText === null;
  const requestedHash = spec.url.includes('#') ? spec.url.slice(spec.url.indexOf('#')) : null;
  return {
    name: spec.name,
    mode,
    url: spec.url,
    ...rendered,
    blank,
    redirectedTo: requestedHash && requestedHash !== rendered.hash ? rendered.hash : null, // the app moved us off the route we asked for
    loadError,
    consoleErrors: errors.unexpected,
    consoleWarnings: seen.consoleWarnings,
    exceptions: seen.exceptions,
    failedRequests: failures.unexpected,
    expectedFailedRequests: failures.expected,
    expectedConsoleErrors: errors.expected,
    cancelledRequests: seen.cancelledRequests,
    openResources: await probe.snapshotOpenResources(page),
  };
}

export const hasProblems = (record) => record.blank || record.loadError || record.redirectedTo || record.consoleErrors.length || record.consoleWarnings.length
  || record.exceptions.length || record.failedRequests.length;

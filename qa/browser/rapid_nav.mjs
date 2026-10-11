// Cycles through every hash route quickly, three times, in one page load, then looks for errors and for timers, microphone streams and
// audio contexts left open. A final move to #/start shows what is still open after leaving every screen.
import { prepareStorage, sleep } from './check_screen.mjs';

const CYCLES = 3;
const STEP_MS = 120;
const SETTLE_MS = 2500;

export async function rapidNavigation({ page, probe, origin, mode, hashes, stored }) {
  await prepareStorage(page, origin, mode, stored);
  await page.goto(`${origin}/${mode === 'mock' ? '?mock=1' : ''}#/take`);
  await page.waitFor(`document.getElementById('screen').children.length > 0`);
  await sleep(SETTLE_MS);
  probe.reset();
  for (let cycle = 0; cycle < CYCLES; cycle++) {
    for (const hash of hashes) {
      await page.eval(`location.hash = ${JSON.stringify(hash)}`);
      await sleep(STEP_MS);
    }
  }
  await sleep(SETTLE_MS);
  const afterCycles = { openResources: await probe.snapshotOpenResources(page), hash: await page.eval('location.hash'), seen: probe.seen() };
  await page.eval(`location.hash = '#/start'`);
  await sleep(SETTLE_MS);
  const afterStart = await probe.snapshotOpenResources(page);
  return { name: `rapid navigation (${CYCLES} cycles of ${hashes.length} routes)`, mode, ...afterCycles.seen, hash: afterCycles.hash,
    openResourcesAfterCycles: afterCycles.openResources, openResourcesAfterLeavingToStart: afterStart };
}

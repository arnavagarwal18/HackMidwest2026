// Takes the prototype screenshots into this folder: desktop and mobile (light and dark), a whole-page copy of each,
// and the mobile view with the coach bottom sheet open.
// Run: CHROME=<path to chrome> node frontend/dev/prototype/shoot.mjs        (results.html, v1: light and dark)
//      CHROME=<path to chrome> node frontend/dev/prototype/shoot.mjs v2     (results-v2.html: light only, palettes a, b and c)
//      CHROME=<path to chrome> node frontend/dev/prototype/shoot.mjs v2 b   (only palette b)
import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { launchChrome, openPage } from '../../tests/browser.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const IS_V2 = process.argv[2] === 'v2';
const PAGE_URL = pathToFileURL(join(HERE, IS_V2 ? 'results-v2.html' : 'results.html')).href;
const PALETTES = process.argv[3] ? [process.argv[3]] : ['a', 'b', 'c'];
// Each variant is one query string and the file-name prefix that goes with it.
const VARIANTS = IS_V2
  ? PALETTES.map((palette) => ({ query: `palette=${palette}`, prefix: `results-v2-${palette}`, theme: 'light' }))
  : ['light', 'dark'].map((theme) => ({ query: `theme=${theme}`, prefix: 'results', theme }));
const DESKTOP = { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false };
const MOBILE = { width: 390, height: 844, deviceScaleFactor: 1, mobile: true };
const OPEN_SHEET = `document.querySelector('#coach-open button').click()`;
const SHOTS = [
  { name: 'desktop', metrics: DESKTOP, whole: true },
  { name: 'mobile', metrics: MOBILE, whole: true },
  { name: 'mobile-coach', metrics: MOBILE, act: OPEN_SHEET },
];
const FILE_NAME = ({ prefix, theme }, name, suffix) => `${prefix}-${name}-${theme}${suffix}.png`;

const { stop, browserWsUrl } = await launchChrome();
try {
  for (const { name, metrics, whole, act } of SHOTS) {
    for (const variant of VARIANTS) {
      const page = await openPage(browserWsUrl);
      await page.send('Emulation.setDeviceMetricsOverride', metrics);
      await page.goto(`${PAGE_URL}?${variant.query}&bar=7`);
      await page.waitFor(`document.querySelector('.detail h3') !== null`);
      if (act) await page.eval(act);
      await new Promise((resolve) => setTimeout(resolve, 500)); // let the sheet finish sliding
      const shoot = async (suffix) => {
        const { data } = await page.send('Page.captureScreenshot', { format: 'png' });
        const file = join(HERE, FILE_NAME(variant, name, suffix));
        writeFileSync(file, Buffer.from(data, 'base64'));
        console.log(`${file} (console errors: ${page.errors.length})`);
      };
      await shoot('');
      if (whole) { // the fixed viewport shows only the top; the whole-page copy shows everything below it
        await page.send('Emulation.setDeviceMetricsOverride', { ...metrics, height: await page.eval('document.documentElement.scrollHeight') });
        await shoot('-full');
      }
      page.close();
    }
  }
} finally {
  stop();
}

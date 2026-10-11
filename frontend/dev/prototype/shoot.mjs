// Takes the four prototype screenshots into this folder.
// Run: CHROME=<path to chrome> node frontend/dev/prototype/shoot.mjs
import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { launchChrome, openPage } from '../../tests/browser.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const PAGE_URL = pathToFileURL(join(HERE, 'results.html')).href;
const SIZES = {
  desktop: { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false },
  mobile: { width: 390, height: 844, deviceScaleFactor: 1, mobile: true },
};

const { stop, browserWsUrl } = await launchChrome();
try {
  for (const [size, metrics] of Object.entries(SIZES)) {
    for (const theme of ['light', 'dark']) {
      const page = await openPage(browserWsUrl);
      await page.send('Emulation.setDeviceMetricsOverride', metrics);
      await page.goto(`${PAGE_URL}?theme=${theme}&bar=7`);
      await page.waitFor(`document.querySelector('.detail h3') !== null`);
      await new Promise((resolve) => setTimeout(resolve, 400));
      const { data } = await page.send('Page.captureScreenshot', { format: 'png' });
      const file = join(HERE, `results-${size}-${theme}.png`);
      writeFileSync(file, Buffer.from(data, 'base64'));
      console.log(`${file} (console errors: ${page.errors.length})`);
      { // the fixed viewport shows only the top; a second, whole-page shot shows the bars and the plan
        await page.send('Emulation.setDeviceMetricsOverride', { ...metrics, height: await page.eval('document.documentElement.scrollHeight') });
        const full = await page.send('Page.captureScreenshot', { format: 'png' });
        writeFileSync(join(HERE, `results-${size}-${theme}-full.png`), Buffer.from(full.data, 'base64'));
      }
      page.close();
    }
  }
} finally {
  stop();
}

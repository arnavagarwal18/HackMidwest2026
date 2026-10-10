// Test helpers: a static file server for frontend/, a headless Chrome, and a tiny DevTools-protocol page driver.
// Needs Node 22+ (global WebSocket) and Chrome; set CHROME to its binary if it is not in the usual place.
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.wav': 'audio/wav' };
const CHROME_CANDIDATES = [
  process.env.CHROME,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
].filter(Boolean);

export function startServer() {
  const server = createServer((req, res) => {
    const path = normalize(decodeURIComponent(new URL(req.url, 'http://x').pathname)).replace(/^(\.\.[/\\])+/, '');
    const file = join(FRONTEND_DIR, path === '/' ? 'index.html' : path);
    if (!file.startsWith(FRONTEND_DIR) || !existsSync(file)) {
      res.writeHead(404).end('not found');
      return;
    }
    const body = readFileSync(file);
    const range = /bytes=(\d+)-/.exec(req.headers.range ?? ''); // media seeking needs byte ranges
    if (range) {
      const start = Number(range[1]);
      res.writeHead(206, { 'Content-Type': TYPES[extname(file)], 'Content-Range': `bytes ${start}-${body.length - 1}/${body.length}`, 'Accept-Ranges': 'bytes' });
      res.end(body.subarray(start));
      return;
    }
    res.writeHead(200, { 'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream', 'Accept-Ranges': 'bytes' }).end(body);
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve({ server, origin: `http://127.0.0.1:${server.address().port}` })));
}

export async function launchChrome() {
  const binary = CHROME_CANDIDATES.find((candidate) => existsSync(candidate));
  if (!binary) throw new Error('Chrome not found; set the CHROME environment variable to its binary.');
  const profile = mkdtempSync('/tmp/results-test-');
  const chrome = spawn(binary, [
    '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', '--disable-gpu',
    '--disable-extensions', '--renderer-process-limit=1', '--js-flags=--max-old-space-size=256',
    '--autoplay-policy=no-user-gesture-required', '--window-size=1200,700', 'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  const wsUrl = await new Promise((resolve, reject) => {
    let log = '';
    chrome.stderr.on('data', (chunk) => {
      log += chunk;
      const found = /DevTools listening on (ws:\/\/\S+)/.exec(log);
      if (found) resolve(found[1]);
    });
    chrome.on('exit', (code) => reject(new Error(`Chrome exited early (${code}):\n${log}`)));
  });
  const stop = () => { // ends this Chrome (we started it, by its child handle) and removes its profile
    chrome.kill();
    try {
      rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }); // Chrome may still be writing as it exits
    } catch (err) { // a leftover temp folder must not hide the test results
      console.warn(`Could not remove the Chrome profile ${profile} (${err.code}); delete it by hand.`);
    }
  };
  return { stop, browserWsUrl: wsUrl };
}

// One browser tab. page.errors collects console errors and uncaught exceptions.
export async function openPage(browserWsUrl) {
  const port = new URL(browserWsUrl).port;
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let nextId = 0;
  const pending = new Map();
  const errors = [];
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message)); else resolve(message.result);
    } else if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') {
      errors.push(`console.error: ${message.params.args.map((a) => a.value ?? a.description).join(' ')}`);
    } else if (message.method === 'Runtime.exceptionThrown') {
      errors.push(`exception: ${message.params.exceptionDetails.exception?.description ?? message.params.exceptionDetails.text}`);
    } else if (message.method === 'Log.entryAdded' && message.params.entry.level === 'error') {
      errors.push(`log: ${message.params.entry.text} ${message.params.entry.url ?? ''}`);
    }
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
  await Promise.all([send('Runtime.enable'), send('Log.enable'), send('Page.enable')]);

  const page = {
    errors,
    async goto(url) {
      await send('Page.navigate', { url });
      await page.waitFor('document.readyState === "complete"');
    },
    async eval(expression) {
      const { result, exceptionDetails } = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
      if (exceptionDetails) throw new Error(`Page evaluation failed: ${exceptionDetails.exception?.description ?? exceptionDetails.text}\n${expression}`);
      return result.value;
    },
    async waitFor(expression, timeoutMs = 15000) {
      const deadline = Date.now() + timeoutMs;
      for (;;) {
        let value;
        try { value = await page.eval(expression); } catch { value = false; } // page may be mid-navigation
        if (value) return value;
        if (Date.now() > deadline) throw new Error(`Timed out after ${timeoutMs} ms waiting for: ${expression}`);
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
    },
    close: () => socket.close(),
  };
  return page;
}

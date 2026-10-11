// A second DevTools connection to a page's tab, so we can see more than frontend/tests/browser.mjs reports: console warnings, failed and
// 4xx/5xx requests, and (through a script run before the app's own) the timers, microphone streams and audio contexts it leaves open.

// Runs in the page before any app script. Wraps the timer and media entry points to keep a count of what is still open.
const TRACKING_SCRIPT = `(() => {
  const open = { intervals: new Set(), timeouts: new Set(), streams: [], audioContexts: [] };
  window.__qa = open;
  const { setInterval: realSetInterval, clearInterval: realClearInterval, setTimeout: realSetTimeout, clearTimeout: realClearTimeout } = window;
  window.setInterval = (fn, ms, ...args) => { const id = realSetInterval(fn, ms, ...args); open.intervals.add(id); return id; };
  window.clearInterval = (id) => { open.intervals.delete(id); realClearInterval(id); };
  window.setTimeout = (fn, ms, ...args) => {
    const id = realSetTimeout((...a) => { open.timeouts.delete(id); return fn(...a); }, ms, ...args);
    open.timeouts.add(id);
    return id;
  };
  window.clearTimeout = (id) => { open.timeouts.delete(id); realClearTimeout(id); };
  const realGetUserMedia = navigator.mediaDevices?.getUserMedia?.bind(navigator.mediaDevices);
  if (realGetUserMedia) navigator.mediaDevices.getUserMedia = async (constraints) => { const s = await realGetUserMedia(constraints); open.streams.push(s); return s; };
  const RealAudioContext = window.AudioContext;
  if (RealAudioContext) {
    window.AudioContext = function (...args) { const ctx = new RealAudioContext(...args); open.audioContexts.push(ctx); return ctx; };
    window.AudioContext.prototype = RealAudioContext.prototype;
  }
})()`;

const SNAPSHOT_EXPRESSION = `(() => {
  const open = window.__qa;
  if (!open) return null;
  return {
    intervals: open.intervals.size,
    pendingTimeouts: open.timeouts.size,
    liveMicTracks: open.streams.flatMap((s) => s.getTracks()).filter((t) => t.readyState === 'live').length,
    openAudioContexts: open.audioContexts.filter((c) => c.state !== 'closed').length,
    playingMedia: [...document.querySelectorAll('audio,video')].filter((m) => !m.paused).length,
  };
})()`;

const where = (frame) => (frame ? ` (${frame.url.replace(/^https?:\/\/[^/]+\//, '')}:${frame.lineNumber + 1})` : '');
const describeArgs = (args) => args.map((a) => a.value ?? a.description ?? a.type).join(' ');

async function findTargetByTitle(port, title) {
  for (let attempt = 0; attempt < 40; attempt++) {
    const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
    const found = targets.find((t) => t.type === 'page' && t.title === title);
    if (found) return found;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error(`Could not find the page's DevTools target by its title ${title}.`);
}

// Finds the tab by giving it a unique title, then listens to it. Call before the first navigation of the tab.
export async function attachProbe(browserWsUrl, page) {
  const port = new URL(browserWsUrl).port;
  const title = `qa-probe-${Date.now()}`;
  await page.eval(`document.title = ${JSON.stringify(title)}`);
  const target = await findTargetByTitle(port, title);
  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = () => reject(new Error('DevTools probe connection failed.')); });

  let nextId = 0;
  const pending = new Map();
  const probeFailures = []; // the probe itself broke: what it reports can no longer be trusted, so these count as exceptions
  let closedOnPurpose = false;
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { method, resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
  socket.onerror = () => probeFailures.push('[probe] DevTools probe connection error');
  socket.onclose = () => {
    if (!closedOnPurpose) probeFailures.push('[probe] DevTools probe connection closed unexpectedly; later results are incomplete');
    pending.forEach(({ method, reject }) => reject(new Error(`DevTools probe closed before ${method} was answered.`)));
    pending.clear();
  };

  let seen = empty();
  const urls = new Map();
  const ignored = new Set();
  function empty() {
    return { consoleErrors: [], consoleWarnings: [], exceptions: [], failedRequests: [], cancelledRequests: [] };
  }
  function recordEvent(method, params) {
    if (method === 'Runtime.consoleAPICalled' && (params.type === 'error' || params.type === 'assert')) {
      seen.consoleErrors.push(`${describeArgs(params.args)}${where(params.stackTrace?.callFrames[0])}`);
    } else if (method === 'Runtime.consoleAPICalled' && params.type === 'warning') {
      seen.consoleWarnings.push(`${describeArgs(params.args)}${where(params.stackTrace?.callFrames[0])}`);
    } else if (method === 'Runtime.exceptionThrown') {
      const details = params.exceptionDetails;
      seen.exceptions.push(`${details.exception?.description ?? details.text} (${(details.url ?? '').replace(/^https?:\/\/[^/]+\//, '')}:${(details.lineNumber ?? 0) + 1})`);
    } else if (method === 'Log.entryAdded' && params.entry.source !== 'network') {
      const list = params.entry.level === 'error' ? seen.consoleErrors : params.entry.level === 'warning' ? seen.consoleWarnings : null;
      list?.push(`[${params.entry.source}] ${params.entry.text}`);
    } else if (method === 'Network.requestWillBeSent') {
      if (params.request.url.endsWith('/favicon.ico')) { ignored.add(params.requestId); return; } // Chrome asks for it for the bare CSS page we use to reach localStorage
      urls.set(params.requestId, `${params.request.method} ${params.request.url.replace(/^https?:\/\/[^/]+/, '')}`);
    } else if (ignored.has(params?.requestId)) {
      return;
    } else if (method === 'Network.responseReceived' && params.response.status >= 400) {
      seen.failedRequests.push(`${urls.get(params.requestId) ?? params.response.url} -> ${params.response.status}`);
    } else if (method === 'Network.loadingFailed') {
      const entry = `${urls.get(params.requestId) ?? params.requestId} -> ${params.errorText}`;
      (params.canceled ? seen.cancelledRequests : seen.failedRequests).push(entry);
    }
  }
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.id !== undefined) { // the answer to one of our commands
      const call = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) call?.reject(new Error(`DevTools ${call.method} failed: ${message.error.message}`));
      else call?.resolve(message.result);
    } else {
      recordEvent(message.method, message.params);
    }
  };
  await Promise.all(['Runtime.enable', 'Log.enable', 'Network.enable', 'Page.enable'].map((method) => send(method)));
  await send('Page.addScriptToEvaluateOnNewDocument', { source: TRACKING_SCRIPT });

  return {
    reset: () => { seen = empty(); urls.clear(); },
    seen: () => ({ ...structuredClone(seen), exceptions: [...seen.exceptions, ...probeFailures] }),
    async snapshotOpenResources(inPage) {
      const snapshot = await inPage.eval(SNAPSHOT_EXPRESSION);
      if (!snapshot) throw new Error('The open-resource tracker is missing from the page, so leftover timers and streams cannot be checked.');
      return snapshot;
    },
    close: () => { closedOnPurpose = true; socket.close(); },
  };
}

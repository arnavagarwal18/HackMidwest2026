// A tiny fake browser for node tests: DOM nodes, window, an AudioContext, MediaRecorder and a mic. Logic tests only; no real browser.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND_DIR = join(dirname(fileURLToPath(import.meta.url)), '..');

export class FakeNode {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.attrs = {};
    this.listeners = {};
    this.ownText = '';
    this.className = '';
    this.hidden = false;
    this.disabled = false;
    const classes = new Set();
    this.classList = {
      add: (name) => classes.add(name),
      toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)),
      contains: (name) => classes.has(name) || this.className.split(' ').includes(name),
    };
  }

  get textContent() { return this.ownText + this.children.map((child) => child.textContent).join(''); }
  set textContent(text) { this.children = []; this.ownText = String(text); }
  append(...nodes) { nodes.forEach((n) => this.children.push(typeof n === 'string' ? Object.assign(new FakeNode('#text'), { ownText: n }) : n)); }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  remove() {}
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name] ?? null; }
  addEventListener(type, handler) { (this.listeners[type] ??= []).push(handler); }
  // Runs the click handlers (a disabled button ignores clicks) and resolves when the async ones are done.
  async click() { if (!this.disabled) await Promise.all((this.listeners.click ?? []).map((handler) => handler())); }
  all() { return this.children.flatMap((child) => [child, ...child.all()]); }
  find(predicate) { return this.all().filter(predicate); }
  button(text) { return this.find((n) => n.tagName === 'button' && (typeof text === 'string' ? n.textContent === text : text.test(n.textContent)))[0]; }
  hasText(text) { return this.textContent.includes(text); }
}

// Installs fake window/document/audio globals. `search` is the page's query string. Returns the pieces tests drive.
export function installFakeBrowser({ search = '?mock=1', host = '127.0.0.1:8000', micError = null, holdMic = false } = {}) {
  const realSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (fn, ms, ...args) => realSetTimeout(fn, Math.min(ms, 2), ...args); // a 3 s clip takes 2 ms
  const handlers = [];
  const banner = new FakeNode('div');
  banner.hidden = true;
  const head = new FakeNode('head');
  let grantMic = () => {};
  const micAnswer = holdMic ? new Promise((resolve) => { grantMic = resolve; }) : null; // the permission prompt, until grantMic()
  const env = { grantMic: () => grantMic(), banner, head, handlers, streams: [], clipsStarted: 0, clickTimes: [] };

  globalThis.document = {
    createElement: (tag) => new FakeNode(tag),
    createElementNS: (ns, tag) => new FakeNode(tag),
    getElementById: (id) => (id === 'banner' ? banner : null),
    querySelector: () => null,
    head,
  };
  globalThis.window = {
    location: { hash: '', search, host, protocol: 'http:' },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    addEventListener: (type, handler) => type === 'hashchange' && handlers.push(handler),
    AudioContext: class {
      constructor() { this.currentTime = 100.1; this.state = 'running'; this.destination = {}; env.audioContext = this; }
      async resume() {}
      createOscillator() { const osc = { frequency: {}, connect: (n) => n, start: (t) => env.clickTimes.push(t), stop() {} }; return osc; }
      createGain() { return { gain: { value: 0.5, setValueAtTime() {}, exponentialRampToValueAtTime() {}, linearRampToValueAtTime() {}, cancelScheduledValues() {} }, connect: (n) => n, disconnect() {} }; }
      createAnalyser() { return { fftSize: 0, getFloatTimeDomainData() {} }; }
      createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
    },
  };
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      mediaDevices: {
        async getUserMedia() {
          if (micAnswer) await micAnswer;
          if (micError) throw Object.assign(new Error('denied'), { name: micError });
          const tracks = [{ stopped: false, stop() { this.stopped = true; } }];
          const stream = { tracks, getTracks: () => tracks, getVideoTracks: () => [] };
          env.streams.push(stream);
          return stream;
        },
      },
    },
  });
  globalThis.requestAnimationFrame = () => 1;
  globalThis.cancelAnimationFrame = () => {};
  globalThis.MediaRecorder = class {
    static isTypeSupported() { return true; }
    constructor() { this.state = 'inactive'; this.mimeType = 'audio/webm'; this.listeners = {}; }
    addEventListener(type, handler) { (this.listeners[type] ??= []).push(handler); }
    emit(type, event = {}) { (this.listeners[type] ?? []).forEach((handler) => handler(event)); }
    start() { this.state = 'recording'; env.clipsStarted += 1; queueMicrotask(() => this.emit('start')); }
    stop() { this.state = 'inactive'; this.emit('dataavailable', { data: new Blob(['audio']) }); this.emit('stop'); }
  };
  globalThis.fetch = async (url) => {
    const body = readFileSync(join(FRONTEND_DIR, url), 'utf8');
    return { ok: true, status: 200, json: async () => JSON.parse(body) };
  };
  env.leave = () => handlers.splice(0).forEach((handler) => handler());
  env.restore = () => { globalThis.setTimeout = realSetTimeout; };
  return env;
}

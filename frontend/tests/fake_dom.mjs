// A tiny DOM stand-in for node tests of screens that only use createElement, append, replaceChildren, text and click handlers.
export class FakeNode {
  constructor(tag, doc) {
    this.tagName = tag.toUpperCase();
    this.doc = doc;
    this.children = [];
    this.parent = null;
    this.attributes = {};
    this.listeners = {};
    this.className = '';
    this.ownText = '';
    this.hidden = false;
    this.dataset = {};
  }

  set textContent(value) { this.ownText = String(value); this.children.forEach((c) => { c.parent = null; }); this.children = []; }
  get textContent() { return this.ownText + this.children.map((c) => c.textContent).join(''); }
  get isConnected() { let node = this; while (node.parent) node = node.parent; return node === this.doc.body; }
  setAttribute(name, value) { this.attributes[name] = value; }
  append(...nodes) {
    nodes.forEach((node) => {
      const child = typeof node === 'string' ? Object.assign(new FakeNode('#text', this.doc), { ownText: node }) : node;
      child.parent = this;
      this.children.push(child);
    });
  }
  replaceChildren(...nodes) { this.children.forEach((c) => { c.parent = null; }); this.children = []; this.append(...nodes); }
  contains(node) { return node === this || this.all().includes(node); }
  focus() { this.doc.activeElement = this; }
  remove() { if (this.parent) { this.parent.children = this.parent.children.filter((c) => c !== this); this.parent = null; } }
  addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn); }
  click() { (this.listeners.click ?? []).forEach((fn) => fn({ target: this })); }
  all() { return this.children.flatMap((c) => [c, ...c.all()]); }
  withClass(name) { return this.all().filter((n) => n.className.split(' ').includes(name)); }
  texts(name) { return this.withClass(name).map((n) => n.textContent); }
  button(label) { return this.all().find((n) => n.tagName === 'BUTTON' && n.textContent === label); }
}

class Target {
  constructor() { this.handlers = {}; }
  addEventListener(type, fn) { (this.handlers[type] ??= new Set()).add(fn); }
  removeEventListener(type, fn) { this.handlers[type]?.delete(fn); }
  count(type) { return this.handlers[type]?.size ?? 0; }
  dispatch(type, event = {}) { [...(this.handlers[type] ?? [])].forEach((fn) => fn(event)); }
}

// Installs globalThis.document and globalThis.window; returns { body, banner, document, window }.
export function installFakeDom() {
  const doc = Object.assign(new Target(), { body: null });
  doc.createElement = (tag) => new FakeNode(tag, doc);
  doc.body = doc.createElement('body');
  const banner = doc.createElement('div');
  banner.hidden = true;
  doc.body.append(banner);
  doc.head = doc.createElement('head');
  doc.querySelector = () => null; // no stylesheet is ever "already loaded"
  doc.getElementById = (id) => (id === 'banner' ? banner : null);
  const win = Object.assign(new Target(), { location: { search: '', hash: '' } });
  globalThis.document = doc;
  globalThis.window = win;
  return { body: doc.body, banner, document: doc, window: win };
}

export const space = (extra = {}) => ({ code: 'Space', repeat: false, target: null, preventDefault() {}, ...extra });
export const settle = () => new Promise((resolve) => setTimeout(resolve, 15));

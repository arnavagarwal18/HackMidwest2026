// Small DOM helpers shared by screens that build their own markup.

// element('p', 'Hello', 'muted', { id: 'x' }) -> <p class="muted" id="x">Hello</p>. Text is always set as text, never HTML.
export function element(tag, text = '', className = '', attributes = {}) {
  const el = document.createElement(tag);
  if (text) el.textContent = text;
  if (className) el.className = className;
  Object.entries(attributes).forEach(([name, value]) => el.setAttribute(name, value));
  return el;
}

export function button(label, onClick, className = '') {
  const el = element('button', label, className, { type: 'button' });
  el.addEventListener('click', onClick);
  return el;
}

export function link(label, href, className = '') {
  return element('a', label, className, { href });
}

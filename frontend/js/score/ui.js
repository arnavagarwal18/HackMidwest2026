// Small DOM helpers shared by the Start and Score screens.
import { reportError } from '../banner.js';

export function el(tag, { text, className, attrs = {}, children = [] } = {}) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  Object.entries(attrs).forEach(([name, value]) => node.setAttribute(name, value));
  node.append(...children);
  return node;
}

export function button(label, onClick, className) {
  const node = el('button', { text: label, className, attrs: { type: 'button' } });
  node.addEventListener('click', onClick);
  return node;
}

// The Start/Score styles live in their own file so they never collide with other screens' CSS.
export function loadScoreStyles() {
  const href = 'css/score.css';
  if (document.querySelector(`link[href="${href}"]`)) return;
  document.head.append(el('link', { attrs: { rel: 'stylesheet', href } }));
}

// Runs an action while `controls` are disabled. A failure goes to the red banner and the inputs stay as they are.
export async function runGuarded(controls, action) {
  controls.forEach((control) => { control.disabled = true; });
  try {
    return await action();
  } catch (err) {
    reportError(err);
    return undefined;
  } finally {
    controls.forEach((control) => { control.disabled = false; });
  }
}

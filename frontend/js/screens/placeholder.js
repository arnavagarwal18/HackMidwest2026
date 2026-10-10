// Shared placeholder body: a heading and the saved response of each API call the real screen will make.
import { api } from '../api.js';

function element(tag, text, className) {
  const el = document.createElement(tag);
  el.textContent = text;
  if (className) el.className = className;
  return el;
}

export async function renderPlaceholder(root, { title, description, calls }) {
  root.append(element('h1', title), element('p', description), element('p', 'Placeholder screen.', 'muted'));
  for (const [method, path] of calls) {
    const block = element('pre', 'Loading...', 'response');
    root.append(element('h2', `${method} ${path}`), block);
    const data = method === 'GET' ? await api.get(path) : await api.post(path);
    block.textContent = JSON.stringify(data, null, 2);
  }
}

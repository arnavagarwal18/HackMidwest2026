// Shared placeholder body: a heading and the saved response of each API call the real screen will make.
// calls: [{ label, run }] where run() returns the promise from an api.js function.
// Real screens replace this; it exists so the shell and mock mode can be walked end to end.

export function element(tag, text, className) {
  const el = document.createElement(tag);
  el.textContent = text;
  if (className) el.className = className;
  return el;
}

export async function renderPlaceholder(root, { title, description, calls }) {
  root.append(element('h1', title), element('p', description), element('p', 'Placeholder screen.', 'muted'));
  for (const { label, run } of calls) {
    const block = element('pre', 'Loading...', 'response');
    root.append(element('h2', label), block);
    block.textContent = JSON.stringify(await run(), null, 2);
  }
}

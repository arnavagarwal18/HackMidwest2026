// Hash router: maps #/route/params to a screen module in js/screens/.
import { clearBanner, reportError, showNotice } from './banner.js';
import { resumeSession } from './resume.js';

const ROUTES = [
  { pattern: '/start', screen: 'start' },
  { pattern: '/score', screen: 'score' },
  { pattern: '/calibrate', screen: 'calibrate' },
  { pattern: '/take', screen: 'take' },
  { pattern: '/results/:take', screen: 'results' },
  { pattern: '/exercise/:ex', screen: 'exercise' },
  { pattern: '/progress', screen: 'progress' },
  { pattern: '/trace/:fb', screen: 'trace' },
  { pattern: '/demo', screen: 'demo' }, // hidden: not in the nav (see screens/demo.js)
].map((route) => ({
  ...route,
  names: [...route.pattern.matchAll(/:(\w+)/g)].map((m) => m[1]),
  regex: new RegExp(`^${route.pattern.replace(/:\w+/g, '([^/]+)')}$`),
}));

export const DEFAULT_HASH = '#/start';
let renderToken = 0;

// Decodes the matched URL segments; a malformed one (e.g. a stray "%") is logged and gives null, like an unknown route.
function decodeParams(names, segments, hash) {
  try {
    return Object.fromEntries(names.map((name, i) => [name, decodeURIComponent(segments[i])]));
  } catch (err) {
    console.error(`Malformed URL hash "${hash}"; showing the start screen instead.`, err);
    return null;
  }
}

export function matchRoute(hash) {
  const path = hash.replace(/^#/, '');
  for (const route of ROUTES) {
    const found = route.regex.exec(path);
    if (found) {
      const params = decodeParams(route.names, found.slice(1), hash);
      return params && { screen: route.screen, params };
    }
  }
  return null;
}

async function renderCurrent() {
  const token = ++renderToken;
  const root = document.getElementById('screen');
  const match = matchRoute(window.location.hash);
  if (!match) {
    window.location.hash = DEFAULT_HASH;
    return;
  }
  clearBanner();
  document.querySelectorAll('nav a').forEach((link) => {
    link.classList.toggle('current', link.getAttribute('href').split('/')[1] === window.location.hash.split('/')[1]);
  });
  root.className = ''; // screens may set their own layout class
  root.replaceChildren();
  try {
    const screen = await import(`./screens/${match.screen}.js`);
    if (token !== renderToken) return; // the user already moved on
    // isCurrent() lets a screen drop the rest of its render when the learner moved on while it waited for the server.
    await screen.render(root, match.params, () => token === renderToken);
  } catch (err) {
    if (token !== renderToken) return;
    reportError(err);
  }
}

export async function start() {
  const { hash, notice, error } = await resumeSession(window.location.hash);
  if (hash !== window.location.hash) {
    // replaceState does not fire hashchange, so the first render happens exactly once below.
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${hash}`);
  }
  window.addEventListener('hashchange', renderCurrent);
  await renderCurrent();
  if (notice) showNotice(notice);
  if (error) reportError(error);
}

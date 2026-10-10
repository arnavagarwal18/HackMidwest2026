// Requests that found the server down wait here together: one Retry press repeats all of them,
// and leaving the screen cancels them all, so no caller is left waiting forever.
import { showUnreachable, clearBanner } from './banner.js';
import { RequestCancelled } from './request_cancelled.js';

const waiting = new Set(); // entries of { retry, cancel }
let listeningForNavigation = false;

// retry() repeats the request once and returns true when it settled (so it leaves the queue),
// false when the server was still unreachable. cancel(err) rejects the waiting caller.
export function waitInQueue(retry, cancel) {
  listenForNavigation();
  waiting.add({ retry, cancel });
  showUnreachable(retryAll);
}

async function retryAll() {
  await Promise.all([...waiting].map(retryEntry));
  if (waiting.size === 0) clearBanner();
}

async function retryEntry(entry) {
  try {
    if (await entry.retry()) waiting.delete(entry);
  } catch (err) {
    console.error('Retrying a request failed unexpectedly:', err); // retry() settles its caller; this is a bug guard
    waiting.delete(entry);
    entry.cancel(err);
  }
}

function cancelAll() {
  const entries = [...waiting];
  waiting.clear();
  entries.forEach((entry) => entry.cancel(new RequestCancelled()));
  clearBanner(); // its Retry button has nothing left to repeat
}

function listenForNavigation() {
  if (listeningForNavigation) return;
  listeningForNavigation = true;
  window.addEventListener('hashchange', cancelAll);
}

// The banner strip at the top of every screen: red errors, notices, and the server-down banner.
const UNREACHABLE_TEXT = "Can't reach the app server on this laptop";

function bannerEl() {
  return document.getElementById('banner');
}

function show(kind, text, retryHandler) {
  const el = bannerEl();
  el.className = `banner banner-${kind}`;
  el.hidden = false;
  el.replaceChildren();
  const message = document.createElement('span');
  message.textContent = text;
  el.append(message);
  if (retryHandler) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = 'Retry';
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        await retryHandler();
      } finally {
        button.disabled = false;
      }
    });
    el.append(button);
  }
}

export function clearBanner() {
  const el = bannerEl();
  el.hidden = true;
  el.replaceChildren();
}

export function showNotice(text) {
  show('notice', text);
}

export function showError(text) {
  show('error', text);
}

// retryHandler runs once per Retry press; it never runs by itself.
export function showUnreachable(retryHandler) {
  show('error', UNREACHABLE_TEXT, retryHandler);
}

// Used by screens and the router for anything a request threw.
export function reportError(err) {
  console.error('Request failed:', err);
  showError(err && err.message ? err.message : 'Something went wrong. Please try again.');
}

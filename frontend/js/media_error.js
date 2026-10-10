// What to tell the learner when the mic or camera cannot be opened, and a reusable message block.
export const HELP_LINE = 'Allow it in Chrome: click the camera icon in the address bar';

export class MediaAccessError extends Error {
  // device: 'mic' | 'camera'; reason: 'blocked' | 'missing' | 'busy' | 'unknown'
  constructor(device, reason, cause) {
    super(MediaAccessError.describe(device, reason));
    this.name = 'MediaAccessError';
    this.device = device;
    this.reason = reason;
    this.cause = cause;
  }

  static describe(device, reason) {
    if (reason === 'blocked') return `Chrome is blocking the ${device}. The app cannot record without it.`;
    if (reason === 'missing') return `No ${device} was found on this computer.`;
    if (reason === 'busy') return `The ${device} could not be started. Another app may be using it.`;
    return `The ${device} could not be opened.`;
  }
}

const REASONS = { NotAllowedError: 'blocked', SecurityError: 'blocked', NotFoundError: 'missing', OverconstrainedError: 'missing', NotReadableError: 'busy', AbortError: 'busy' };

export function toMediaAccessError(device, err) {
  console.error(`Opening the ${device} failed:`, err);
  return new MediaAccessError(device, REASONS[err && err.name] || 'unknown', err);
}

// Fills `container` with: the message, the help line (when it is a permission problem), Try again and Upload.
// Nothing retries by itself: onTryAgain runs only when the learner presses the button.
// onUpload is optional; leave it out to hide the Upload option. Returns the block so a screen can remove it.
export function renderMediaError(container, error, { onTryAgain, onUpload }) {
  const block = document.createElement('div');
  block.className = 'media-error';
  block.setAttribute('role', 'alert');
  const lines = [error.message];
  if (error.reason === 'blocked') lines.push(HELP_LINE);
  lines.forEach((text) => {
    const p = document.createElement('p');
    p.textContent = text;
    block.append(p);
  });
  const tryAgain = document.createElement('button');
  tryAgain.type = 'button';
  tryAgain.textContent = 'Try again';
  tryAgain.addEventListener('click', () => onTryAgain());
  block.append(tryAgain);
  if (onUpload) {
    const upload = document.createElement('button');
    upload.type = 'button';
    upload.textContent = 'Upload a recording instead';
    upload.addEventListener('click', () => onUpload());
    block.append(upload);
  }
  container.replaceChildren(block);
  return block;
}

// What to tell the learner when the mic or camera cannot be opened, and a reusable message block.
export const HELP_LINES = [
  'To allow it on iPhone or iPad: open Settings, then Safari, then Camera and Microphone, choose Ask or Allow, and reload this page.',
  'In Safari on a Mac: choose Safari, then Settings, then Websites, then Microphone or Camera, and set this site to Allow.',
  'In Chrome: click the camera icon in the address bar and allow it.',
];

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
    if (reason === 'blocked') return `This page is not allowed to use the ${device}, so the app cannot record.`;
    if (reason === 'missing') return `No ${device} was found. Check that one is connected and turned on.`;
    if (reason === 'busy') return `Another app may be using the ${device}. Close it (video calls and other tabs too), then try again.`;
    return `The ${device} could not be opened.`;
  }
}

const REASONS = { NotAllowedError: 'blocked', SecurityError: 'blocked', NotFoundError: 'missing', OverconstrainedError: 'missing', NotReadableError: 'busy', AbortError: 'busy' };

// Blocked, missing and busy devices are shown to the learner as a friendly message, so they are logged as warnings;
// only an unexpected failure is an error in the console.
export function toMediaAccessError(device, err) {
  const reason = REASONS[err && err.name] || 'unknown';
  (reason === 'unknown' ? console.error : console.warn)(`Opening the ${device} failed (${reason}):`, err);
  return new MediaAccessError(device, reason, err);
}

// Fills `container` with: the message, the help lines (when it is a permission problem), Try again and Upload.
// Nothing retries by itself: onTryAgain runs only when the learner presses the button.
// onUpload is optional; leave it out to hide the Upload option. Returns the block so a screen can remove it.
export function renderMediaError(container, error, { onTryAgain, onUpload }) {
  const block = document.createElement('div');
  block.className = 'media-error';
  block.setAttribute('role', 'alert');
  const lines = [error.message];
  if (error.reason === 'blocked') lines.push(...HELP_LINES);
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

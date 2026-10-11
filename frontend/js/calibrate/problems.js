// Turns a 422 calibration_failed answer into the list of notes to play again.
export const PROBLEM_TEXT = { not_heard: 'not heard', off_pitch: 'off pitch', too_noisy: 'too noisy' };

export const problemText = (code) => PROBLEM_TEXT[code] ?? String(code ?? 'problem').replace(/_/g, ' ');

// err.details.notes is [{ asked, problem, cents }]. Returns [{ index, asked, text }] for the notes we asked for,
// or [] when the error is not a calibration_failed answer (the screen then shows err.message only).
export function failuresFromError(err, notes) {
  if (!err || err.code !== 'calibration_failed' || !Array.isArray(err.details?.notes)) return [];
  return err.details.notes
    .map((item) => ({ index: notes.findIndex((note) => note.name === item.asked), asked: item.asked, text: problemText(item.problem) }))
    .filter((failure) => failure.index >= 0);
}

// Fills `container` with one row per failing note: "A4: not heard" and a Retry button for that note.
// Returns the Retry buttons so the screen can disable them while a recording or a send is running.
export function renderFailureList(container, failures, onRetry) {
  container.replaceChildren();
  if (!failures.length) return [];
  const title = document.createElement('p');
  title.textContent = 'These notes need to be played again:';
  const list = document.createElement('ul');
  list.className = 'calibrate-failures';
  const buttons = failures.map((failure) => {
    const item = document.createElement('li');
    const label = document.createElement('span');
    label.textContent = `${failure.asked}: ${failure.text}`;
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.textContent = 'Retry';
    retry.setAttribute('aria-label', `Retry ${failure.asked}`);
    retry.addEventListener('click', () => onRetry(failure.index));
    item.append(label, retry);
    list.append(item);
    return retry;
  });
  container.append(title, list);
  return buttons;
}

// A 422/415 that names one of our clips (audio_unreadable, a clip too long, a missing part...) means that recording is bad:
// sending it again can only fail the same way. Returns { field, kind, index, label, message } for the clip to record again, or null.
const CLIP_FIELD = /\b(ref_[0-2]|inst_[0-2]|click)\b/;
const REJECTED_CLIP_STATUSES = [415, 422];

export function clipProblemFromError(err, notes) {
  if (!err || err.code === 'calibration_failed' || !REJECTED_CLIP_STATUSES.includes(err.status)) return null;
  const field = CLIP_FIELD.exec(err.message ?? '')?.[1];
  if (!field) return null;
  const [kind, indexText] = field.split('_');
  const index = Number(indexText);
  const note = notes[index];
  if (kind !== 'click' && !note) return null;
  const labels = { click: 'the delay test', ref: `${note?.name} on your other device`, inst: `${note?.name} on your instrument` };
  const label = labels[kind];
  return { field, kind, index, label, message: `We couldn't use the recording of ${label}. Please record it again.` };
}

// After a send that failed for a reason the recordings did not cause (server down, 5xx, timeout): the clips are kept,
// so one press re-sends them. Returns the Try again button so the screen can disable it while a send is running.
export function renderSendRetry(container, onTryAgain) {
  const note = document.createElement('p');
  note.textContent = 'Your recordings are kept, so there is no need to record again.';
  const tryAgain = document.createElement('button');
  tryAgain.type = 'button';
  tryAgain.textContent = 'Try again';
  tryAgain.addEventListener('click', () => onTryAgain());
  container.replaceChildren(note, tryAgain);
  return tryAgain;
}

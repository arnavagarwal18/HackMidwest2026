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
export function renderFailureList(container, failures, onRetry) {
  container.replaceChildren();
  if (!failures.length) return;
  const title = document.createElement('p');
  title.textContent = 'These notes need to be played again:';
  const list = document.createElement('ul');
  list.className = 'calibrate-failures';
  failures.forEach((failure) => {
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
  });
  container.append(title, list);
}

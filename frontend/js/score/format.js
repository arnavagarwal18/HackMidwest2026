// Plain-language text for the score screen. The DoubtfulBar shape is not pinned yet (LLD-1 question), so
// everything that reads its fields lives in formatDoubtfulBar.

// Mock and back end send { bar, homr_text, reader_text }; reader_text is null when the second reader gave nothing.
export function formatDoubtfulBar(doubtful) {
  const second = doubtful.reader_text ?? 'no second reading';
  return `Bar ${doubtful.bar} - scan read: ${doubtful.homr_text}; second reading: ${second}`;
}

const SCAN_ERROR_MESSAGES = {
  scan_failed: "We couldn't read this photo. Try another photo, or choose a file instead.",
  no_notes: 'No notes found in this photo. Is the whole staff inside the crop?',
  scan_timeout: 'Reading the photo took too long. Try another photo, or choose a file instead.',
};
const UNKNOWN_SCAN_ERROR = 'The scan did not work. Try another photo, or choose a file instead.';

// The back end sends its own wording as score_error_message; the table is the fallback.
export function scanErrorMessage(status) {
  return status.score_error_message || SCAN_ERROR_MESSAGES[status.score_error] || UNKNOWN_SCAN_ERROR;
}

export const SLOW_MESSAGE = 'Still working - this can take a while';
export const TOO_LONG_MESSAGE = 'This is taking too long';

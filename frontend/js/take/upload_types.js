// The file types POST /sessions/{id}/takes accepts (backend/app/takes/validation.py ACCEPTED_TYPES and its aliases).
// Anything else, such as mp3 or m4a, gets a 415, so the picker is limited to these and a file of another type is
// refused before it is uploaded.
const ACCEPTED_TYPES = {
  'audio/webm': 'webm',
  'audio/wav': 'wav',
  'audio/ogg': 'ogg',
  'video/webm': 'webm',
  'video/mp4': 'mp4',
  'video/quicktime': 'mov',
};
const TYPE_ALIASES = { 'audio/x-wav': 'audio/wav', 'audio/wave': 'audio/wav' };

const EXTENSIONS = [...new Set(Object.values(ACCEPTED_TYPES))].map((extension) => `.${extension}`);

// The value of the file input's `accept` attribute: the exact types, plus their extensions for pickers that match by name.
export const UPLOAD_ACCEPT = [...Object.keys(ACCEPTED_TYPES), ...EXTENSIONS].join(',');

export const UNSUPPORTED_FILE_TEXT = "That file type isn't supported. Upload a WAV, WebM, OGG, MP4 or MOV recording (MP3 and M4A are not accepted).";

const normalise = (type) => {
  const base = (type || '').split(';')[0].trim().toLowerCase();
  return TYPE_ALIASES[base] ?? base;
};

// A message the learner can act on when `file` would be refused by the server, or null when it can be sent.
export const uploadTypeProblem = (file) => (normalise(file.type) in ACCEPTED_TYPES ? null : UNSUPPORTED_FILE_TEXT);

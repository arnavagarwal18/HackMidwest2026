# LLD-1 Score ingest - change 4: File upload, built-in pieces, confirm and score routes

Approved design LLD-1, proposed change 4. Text as given to the coder.

## Shared

- JSON in and out unless stated; uploads are multipart/form-data with the file in field 'file'.
- Errors: HTTP 4xx/5xx with body `{ error: { code, message } }` (message in plain words a learner can read).
  Codes: 404 session_not_found, 413 file_too_large, 415 unsupported_type, 409 wrong_state,
  422 bad_request, 500 storage_error.
- Session score_status: 'none' | 'scanning' | 'scanned' | 'failed' | 'confirmed'.

## Routes

- **POST /sessions/{id}/score/file**. Request: multipart 'file' (.musicxml, .xml, .mxl, .mid or .midi,
  at most 5 MB), or JSON `{ builtin: piece_id }`. Response 200
  `{ score_status: 'scanned', bars, doubtful_bars: [], double_checked: false, warnings }`.
  Errors: 404, 413, 415, 409 wrong_state (confirmed or scanning), 422 bad_score_file (can't be parsed or
  has no notes), 404 builtin_not_found. Saves score.json in the session folder; a new upload before
  confirming replaces the previous result.
- **GET /builtins**: 200 `[ { piece_id, title, instrument, bars } ]`, filtered by `?instrument=` if given.
- **POST /sessions/{id}/score/confirm**. Request `{}`. Response 200
  `{ score_status: 'confirmed', bars, tempo_bpm, time_signature }`. Errors: 404, 409 wrong_state unless
  score_status is 'scanned'. After confirm the score is read-only for the session.
- **GET /sessions/{id}/score**: the MusicXML text (content type `application/vnd.recordare.musicxml+xml`);
  with `?format=json`, the score model. 409 wrong_state if there is no score yet. (Keep the original
  upload / built-in MusicXML in the session folder so this can be served; for MIDI uploads, export
  MusicXML via music21.)

## Built-in pieces

`backend/app/score/builtins/{piece_id}.musicxml` plus `builtins.json` listing
`{ piece_id, title, instrument, bars }`. 4 short public-domain single-line melodies: Ode to Joy and
Twinkle Twinkle for violin, and the same two for B-flat trumpet with a MusicXML transpose chromatic -2
(written pitch stored). Written by us (generated with music21 once, .musicxml files committed); a
teammate may replace them later.

## Errors

- Unparseable file or no notes: 422 bad_score_file, nothing saved, message
  'This file couldn't be read as sheet music.'
- Wrong type or too big: 415 or 413 with the allowed types and size in the message.
- Session folder can't be written: 500 storage_error, message 'The app couldn't save your work. Tell the
  team.', logged with the path.
- Several parts or chords: not an error, warnings returned.

## Tests (from the test plan)

Each built-in parses to its listed bar count and expected first note; trumpet built-in gives
written_transpose_semitones -2; a .txt upload returns 415; a 6 MB MusicXML returns 413; broken XML
returns 422 bad_score_file; unknown builtin returns 404 builtin_not_found; confirm before any score
returns 409 wrong_state; storage failure (session folder unwritable) returns 500 storage_error in the
shared shape; plus one happy path: builtin -> confirm -> GET ?format=json.

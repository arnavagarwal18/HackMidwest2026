# testdata/calibration

Tuning/calibration clips: the three reference notes played at the start of a recording, as the app's video calibration expects.

- `jameson_tuning_calibration.mp4`: 13.42 s, 1920x1080 @ 23.97 fps h264 + AAC 44.1 kHz stereo 128 kb/s (3.4 MB, original file, not re-encoded). Jameson on trumpet, 2026-10-11 (original name "Tuning calibration C G C.mp4"). The audio is meaningful.
  - Contents: written C4, G4, C5 on trumpet, i.e. concert Bb3, F4, Bb4 (the app's trumpet reference notes), each held about 1.2 s with silence between. There is nothing after the third note: the clip ends at 13.42 s.
  - Notes found (pYIN, concert pitch):

    | Asked | Start - end (s) | Measured Hz | Cents off |
    | --- | --- | --- | --- |
    | Bb3 | 4.20 - 5.36 | 231.33 | -13.05 |
    | F4 | 8.31 - 9.48 | 348.73 | -2.45 |
    | Bb4 | 11.96 - 13.38 | 464.83 | -4.96 |

    Short (about 0.1 s) pitched blips at 0.1-1.2 s, 5.7 s and 10.3 s are ignored by the rule (shorter than 0.5 s).
  - Expected calibration result (`calibrate_from_audio(audio, "trumpet")`, rule: steady pitch for at least 0.5 s within 50 cents of each asked note, in order, within the first 20 s): found, `calib_end_s` 13.382. Profile: source `video`, calibrated, `pitch_offset_cents` -6.82, `noise_floor_db` -78.53, `pickup_db` low -3.94 / mid 0 / high +0.18, `latency_ms` 0, no problem on any note.
  - Transcription after `calib_end_s` is not possible with this clip (both the calibrated and the default profile raise `NoNotesHeard`: "The recording has no sound after the calibration part."). To compare calibrated and default transcription, use a take that has playing after its calibration notes.

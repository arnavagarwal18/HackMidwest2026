# Form analysis runs on real clips

## puffed_then_not.mp4 (cheekPuff measurement, 2026-10-11)

Clip: `testdata/form/puffed_then_not.mp4`, 14.0 s, 1920x1080, 30 fps. The owner says the first half is played with puffed cheeks, the second half without.
Run: `backend/.venv/Scripts/python backend/scripts/dump_face_readings.py testdata/form/puffed_then_not.mp4 testdata/form/puffed_then_not_face.csv --split-s 7`
(per-frame values in `testdata/form/puffed_then_not_face.csv`; 140 frames at 10 fps; FACE_ENABLED on; notes transcribed from the clip's audio).

| Item | Result |
|---|---|
| Audio | Sound only from about 2 s to 7 s; digital silence from about 8.5 s to the end. Transcribed notes: 4, 1.08 s to 7.89 s. So only 48 frames of the first half and 4 of the second fall inside a note. |
| Detected view | `front` (view_ratio 1.66), but the picture is a side / three-quarter profile with the far cheek hidden: view detection is wrong on this clip (not changed). |
| face_quality | 1.0 inside notes (52/52 frames); 0.886 over all frames (no face on 16 of 140 frames, mostly 9.8 to 12.0 s). |
| `trumpet_cheeks_puffed` | Does not fire (no flag at all). |
| `trumpet_smile_embouchure` | Does not fire: smile above 0.5 inside notes only at 1.1 to 1.3 s (under the 1 s minimum episode). |

cheekPuff and smile (blendshape scores), split at 7 s:

| Frames | n with face | cheekPuff median | cheekPuff p90 | cheekPuff max | smile median | smile p90 | smile max |
|---|---|---|---|---|---|---|---|
| First half, all frames (0 to 7 s) | 67/70 | 0.000 | 0.000 | 0.000 | 0.000 | 0.591 | 0.699 |
| Second half, all frames (7 to 14 s) | 57/70 | 0.000 | 0.000 | 0.001 | 0.063 | 0.638 | 0.781 |
| First half, inside notes | 48/48 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.598 |
| Second half, inside notes | 4/4 | 0.000 | 0.000 | 0.000 | 0.032 | 0.052 | 0.052 |

Checked also on 28 frames (every 0.5 s) with the whole frame, a top-left crop of the player, and that crop mirrored: cheekPuff never went above 0.001 in any of them. The viewer-side cheek looked full but not clearly puffed in two frames I looked at (a picture model, so weak evidence); I did not verify the owner's claim independently.

Where the change happens: cheekPuff does not change anywhere, so there is no change point in this signal. The audio changes at about 7 s (playing stops), which is the only boundary visible in the data; whether the owner's halves are 0 to 7 s and 7 to 14 s is not confirmed.

Does 0.45 separate the halves? No, and no threshold can: both halves read 0.000 to 0.001, so there is nothing to place a threshold between. The Face Landmarker's `cheekPuff` does not respond to this player's puffed cheeks (three-quarter profile, trumpet mouthpiece over the lips, far cheek hidden). The rule `trumpet_cheeks_puffed` would not catch this case with its current measure. Inference, not verified: puffed trumpet cheeks need a different signal (for example the cheek width in the landmark mesh, or a camera pointing at the player's face from the front) or a clip filmed from the front.

Also noted, not changed: smile reads above 0.5 on the face before and after playing (0.7 to 2.0 s, 8.1 to 8.8 s), so the smile rule relies on the note gate to avoid false flags.

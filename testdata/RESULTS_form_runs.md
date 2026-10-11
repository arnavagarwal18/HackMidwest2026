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

## cheek_modulation.mp4 (cheekPuff and cheek-width measurement, 2026-10-11)

Clip: `testdata/form/cheek_modulation.mp4`, 26 s, 1920x1080, 30 fps, 39 MB. It is a screen recording of an orchestra performance with a sheet-music band across the top that hides the top of the player's head; the player is mostly facing the camera, head tipped down, mouthpiece on the lips, valve hand and trumpet across the lower face. The owner says the player alternates puffed and not-puffed cheeks.
Run: `backend/.venv/Scripts/python backend/scripts/dump_face_readings.py testdata/form/cheek_modulation.mp4 testdata/form/cheek_modulation_face.csv --cheek-width` (new `--cheek-width` column: Face Mesh landmarks 234-454 distance / landmarks 33-263 distance, in the face crop's pixels; `--split-s` is now optional). FACE_ENABLED on, 70 notes transcribed.

| Item | Result |
|---|---|
| Detected view | `front` (view_ratio 2.03). |
| face_quality | 0.10 inside notes, 0.149 over all frames (the app's pose-based crop gave a face on only 39 of 261 frames, mostly 19 to 26 s). |
| Face rules | Both skipped as `not_visible`, so `trumpet_cheeks_puffed` cannot fire. |
| Other flags | slouching, shoulders_raised, trumpet_head_down (not examined). |

Independent run on a fixed crop around the head (x 480-1200, y 0-700 px, every 3rd frame, 261 frames; `testdata/form/cheek_modulation_fixed_crop.csv`, ad-hoc script not committed): the Face Landmarker found a face in 251 of 261 frames. So the face is trackable here; the app's crop (from the pose nose and shoulders) loses it. This is the reason for the low face_quality.

| Signal (fixed crop, 251 frames) | min | median | p90 | max |
|---|---|---|---|---|
| cheekPuff | 0.000004 | 0.00005 | 0.0003 | 0.0010 |
| cheek width / inter-eye | 1.412 | 1.510 | 1.575 | 1.748 |

cheekPuff is never above 0.001, so it has no period above 0.1 and does not rise and fall. (The app-crop run, 39 frames, gives the same: max 0.001.)
Cheek width stays within about 1.41 to 1.62 (p10 1.47, p90 1.575, per-second means 1.46 to 1.58) with one spike to 1.75 at about 22.2 s; it shows no regular alternation over the 26 s. Its spread (about +-5% of the median) is no larger than head tilt and head turn would produce on their own.

Visual check (picture model, weak evidence; I looked at 8 face crops at 0.5, 1.0, 9.0, 10.0, 13.5, 14.0, 17.5 and 22.2 s, plus 4 whole frames): all looked normal to slightly full; only 22.2 s (the width spike) was called "somewhat fuller", with low confidence. I could not confirm the owner's alternation from the frames, and a picture model cannot separate puffed from normal reliably at this size.

- Does cheekPuff track the puffing? No: it stays at 0.000 to 0.001 and does not change anywhere.
- Does cheek width track it? Not shown: it moves little, has no on/off pattern, and only its one spike at 22.2 s agrees with a (weak) visual call. No threshold proposed, since there is no ratio that separates two states in this data; a per-player-median ratio (for example width above 1.1 x the player's median) would fire only on that one spike.
- Separate finding: on this clip the app's face crop fails (face_quality 0.10), so even a working signal would be skipped; the crop would need to follow the head better (for example a larger crop, or one centred on the face detector rather than the pose nose).

## Good-posture statistics (YouTube set)

Run: `backend/.venv/bin/python backend/scripts/posture_stats.py` (per-video percentiles in `testdata/youtube/posture_stats.csv`). Each video's first 120 s sampled at 5 fps (app.form.track.track_video), pose tracked with the app's tracker, view detected per video with app.form.view (one view per video), absolute (not baseline-relative) measure values on every tracked frame.

Videos in the manifest: 90; used: 70 (51 front, 19 side); skipped: 20.

`bell_proxy` (mouth = midpoint of pose landmarks 9 and 10, hands = midpoint of the wrists 15 and 16): **side view** = degrees above horizontal of the line from the mouth to the wrist midpoint (positive = wrists higher than the mouth), sign-corrected for the facing direction (nose vs the near ear); **front view** = (wrist-midpoint y - mouth y) / shoulder width (positive = wrists *below* the mouth, so the sign is opposite to the side view). Image-space proxies, not true bell angles.

Front measures (head_drop, neck_ratio, torso_lean, elbow gaps) are also taken in side videos but are scaled by the tiny side-on shoulder width there, so for the side view use head_pitch, neck_side and side_torso_lean. Elbow gap = horizontal elbow-to-hip distance / shoulder width, as `trumpet_elbows_pinned` takes it.

### Front view: pooled over 51 videos

| Measure | Videos | Frames | p1 | p5 | p50 | p95 | p99 | median of per-video p1 | median of per-video p99 |
|---|---|---|---|---|---|---|---|---|---|
| head_drop | 51 | 20460 | -0.14 | 0.01 | 0.08 | 0.17 | 0.27 | 0.02 | 0.17 |
| neck_ratio | 51 | 20460 | 0.09 | 0.35 | 0.58 | 0.81 | 1.48 | 0.46 | 0.74 |
| torso_lean | 42 | 11138 | 0.05 | 0.24 | 2.89 | 68.94 | 131.96 | 0.20 | 8.58 |
| elbow_gap_left | 41 | 10582 | 0.01 | 0.04 | 0.37 | 0.78 | 2.18 | 0.15 | 0.75 |
| elbow_gap_right | 42 | 10508 | 0.02 | 0.07 | 0.45 | 0.89 | 1.78 | 0.16 | 0.84 |
| bell_proxy | 49 | 15650 | -0.48 | 0.03 | 0.78 | 1.46 | 1.89 | 0.42 | 1.27 |

### Side view: pooled over 19 videos

| Measure | Videos | Frames | p1 | p5 | p50 | p95 | p99 | median of per-video p1 | median of per-video p99 |
|---|---|---|---|---|---|---|---|---|---|
| head_pitch | 19 | 8222 | -55.78 | -30.11 | 13.37 | 37.34 | 77.59 | 3.95 | 27.75 |
| head_drop | 19 | 8203 | -0.33 | -0.17 | 0.09 | 0.43 | 1.07 | 0.04 | 0.22 |
| neck_ratio | 19 | 8203 | 0.25 | 0.58 | 0.79 | 2.12 | 5.56 | 0.59 | 1.29 |
| neck_side | 19 | 8206 | 0.02 | 0.06 | 0.17 | 0.35 | 0.41 | 0.09 | 0.23 |
| torso_lean | 16 | 5872 | 0.05 | 0.32 | 4.88 | 82.78 | 97.44 | 0.20 | 9.56 |
| side_torso_lean | 16 | 5994 | 0.73 | 2.25 | 7.81 | 85.59 | 98.14 | 2.41 | 13.24 |
| elbow_gap_left | 17 | 5486 | 0.01 | 0.07 | 0.43 | 3.72 | 8.76 | 0.09 | 1.19 |
| elbow_gap_right | 15 | 4491 | 0.06 | 0.21 | 0.54 | 1.65 | 2.95 | 0.34 | 0.91 |
| bell_proxy | 17 | 5883 | -100.05 | -92.97 | -51.77 | -25.35 | -8.68 | -81.60 | -38.02 |

### Skipped videos

| Video id | Reason |
|---|---|
| nEwnXo02C1Y | download failed: [youtube] nEwnXo02C1Y: This video is not available |
| Xm5Q_ydreGI | download failed: [youtube] Xm5Q_ydreGI: This video is not available |
| hrfrmjL1Dtw | download failed: [youtube] hrfrmjL1Dtw: This video is not available |
| jpno20OL-ag | no visible player: pose in only 0 of 281 sampled frames |
| KF4553PAQok | no visible player: pose in only 33 of 601 sampled frames |
| RGrE7TEHu-k | no visible player: pose in only 0 of 258 sampled frames |
| NswDK689SK4 | download failed: [youtube] NswDK689SK4: This video is not available |
| cHxfCXHhbKQ | no visible player: pose in only 0 of 530 sampled frames |
| lKI1V0RqOKI | download failed: [youtube] lKI1V0RqOKI: This video is not available |
| Gi-xalf4SfU | download failed: [youtube] Gi-xalf4SfU: This video is not available |
| iOH8JYJYUic | no visible player: pose in only 16 of 601 sampled frames |
| Qn3RQJiFY_s | no visible player: pose in only 0 of 601 sampled frames |
| a6BMMasXmts | no visible player: pose in only 1 of 600 sampled frames |
| 2CDXhMwqz-E | no visible player: pose in only 0 of 601 sampled frames |
| 6b_nIBYQxX8 | no visible player: pose in only 0 of 317 sampled frames |
| 41gfqnSFgWU | no visible player: pose in only 0 of 601 sampled frames |
| shA2E-8WpcE | no visible player: pose in only 0 of 191 sampled frames |
| 1M-YhmKU6YA | no visible player: pose in only 0 of 120 sampled frames |
| rj7rMppaZl0 | download failed: [youtube] rj7rMppaZl0: This video is not available |
| neNzJCDWH-E | download failed: [youtube] neNzJCDWH-E: This video is not available |

Caveats (added by hand after the run; re-running the script regenerates the section above without them): the tails are noisy. In the pooled front table torso_lean reaches 69 degrees at p95 and 132 at p99, and neck_ratio 1.48 at p99, while the medians of the per-video p99 are 8.6 degrees and 0.74. Likely (an inference, not verified frame by frame) a few videos where the hips are cropped or occluded and the tracker still reports them above the 0.5 visibility cut, so fixed limits should be taken from the per-video medians or the p5/p50/p95 columns rather than the pooled p1/p99. Each video has one view (the median ratio over its first 120 s), so a video that cuts between a front and a side camera is counted wholly in one view. The 12 "no visible player" skips were not looked at, so whether they are title cards, ensembles or a player too small for the tracker is unverified. The side-view bell_proxy is negative throughout (median -52 degrees, p99 -9): the wrist midpoint sits below the mouth in these videos, so use it as a relative measure.

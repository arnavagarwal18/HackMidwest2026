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

## Posture stats: full video length vs the 120 s cap (2026-10-11)

Same script and settings as above (5 fps) with `--cap-s 100000`, run in batches of 10 manifest rows (one python process each, peak ~420 MB); per-video percentiles are in `testdata/youtube/posture_stats_full.csv`, the 120 s ones stay in `posture_stats.csv`. The same 70 videos are used and the same 20 skipped. Each measure's median over its videos of the per-video p1 and p99, then the largest single-video change in either:

| Measure | Videos | Median p1: 120 s | Median p1: full | Median p99: 120 s | Median p99: full | Largest per-video shift (p1 / p99) |
|---|---|---|---|---|---|---|
| head_pitch | 17 | 3.67 | 3.72 | 29.12 | 28.25 | 83.29 / 53.42 |
| head_drop | 70 | 0.02 | 0.02 | 0.17 | 0.18 | 1.90 / 1.53 |
| neck_ratio | 70 | 0.49 | 0.49 | 0.86 | 0.95 | 0.60 / 8.25 |
| neck_side | 17 | 0.07 | 0.13 | 0.21 | 0.23 | 0.29 / 0.04 |
| torso_lean | 58 | 0.20 | 0.19 | 9.18 | 16.53 | 10.75 / 96.40 |
| side_torso_lean | 16 | 2.41 | 1.27 | 13.24 | 23.39 | 2.19 / 34.11 |
| elbow_gap_left | 58 | 0.14 | 0.11 | 0.78 | 0.88 | 0.33 / 16.97 |
| elbow_gap_right | 57 | 0.23 | 0.21 | 0.86 | 0.95 | 0.89 / 15.26 |
| bell_proxy | 66 | 0.28 | 0.28 | 1.14 | 1.30 | 93.18 / 247.77 |

## Good posture clips (owner, 2026-10-11)

Clips: `testdata/form/good_posture_1_general.mp4` (115.6 s), `good_posture_2.mp4` (90.8 s), `good_posture_3.mp4` (164.3 s), all 1920x1080 at 24 fps, 17 to 29 MB. The owner says all three show very good trumpet playing and very good posture, so the expected result is zero form problems and every flag is a false positive.
Run (per clip): `dump_face_readings.py`'s steps (notes transcribed from the clip's audio, face read inside the notes, whole video analysed at 10 fps with no time limit) plus `check_camera_frame` on frames at 10, 30, 50, 70 and 90% of the clip; scratch script, not committed. The app's own path (`form.run`, as `test_form_real_video.py` runs it) gave the same flags where it got to run, but stops tracking after 90 s of run time (see Time limit below).

| Item | good_posture_1_general | good_posture_2 | good_posture_3 |
|---|---|---|---|
| Notes transcribed | 274 (9.1 to 112.5 s, 66.4 s of notes) | 130 (8.5 to 87.5 s, 48.7 s) | 438 (5.4 to 158.0 s, 103.4 s) |
| Detected view | `front`, view_ratio 1.743 | `front`, view_ratio 1.726 | `front`, view_ratio 1.904 |
| Camera check (5 frames) | not ok on all 5: `too_small` (shoulders narrower than 15% of the width) | not ok on all 5: first (9.1 s) no person found (all points missing), the other 4 `too_small` | not ok on all 5: `hips` not visible, nothing else |
| Tracking | 1064 / 1156 frames | 811 / 908 | 1543 / 1643 |
| Baseline | defaulted (neck 0.55, head_drop -0.05) | defaulted | defaulted |
| face_quality | 0.993 inside notes (662/667), 0.915 over all frames | 0.971 (471/485), 0.876 | 1.000 (1032/1032), 0.939 |
| `shoulders_raised` | not flagged | not flagged | not flagged |
| `slouching` | not flagged | not flagged | `not_visible` (hips out of frame) |
| `trumpet_head_down` | FLAGGED 8 times | FLAGGED 4 times | FLAGGED 4 times |
| `trumpet_elbows_pinned` | not flagged | not flagged | `not_visible` |
| `trumpet_cheeks_puffed` | not flagged | not flagged | not flagged |
| `trumpet_smile_embouchure` | not flagged | not flagged | not flagged |

The only flag on any clip is `trumpet_head_down` (head_drop above baseline + 0.15). Every one is a false positive, all barely over the line:

| Clip | Flag times (s) | Measured value (peak) | Threshold |
|---|---|---|---|
| good_posture_1_general | 8.1-10.4, 12.4-15.2, 16.1-17.3, 72.0-73.7, 76.4-77.4, 94.1-95.6, 98.1-99.5, 102.6-103.9 | 0.103 to 0.113 | 0.100 |
| good_posture_2 | 7.6-9.8, 12.3-13.9, 30.3-31.3, 33.2-36.2 | 0.103 to 0.109 | 0.100 |
| good_posture_3 | 19.7-21.1, 22.6-24.1, 29.5-31.1, 43.1-44.9 | 0.112 to 0.129 | 0.100 |

Likely cause (measured): the baseline is the default. The baseline is the median over the first 2 s of the clip, and none of the three has a tracked person that early (first frame with a head_drop reading: 6.1 s, 5.5 s, 5.0 s; the player is still getting into position), so `head_drop` defaults to -0.05 and the threshold becomes 0.10. These players' own head_drop sits at median 0.086, 0.083 and 0.064 over the whole clip (p90 0.104, 0.101, 0.098; share of frames above 0.10: 15%, 11%, 9%). So the default baseline is about 0.1 to 0.14 lower than the players' normal, and a normal head position crosses the threshold now and then. Against a baseline of their own median the threshold would be about 0.23, and none of the three would flag (max head_drop 0.124, 0.123, 0.166). Not tried in code: no app code was changed. Inference, not verified: the same default would hit any clip where the player is not in frame for the first 2 s.

False positives found:
- good_posture_1_general: 8 `trumpet_head_down` flags (default baseline; peak 0.113 vs 0.100).
- good_posture_2: 4 `trumpet_head_down` flags (default baseline; peak 0.109 vs 0.100).
- good_posture_3: 4 `trumpet_head_down` flags (default baseline; peak 0.129 vs 0.100); `slouching` and `trumpet_elbows_pinned` were skipped as `not_visible`, not judged.

Other things noticed, not changed:
- Camera check: it says "not ok" on every sampled frame of all three clips, though the owner calls the posture and playing very good. Clips 1 and 2: `too_small` (shoulders under 15% of the width of a 1920x1080 frame); clip 3: hips not in frame.
- Time limit: `form.run` gives up tracking after 90 s of run time (`TIME_LIMIT_S`), so how much of a long clip it checks depends on machine load. In the expectations test, good_posture_1_general was checked for its first 97 s (`warning: partial: first 97 s checked`), and good_posture_3 for its first 52 s in one run and its first 146 s in another; good_posture_2 was checked in full. The face rules were skipped as `not_visible` in that test path (face_quality None), because the test's take has no transcribed notes to gate the face on.
- `testdata/form_expectations.json`: the three clips are listed in `good_form` with `known_false_positive` set (`trumpet_head_down`), and `test_form_real_video.py` runs such an entry as a strict expected failure: the suite stays green, and goes red (XPASS) once the false flag is gone, which is the cue to remove the field.

## Fixed limits (LLD-4 change 11, 2026-10-11)

Fixed trumpet limits apply from the first frame; the baseline rules stay for drift. A frame breaks a rule when it crosses the stricter of the baseline threshold and the fixed limit, so one episode gives one flag (same rule names and output shape). When the baseline is the default (nobody tracked in the first 2 s), only the fixed limit is used: the default head_drop of -0.05 had put the head-down threshold at 0.10, which flagged the owner's three good clips. The limits live in `backend/app/form/config.py` (each with its source stat in a comment). Trumpet only; violin is unchanged. Source stats: the "Good-posture statistics (YouTube set)" tables above. Pooled p1/p99 of torso_lean and neck_ratio are inflated (probably cropped hips), so those limits rest on per-video medians and pooled p5/p95.

| Rule (flag) | Measure, view | Limit | Stat it came from |
|---|---|---|---|
| `trumpet_head_down` | head_drop, front | above 0.30 | pooled p95 0.17, p99 0.27; median of per-video p99 0.17 |
| `shoulders_raised` | neck_ratio, front | below 0.30 | pooled p5 0.35 (p1 0.09 inflated); median of per-video p1 0.46 |
| `trumpet_head_down` | head_pitch, side | above 40 deg | pooled p95 37.3 (p99 77.6 is noise); median of per-video p99 27.8 |
| `shoulders_raised` | neck_side, side | below 0.04 | pooled p5 0.06, p1 0.02; median of per-video p1 0.09 |
| `slouching` | torso_lean (front) / side_torso_lean (side) | above 15 deg (already fixed before this change; kept) | median of per-video p99 8.6 (front) and 13.2 (side); pooled p95 68.9 / 85.6 inflated |
| `trumpet_elbows_wide` (new) | elbow gap, either side, front only | above 1.0 | pooled p95 0.78 left / 0.89 right; median of per-video p99 0.75 / 0.84 |
| `trumpet_bell_angle` "bell too high" (new) | bell_height, front | below -0.55 (wrists above the mouth) | pooled p1 -0.48 |
| `trumpet_bell_angle` "bell too low" (new) | bell_height, front | above 2.0 | pooled p99 1.89, p95 1.46 |
| `trumpet_bell_angle` "bell too high" (new) | bell_angle, side | above -5 deg | pooled p99 -8.7 |
| `trumpet_bell_angle` "bell too low" (new) | bell_angle, side | below -100 deg | pooled p1 -100.1, p5 -93.0 |

The bell measures are the statistics script's `bell_proxy` (front: `bell_height`, side: `bell_angle`) moved into `app/form/bell_measures.py`; a test keeps the two equal. The bell limits use pooled p1/p99 (their tails are not noted as inflated), so they are loose: the median good side video plays 52 degrees below horizontal.

### Flags on the real clips, before (main 838cb14) and after

Run: each clip tracked with `track_video` (10 fps, no hands) and judged with `analyse(..., "trumpet")`, AI off, no face. "Same" means the same flags as before.

| Clip | View | Before | After |
|---|---|---|---|
| `form/good_posture_1_general.mp4`, `good_posture_2.mp4`, `good_posture_3.mp4` | front | `trumpet_head_down` x8, x4, x4 (default baseline, peaks 0.103-0.129 vs 0.100) | none on all three |
| `form/good_posture_side.mp4` | side | none | none |
| `form/neck_bad_then_good_side.mp4` | side | none | none (see below: not met) |
| `form/bad_posture_side.mp4` | front (3 frames) | none | none (`trumpet_bell_angle` not_visible) |
| `form/take5_ode_form_front.mp4` | front | `trumpet_elbows_pinned` left 2.7-6.1 s and 30.2-31.4 s | same |
| `form/take5_ode_form_side.mp4` | side | none | none |
| `ode_to_joy/ode_to_joy_trumpet11.mp4` | side | `slouching` at 1.7-4.2, 6.7-8.5, 18.1-19.3 s (15.1-15.5 deg vs 15) | same |
| `trumpet_video1.mp4`, `trumpet_video2.mp4` | front | none | none |
| `form/puffed_then_not.mp4` | front | none | none |
| `form/cheek_modulation.mp4` | front | `slouching` x2, `shoulders_raised` x4, `trumpet_head_down` x2 | same plus `trumpet_elbows_wide` x4 (10.1-11.7 s left, 12.9-15.1 s left, 19.2-21.0 s right, 24.6-26.1 s right) |
| `form/posture_explainer.mp4` (reference) | side | `slouching` x2, `shoulders_raised` x2 | same |

`cheek_modulation.mp4` is a screen recording with the player partly cropped, where the pose tracking is unreliable (elbow gaps 1.3 to 3.1); the new wide-elbow flags there are not meaningful. New entries in `rules_skipped`: `trumpet_elbows_wide` is `not_for_view` in every side clip and `not_visible` where `trumpet_elbows_pinned` already was; `trumpet_bell_angle` is `not_visible` on `neck_bad_then_good_side`, `take5_ode_form_side`, `posture_explainer`, `cheek_modulation` and `bad_posture_side` (wrists or mouth not visible in over 70% of frames).

### Not met: `neck_bad_then_good_side.mp4` is not flagged

The bad first half cannot be flagged by any fixed limit that sits outside the good set, because its numbers are inside the good set (and inside the other good clip). Head pitch (side), degrees, per-second median:

| Clip, part | head_pitch | head_drop | neck_side |
|---|---|---|---|
| `neck_bad_then_good_side`, 0-1.2 s (trumpet still coming up) | 21 to 31 | 1.2 to 6 | 0.26 |
| `neck_bad_then_good_side`, 1.4-4.8 s (the bad half) | 8.7 to 14.6 | 0.24 to 0.41 | 0.31-0.32 |
| `neck_bad_then_good_side`, 5-10 s (the good half) | -9 to 1 | -0.08 to 0.04 (0.25 at 10 s) | 0.32-0.36 |
| `good_posture_side`, 0-2.5 s (first take, good) | 9 to 13 | 0.34 to 0.50 | 0.07 |
| `good_posture_side`, 3-6.5 s (good) | 5 to 26 | 0.01 to 0.09 | 0.09-0.10 |
| Good set, side view | median 13.4; per-video p99 median 27.8; pooled p95 37.3 | per-video p99 median 0.22 | per-video p1 median 0.09 |

The bad half's head pitch (about 12) equals the good set's median (13.4) and is below `good_posture_side`'s own good playing (up to 26); its head_drop (0.24 to 0.41) is below that good clip's 0.34 to 0.50; neck_side depends on how close the camera is (0.31 here, 0.07 on the full-body clip). A limit low enough to catch the bad half (head_pitch under about 10) would flag the good-set median, `good_posture_side.mp4`, and `take5_ode_form_side.mp4` (head_pitch p50 11.7), so none was set. Without a second source for the fault (for example neck-forward distance, which the pose landmarks 0-24 in a close-up do not give) this clip cannot be a fixed-limit test; it can still be caught only when the baseline comes from good posture (the drift rule: 17 degrees past the good half's baseline).

## Fault-video review: draft answer keys (LLD-4 change 11 inputs)

Run on 20 of the 21 videos in `testdata/youtube/fault_candidates.csv` (`FSsO_-LrqE4` is unavailable). Answers are in `testdata/youtube/fault_candidates_reviewed.csv` (new `(reviewed)` columns; the sheet's own columns are untouched). **All fault lines are DRAFT - Xavier to confirm.**

Method: each video tracked with the app's form pipeline (`app.form.track.track_video` at **5 fps**, `rules.analyse` with the Face Landmarker read on every frame, `view.detect_view`; AI off), the whole video analysed (longest 788 s). Hips in frame = nose plus at least one hip landmark visible (>= 0.5) and inside the image, as a share of sampled frames. The tracker's own 'trumpet up' test (wrist midpoint near the mouth) is only a hint: it missed a trumpet held with the hands low on the valves (92M9zflsh-M at 392-412 s) and fired on hand-to-face gestures (bs65wygep88 at 175-184 s), so playing and faults were checked on frames (a contact sheet per video, 2-3 picture-model questions each, light model; stills only). Frames were sampled about every 25-65 s plus the tracker's candidate stretches, so short bursts of playing may be missed; the app's posture flags (many 'head dropped' / 'slouching' / 'smile embouchure' flags on talking heads) were not accepted unless the frames agreed. Cheek puffing could not be judged from stills at this size in any video (the app's cheek_puff stayed at 0.000-0.001 everywhere, as in the earlier puffed_then_not run).

Findings: only 3 videos are clean single-player clips with head to hips and 5+ s of playing (1CH0EqpWM6U, EaTvWPsHDQ8, YnPCwbVwDYM), and none of them shows a clear posture fault in its playing stretch; 4 more are usable in part (no hips, or no playing). The other 13 are talking heads cropped at the chest or waist, group shots, a non-trumpet instrument, or stretching without a trumpet.

- **RYGVoq8850U** (5 Mistakes Trumpet Players Make (And How to Fix Them!); 5:02): usable **no**; head to hips: no - pose has hips in frame in 0% of sampled frames (front view, 300.8 s analysed); 5+ s playing: no - longest stretch: 3.6 (tracker 144.4-148.0; six bursts of 2-4 s, 24 s in total); DRAFT - Xavier to confirm: no clear fault demonstrated; talking head to chest/waist, upright; trumpet at lips only in short bursts (~117, 144-148, 207-210, 229-235, 257-259 s); finger at mouth corner ~117 s and jaw ~164 s (embouchure talk) not a posture fault; trim: none (hips never in frame; no unbroken 5 s of playing).
- **Mq-e5iKvIGQ** (Your Posture Is Killing Your Trumpet Sound (Fix This First); 3:32): usable **no**; head to hips: no - pose has hips in frame in 0% of sampled frames (front view, 211.2 s analysed); 5+ s playing: yes - longest stretch: probable ~79-86 (trumpet at mouth in frames 80 and 84 s; tracker's wrist test missed it, so the stretch is not measured); DRAFT - Xavier to confirm: no clear posture fault seen; talking head to waist, upright, shoulders level; slight head tilt toward the horn at ~84 s (tracker 'slouching' 78.8-86.4 s is the horn being raised, not confirmed in frames); trim: none (hips never in frame; playing only ~79-86 s, waist crop).
- **1CH0EqpWM6U** (Avoid Tension and Play Easier! | P for Posture | Trumpet A-Z S01E16; 5:10): usable **yes**; head to hips: no - pose has hips in frame in 13% of sampled frames (front view, 309.4 s analysed); 5+ s playing: yes - longest stretch: 164.0-181.2; DRAFT - Xavier to confirm: no clear posture fault seen while playing (frames 166, 172, 178 s upright, seated side view); tracker flags 'head dropped' 164.6-181.2 s but frames do not confirm it; 140-158 s demo cutaways crop the head out so posture there cannot be judged; trim: 165-181 s.
- **GVlVUcvi4is** (10 Common Trumpet Mistakes and How to Fix Them; 11:16): usable **no**; head to hips: no - pose has hips in frame in 0% of sampled frames (front view, 675.2 s analysed); 5+ s playing: no - longest stretch: <5 (trumpet at lips only briefly at ~100 and ~603 s; tracker 'up' runs 2-4.6 s); DRAFT - Xavier to confirm: no posture fault demonstrated, only described (text card 'Playing with incorrect posture can lead to physical problems' ~123 s); presenter head to chest, edited with cutaways; tracker head dropped/slouching flags not confirmed; trim: none (hips never in frame; playing only in brief cutaways).
- **ZTcrE6iruBc** (How to.. sit properly when playing brass instruments; 0:38): usable **no**; head to hips: yes - pose has hips in frame in 97% of sampled frames (front view, 37.0 s analysed); 5+ s playing: yes - longest stretch: ~4-34 (left/right trumpeters, by frames; tracker's person has no trumpet); DRAFT - Xavier to confirm: three seated players (2 trumpets, 1 tuba/euphonium), too small to judge; left player leaning back ~4-20 s, middle player head down/leaning forward ~12 s (low confidence); not a single-player clip; trim: none (3 players in frame; app tracks the tuba player).
- **qFmhhHTn810** (Posture and Optimal Horn Angle - Play Better Today!; 13:09): usable **partly**; head to hips: no - pose has hips in frame in 0% of sampled frames (front view, 788.8 s analysed); 5+ s playing: yes - longest stretch: 12.2 (478.0-490.2; also 497.2-511.0); DRAFT - Xavier to confirm: bell drooping (below the mouthpiece) ~478-511 s while playing, also ~300 s; head level, no other clear posture fault; presenter head to waist (tracker smile-embouchure flags are speech); trim: 478-498 s (playing, bell drooping; waist crop, no hips).
- **fnvwOqXv8fs** (Finding the Right Playing Angle for Trumpet; 7:10): usable **partly**; head to hips: no - pose has hips in frame in 10% of sampled frames (side view, 429.8 s analysed); 5+ s playing: yes - longest stretch: 35.6 (272.2-307.8); also 53.0-61.4, 64.2-77.0, 189.6-198.4, 204.4-212.2, 252.6-266.2; DRAFT - Xavier to confirm: bell slightly drooping and head forward/tilted down toward the horn while playing ~56-77 s, ~150 s, ~195 s; shoulders not raised (tracker 'head dropped' 215.6-224.6 s and 'shoulders raised' 222.8-224.2 s not confirmed: frame at 220 s upright, trumpet at waist); trim: 53-73 s (standing, playing, bell slightly drooping, head forward; cut at the waist, hips only at the frame edge).
- **92M9zflsh-M** (How to Play Trumpet with Less Tension! | #TrumpetProTips E08; 7:48): usable **no**; head to hips: no - pose has hips in frame in 0% of sampled frames (front view, 467.6 s analysed); 5+ s playing: yes - longest stretch: ~20+ (trumpet at mouth in frames 392, 397, 402, 407, 412 s, gone by 418 s; tracker's wrist test missed it because the hand holds the valves low); DRAFT - Xavier to confirm: no raised shoulders or head-forward seen; head angled toward the horn ~400 s, upright talking head to waist otherwise; tracker 'smile embouchure' flags are speech; trim: 392-412 s (playing, head to waist; hips not in frame).
- **4N_3KYu_hgQ** (Muscle Control to Eliminate Neck and Back Pain Associated with Trumpet Playing; 11:49): usable **no**; head to hips: no - pose has hips in frame in 6% of sampled frames (side view, 708.6 s analysed); 5+ s playing: no - longest stretch: 0 (no trumpet in 18 frames checked 0-600 s; tracker 'up' runs are arms raised overhead in back-view stretches); DRAFT - Xavier to confirm: no trumpet posture fault shown; shoulder/back stretches with arms overhead (back view ~290-420 s), tracker 'shoulders raised' 279-365 s is the stretch itself; upright talking head otherwise; trim: none (no trumpet, head to chest only).
- **KSizitxb9ik** (Reduce tension for trumpet players; 1:25): usable **no**; head to hips: no - pose has hips in frame in 30% of sampled frames (side view, 84.8 s analysed); 5+ s playing: no - longest stretch: 0 (trumpet at chest level in all checked frames); DRAFT - Xavier to confirm: no clear posture fault seen; talking selfie, shoulders to waist, trumpet held at chest (tracker head dropped ~27-29, 65-71 s not confirmed); trim: none (no playing).
- **EaTvWPsHDQ8** (trumpet player - chair for best posture; 1:18): usable **yes**; head to hips: yes - pose has hips in frame in 82% of sampled frames (side view, 77.8 s analysed); 5+ s playing: yes - longest stretch: 0.0-27.8; DRAFT - Xavier to confirm: head dropped / slouching forward 53-64 s with the trumpet resting (tracker head dropped 53.4-61.6 s, slouching 53.8-63.6 s; frame at 56 s: head tilted down, upper body leaning forward); 0-28 s playing upright side view, no clear fault (head tilted toward the horn at ~2 s, low confidence); trim: 0-20 s (seated side view, playing; good-posture reference rather than a fault).
- **AmpggAjW9bk** (Trumpet Technique 101 - Lesson 2 : Sitting Posture; 1:23): usable **partly**; head to hips: yes - pose has hips in frame in 89% of sampled frames (front view, 82.4 s analysed); 5+ s playing: no - longest stretch: 0 (no trumpet in any checked frame); DRAFT - Xavier to confirm: head dropped/forward, looking down ~21-31 s (tracker head dropped 21.6-31.2 s; frame at 22 s shows bending forward, head lowered); otherwise upright seated talk, no trumpet; trim: 19-33 s (head-down demo, no trumpet; no playing in video).
- **YnPCwbVwDYM** (Trumpet: Hand Position & Posture; 1:51): usable **yes**; head to hips: no - pose has hips in frame in 19% of sampled frames (front view, 110.2 s analysed); 5+ s playing: yes - longest stretch: ~90-105 (trumpet at mouth by frames 90, 96, 100 s; tracker 96-105 s); DRAFT - Xavier to confirm: no clear posture fault seen; good-posture demo (upright, back straight, feet flat at 50 s and 100 s); edited cuts between full body, waist crop and valve close-ups; tracker flags (head dropped 26-42 s, slouching/shoulders raised 58-62 s) not confirmed in frames; trim: 90-105 s (waist-to-full-body, trumpet at mouth, ends before 'LEVEL' title card at ~106 s).
- **tsyKFlBsqZY** (Brass Playing Fundamentals - Posture From Head To Toe; 4:59): usable **no**; head to hips: yes - pose has hips in frame in 97% of sampled frames (front view, 297.8 s analysed); 5+ s playing: yes - longest stretch: unmeasured: trumpeter (right of two people) at lips at 138, 270, 274 s by frames; tracker's person is probably the speaker; DRAFT - Xavier to confirm: no clear fault seen; trumpeter (right) upright, head tilted slightly forward at ~274 s; speaker and trumpeter share the frame at lap level (tracker flags head dropped 33-151 s are probably the speaker); trim: none (two people in frame; app cannot be told to follow the trumpeter).
- **z9YjzBBIF78** (Playing Trumpet: How to Correct Puffed cheeks; 0:50): usable **no**; head to hips: no - pose has hips in frame in 0% of sampled frames (front view, 49.6 s analysed); 5+ s playing: yes - longest stretch: uncertain: trumpet at mouth in frames 30, 33, 36, 44, 46, 49 s but not at 38, 41 s; 5 s unbroken not confirmed (tracker's 11.4-18 s is a hand-to-cheek gesture); DRAFT - Xavier to confirm: puffed cheeks not clearly visible at this size (unclear in every frame); head slightly lowered looking at the horn ~41-49 s; no other posture fault seen; hand pressed on cheek 12-26 s (demonstration); trim: face-only clip ~30-49 s (head and chest, hips out of frame, playing on/off); not a posture clip.
- **O58aoxi2t64** (Embouchure Help - Fixing Puffy Cheeks; 7:27): usable **no**; head to hips: no - pose has hips in frame in 0% of sampled frames (front view, 446.8 s analysed); 5+ s playing: no - longest stretch: <5 (trumpet at mouth only at ~332 s in the frames checked; tracker longest 0.8 s); DRAFT - Xavier to confirm: no puffed cheeks or posture fault visible in 24 frames; talking head to chest, upright, hand on chin; puffing not demonstrated on camera in the frames checked; trim: none (hips never in frame; almost no playing).
- **bs65wygep88** (Trumpet Embouchure 4 Things (you probably want to avoid); 5:42): usable **no**; head to hips: no - pose has hips in frame in 0% of sampled frames (side view, 341.2 s analysed); 5+ s playing: no - longest stretch: <5 (trumpet on lips at ~124-127 s and ~155 s in frames, brief; tracker's 174.6-184.0 s is a hand-to-face gesture, no trumpet); DRAFT - Xavier to confirm: no puffed cheeks or posture fault visible (none seen in 12+6+6 frames; 'Don't puff your cheeks' caption at ~100 s is spoken advice, not a demo); front-facing talking head to upper chest; trim: none (hips never in frame; no sustained playing).
- **JEzh4lyPriM** (Brass Playing and Cheek Puffing; 8:03): usable **no**; head to hips: no - pose has hips in frame in 0% of sampled frames (front view, 481.8 s analysed); 5+ s playing: no - longest stretch: 0 in frames checked (low brass beside him, never at his mouth in 12 frames; tracker 'up' 2 s); DRAFT - Xavier to confirm: no puffed cheeks or posture fault visible; talking head to chest, upright; tuba/euphonium-type instrument, not a trumpet (tracker slouching/head dropped flags 57-301 s not confirmed); trim: none (not a trumpet, hips never in frame).
- **FSsO_-LrqE4** (Eliminating PUFFY CHEEKS! For brass students.; 6:33): usable **no**; head to hips: n/a - video unavailable (download failed); 5+ s playing: n/a; DRAFT - Xavier to confirm: not reviewed, video unavailable; trim: n/a.
- **h1q7VzuWuLQ** (Brass Instruments: How To Stop Puffing Out Your Cheeks!; 5:00): usable **no**; head to hips: no - pose has hips in frame in 0% of sampled frames (front view, 299.4 s analysed); 5+ s playing: no - longest stretch: <5 (mouthpiece buzzing at ~178 and ~245 s; low brass at the mouth ~82 and ~272 s, not trumpet; stretches not measured); DRAFT - Xavier to confirm: no puffed cheeks or posture fault clearly visible (cheeks 'unclear' while buzzing at ~178, 245, 272 s); upright talking head to chest; low-resolution 640x360, tuba/euphonium-type instrument, not a trumpet; trim: none (not a trumpet, hips never in frame).
- **k2tBufHUIEg** (Dizzy Gillespie cheeks; 0:41): usable **partly**; head to hips: no - pose has hips in frame in 13% of sampled frames (front view, 40.6 s analysed); 5+ s playing: yes - longest stretch: ~2-40 (trumpet at mouth in all 6 frames checked; tracker's longest 13.0-20.6); DRAFT - Xavier to confirm: cheeks puffed ~6-24 s (close-ups at 6, 12, 16, 24 s); posture upright, no clear fault; wide shots only at ~2 s and ~36 s (head to knees); trim: 5-20 s (close-up, playing, cheeks puffed; head and chest only, so a cheek clip not a posture clip).

## Fault videos with change-11 limits (2026-10-11)

Run on 20 of the 21 videos in `testdata/youtube/fault_candidates.csv` (`FSsO_-LrqE4` is unavailable; `fetch_youtube.py` exits with 20 ok, 1 failed). Main at 3793932 (has the change-11 fixed limits, b811213), AI off, trumpet, no face reading and no hands. Each video tracked one at a time with `track_video` at the app's 10 fps and judged with `analyse(..., "trumpet")` by `backend/scripts/fault_flags.py`; the table comes from `backend/scripts/fault_flags_report.py` and the raw flags are in `testdata/youtube/fault_flags.csv`. **Only the first 290 s of each video were analysed** (`--max-seconds 290`, the default of `video_cap.py`), except `qFmhhHTn810`, re-run with 520 s (`--only qFmhhHTn810 --max-seconds 520`, before the 290 s default cap reached main) so that its key (478-511 s) is inside it (its view reads as side at 520 s and front at 290 s, where it had no flags). Cheek puffing and smile embouchure need the face reading, which `form.run` makes only inside a take's notes; there are none here, so those rules were not run.

**Keys.** `testdata/youtube/fault_candidates_reviewed.csv` is on main; Xavier (H-162) said to treat every row as a correct answer key (a row marked "WIP - unfinished" would not be one; there is none). The fault lines were made from sparse still frames and a 5 fps run, so they are coarse. `testdata/youtube/fault_keys.csv` lists the faults those lines name (19 rows: rule, times, slack; a hedged or approximate mention is a single time with 5 s slack); a flag of the same rule within the slack of a key's times finds it, a key with no such flag is missed (or "not run"), and a flag that finds no key is extra. Videos whose line says "no clear fault" have no key rows, so all their flags count as extra.

Totals (19 keys, 72 flags in 16 of the 20 videos):

| Video | Length s | View | Flags (rule start-end, severity) | Rules skipped as not_visible | Against the answer keys |
|---|---|---|---|---|---|
| `RYGVoq8850U` 5 Mistakes Trumpet Players Make (And How to Fix Them!) | 301 (analysed 289.9) | front | `shoulders_raised` 33.2-34.5 s (1.0)<br>`shoulders_raised` 35.1-36.6 s (0.46)<br>`slouching` 35.6-36.7 s (0.93)<br>`slouching` 42.9-44.8 s (0.26) | `slouching`, `trumpet_elbows_pinned`, `trumpet_elbows_wide` | extra: `shoulders_raised` 33.2-34.5 s<br>`shoulders_raised` 35.1-36.6 s<br>`slouching` 35.6-36.7 s<br>`slouching` 42.9-44.8 s |
| `Mq-e5iKvIGQ` Your Posture Is Killing Your Trumpet Sound (Fix This First) | 211 (analysed 211.2) | front | `slouching` 33.1-34.2 s (0.02)<br>`slouching` 78.8-86.5 s (0.32) | `slouching`, `trumpet_bell_angle`, `trumpet_elbows_pinned`, `trumpet_elbows_wide` | missed: `trumpet_head_down` ~84 s<br>extra: `slouching` 33.1-34.2 s<br>`slouching` 78.8-86.5 s |
| `1CH0EqpWM6U` Avoid Tension and Play Easier! / P for Posture / Trumpet A-Z S01E16 | 310 (analysed 289.9) | front | `slouching` 70.0-72.3 s (0.29)<br>`trumpet_head_down` 133.0-135.1 s (0.41)<br>`trumpet_head_down` 137.4-139.5 s (0.12)<br>`trumpet_head_down` 140.0-141.6 s (0.1)<br>`shoulders_raised` 147.7-158.5 s (0.46)<br>`slouching` 147.8-152.5 s (1.0)<br>`trumpet_head_down` 147.8-149.5 s (0.1)<br>`slouching` 155.7-158.2 s (0.51)<br>`trumpet_head_down` 163.1-164.8 s (0.03)<br>`trumpet_head_down` 166.5-181.2 s (0.62)<br>`trumpet_head_down` 240.9-252.5 s (0.65) | `slouching`, `trumpet_bell_angle`, `trumpet_elbows_pinned`, `trumpet_elbows_wide` | extra: `slouching` 70.0-72.3 s<br>`trumpet_head_down` 133.0-135.1 s<br>`trumpet_head_down` 137.4-139.5 s<br>`trumpet_head_down` 140.0-141.6 s<br>`shoulders_raised` 147.7-158.5 s<br>`slouching` 147.8-152.5 s<br>`trumpet_head_down` 147.8-149.5 s<br>`slouching` 155.7-158.2 s<br>`trumpet_head_down` 163.1-164.8 s<br>`trumpet_head_down` 166.5-181.2 s<br>`trumpet_head_down` 240.9-252.5 s |
| `GVlVUcvi4is` 10 Common Trumpet Mistakes and How to Fix Them | 675 (analysed 290.0) | front | `trumpet_head_down` 37.8-39.4 s (1.0)<br>`shoulders_raised` 269.8-271.0 s (0.92) | `slouching`, `trumpet_bell_angle`, `trumpet_elbows_pinned`, `trumpet_elbows_wide` | extra: `trumpet_head_down` 37.8-39.4 s<br>`shoulders_raised` 269.8-271.0 s |
| `ZTcrE6iruBc` How to.. sit properly when playing brass instruments | 37 (analysed 37.0) | front | `shoulders_raised` 25.7-27.0 s (0.08)<br>`trumpet_head_down` 25.8-26.8 s (0.05) | - | missed: `trumpet_head_down` ~12 s<br>`slouching` 4-20 s<br>extra: `shoulders_raised` 25.7-27.0 s<br>`trumpet_head_down` 25.8-26.8 s |
| `qFmhhHTn810` Posture and Optimal Horn Angle - Play Better Today! | 789 (analysed 519.9) | side | `trumpet_bell_angle` 150.3-151.4 s (0.05)<br>`trumpet_bell_angle` 157.7-158.9 s (0.37)<br>`trumpet_bell_angle` 168.6-169.9 s (0.48)<br>`trumpet_bell_angle` 304.1-305.3 s (0.09) | `slouching` | found: `trumpet_bell_angle` ~300 s<br>missed: `trumpet_bell_angle` 478-511 s<br>extra: `trumpet_bell_angle` 150.3-151.4 s<br>`trumpet_bell_angle` 157.7-158.9 s<br>`trumpet_bell_angle` 168.6-169.9 s |
| `fnvwOqXv8fs` Finding the Right Playing Angle for Trumpet | 430 (analysed 289.9) | side | `trumpet_bell_angle` 112.5-117.1 s (0.1)<br>`trumpet_bell_angle` 117.8-118.8 s (0.04)<br>`trumpet_head_down` 215.5-219.4 s (0.28)<br>`trumpet_head_down` 221.4-224.4 s (0.35)<br>`shoulders_raised` 222.8-224.1 s (0.13)<br>`trumpet_bell_angle` 237.1-238.5 s (0.06)<br>`trumpet_bell_angle` 249.2-253.0 s (0.09) | - | missed: `trumpet_bell_angle` 56-77 s<br>`trumpet_head_down` 56-77 s<br>`trumpet_bell_angle` ~150 s<br>`trumpet_head_down` ~150 s<br>`trumpet_bell_angle` ~195 s<br>`trumpet_head_down` ~195 s<br>extra: `trumpet_bell_angle` 112.5-117.1 s<br>`trumpet_bell_angle` 117.8-118.8 s<br>`trumpet_head_down` 215.5-219.4 s<br>`trumpet_head_down` 221.4-224.4 s<br>`shoulders_raised` 222.8-224.1 s<br>`trumpet_bell_angle` 237.1-238.5 s<br>`trumpet_bell_angle` 249.2-253.0 s |
| `92M9zflsh-M` How to Play Trumpet with Less Tension! / #TrumpetProTips E08 | 468 (analysed 289.9) | front | none | `slouching`, `trumpet_bell_angle`, `trumpet_elbows_pinned`, `trumpet_elbows_wide` | not run: `trumpet_head_down` ~400 s |
| `4N_3KYu_hgQ` Muscle Control to Eliminate Neck and Back Pain Associated with Trumpet Playing | 709 (analysed 289.9) | side | `shoulders_raised` 279.7-281.4 s (0.4)<br>`shoulders_raised` 286.9-290.0 s (0.04) | `slouching`, `trumpet_bell_angle` | extra: `shoulders_raised` 279.7-281.4 s<br>`shoulders_raised` 286.9-290.0 s |
| `KSizitxb9ik` Reduce tension for trumpet players | 85 (analysed 84.9) | side | `shoulders_raised` 16.1-17.4 s (0.02)<br>`trumpet_bell_angle` 25.8-30.1 s (0.38)<br>`trumpet_head_down` 27.2-28.3 s (0.92)<br>`trumpet_bell_angle` 47.4-49.2 s (0.18)<br>`trumpet_bell_angle` 62.9-64.8 s (0.14)<br>`trumpet_bell_angle` 65.4-68.7 s (0.14)<br>`trumpet_bell_angle` 69.3-72.2 s (0.24) | - | extra: `shoulders_raised` 16.1-17.4 s<br>`trumpet_bell_angle` 25.8-30.1 s<br>`trumpet_head_down` 27.2-28.3 s<br>`trumpet_bell_angle` 47.4-49.2 s<br>`trumpet_bell_angle` 62.9-64.8 s<br>`trumpet_bell_angle` 65.4-68.7 s<br>`trumpet_bell_angle` 69.3-72.2 s |
| `EaTvWPsHDQ8` trumpet player - chair for best posture | 78 (analysed 77.8) | side | `trumpet_head_down` 53.3-56.5 s (0.37)<br>`slouching` 53.6-54.9 s (0.53)<br>`trumpet_head_down` 57.2-58.9 s (0.1)<br>`trumpet_head_down` 59.8-61.2 s (0.43)<br>`slouching` 61.5-64.4 s (0.22) | - | found: `trumpet_head_down` 53-64 s<br>`slouching` 53-64 s<br>missed: `trumpet_head_down` ~2 s |
| `AmpggAjW9bk` Trumpet Technique 101 - Lesson 2 : Sitting Posture | 83 (analysed 82.4) | front | `shoulders_raised` 21.0-22.7 s (1.0)<br>`trumpet_head_down` 21.4-22.6 s (0.09)<br>`trumpet_elbows_pinned` 54.3-55.3 s (0.33)<br>`trumpet_elbows_pinned` 73.3-75.4 s (0.27) | - | found: `trumpet_head_down` 21-31 s<br>extra: `shoulders_raised` 21.0-22.7 s<br>`trumpet_elbows_pinned` 54.3-55.3 s<br>`trumpet_elbows_pinned` 73.3-75.4 s |
| `YnPCwbVwDYM` Trumpet: Hand Position & Posture | 110 (analysed 110.3) | front | `trumpet_bell_angle` 73.5-75.0 s (0.45)<br>`slouching` 75.3-76.6 s (0.27) | `slouching`, `trumpet_elbows_pinned`, `trumpet_elbows_wide` | extra: `trumpet_bell_angle` 73.5-75.0 s<br>`slouching` 75.3-76.6 s |
| `tsyKFlBsqZY` Brass Playing Fundamentals - Posture From Head To Toe | 298 (analysed 289.9) | front | `shoulders_raised` 1.1-2.1 s (1.0)<br>`slouching` 1.1-2.1 s (1.0)<br>`slouching` 5.0-7.2 s (0.11)<br>`trumpet_elbows_wide` 118.6-120.0 s (0.07)<br>`trumpet_elbows_pinned` 159.4-161.5 s (0.24)<br>`shoulders_raised` 184.4-186.1 s (0.78) | - | missed: `trumpet_head_down` ~274 s<br>extra: `shoulders_raised` 1.1-2.1 s<br>`slouching` 1.1-2.1 s<br>`slouching` 5.0-7.2 s<br>`trumpet_elbows_wide` 118.6-120.0 s<br>`trumpet_elbows_pinned` 159.4-161.5 s<br>`shoulders_raised` 184.4-186.1 s |
| `z9YjzBBIF78` Playing Trumpet: How to Correct Puffed cheeks | 50 (analysed 49.6) | front | none | `slouching`, `trumpet_bell_angle`, `trumpet_elbows_pinned`, `trumpet_elbows_wide` | missed: `trumpet_head_down` 41-49 s |
| `O58aoxi2t64` Embouchure Help - Fixing Puffy Cheeks | 447 (analysed 290.0) | front | none | `slouching`, `trumpet_elbows_pinned`, `trumpet_elbows_wide` | no key, no flag |
| `bs65wygep88` Trumpet Embouchure 4 Things (you probably want to avoid) | 341 (analysed 290.0) | side | `trumpet_head_down` 148.1-149.1 s (0.56)<br>`trumpet_head_down` 200.3-202.2 s (0.04)<br>`trumpet_head_down` 208.0-209.1 s (0.81)<br>`trumpet_head_down` 251.7-253.1 s (0.75)<br>`trumpet_head_down` 279.4-280.4 s (0.44) | `slouching`, `trumpet_bell_angle` | extra: `trumpet_head_down` 148.1-149.1 s<br>`trumpet_head_down` 200.3-202.2 s<br>`trumpet_head_down` 208.0-209.1 s<br>`trumpet_head_down` 251.7-253.1 s<br>`trumpet_head_down` 279.4-280.4 s |
| `JEzh4lyPriM` Brass Playing and Cheek Puffing | 482 (analysed 289.9) | front | `slouching` 91.3-92.9 s (0.2)<br>`slouching` 96.8-97.9 s (0.08)<br>`slouching` 105.6-106.6 s (0.01)<br>`slouching` 225.6-228.1 s (0.16)<br>`slouching` 242.8-244.1 s (0.01)<br>`slouching` 283.5-285.2 s (0.04) | `slouching`, `trumpet_bell_angle`, `trumpet_elbows_pinned`, `trumpet_elbows_wide` | extra: `slouching` 91.3-92.9 s<br>`slouching` 96.8-97.9 s<br>`slouching` 105.6-106.6 s<br>`slouching` 225.6-228.1 s<br>`slouching` 242.8-244.1 s<br>`slouching` 283.5-285.2 s |
| `FSsO_-LrqE4` Eliminating PUFFY CHEEKS! For brass students. |  | - | download failed: [youtube] FSsO_-LrqE4: This video is not available | - | - |
| `h1q7VzuWuLQ` Brass Instruments: How To Stop Puffing Out Your Cheeks! | 300 (analysed 289.9) | front | `slouching` 181.5-185.6 s (0.12)<br>`slouching` 225.4-226.7 s (0.12)<br>`slouching` 231.1-232.1 s (0.14) | `slouching`, `trumpet_bell_angle`, `trumpet_elbows_pinned`, `trumpet_elbows_wide` | extra: `slouching` 181.5-185.6 s<br>`slouching` 225.4-226.7 s<br>`slouching` 231.1-232.1 s |
| `k2tBufHUIEg` Dizzy Gillespie cheeks | 41 (analysed 40.7) | front | none | `slouching`, `trumpet_elbows_pinned`, `trumpet_elbows_wide` | not run: `trumpet_cheeks_puffed` 6-24 s |

| Rule | Found | Missed | Extra | Not run |
|---|---|---|---|---|
| `shoulders_raised` | 0 | 0 | 12 | 0 |
| `slouching` | 1 | 1 | 19 | 0 |
| `trumpet_bell_angle` | 1 | 4 | 13 | 0 |
| `trumpet_cheeks_puffed` | 0 | 0 | 0 | 1 |
| `trumpet_elbows_pinned` | 0 | 0 | 3 | 0 |
| `trumpet_elbows_wide` | 0 | 0 | 1 | 0 |
| `trumpet_head_down` | 2 | 8 | 17 | 1 |
| **All** | **4** | **13** | **65** | **2** |

- Found 4 of 19 keys: `EaTvWPsHDQ8` head down and slouching (53-64 s), `AmpggAjW9bk` head down (21-31 s), and `qFmhhHTn810` bell too low near 300 s (flag 304.1-305.3 s).
- Missed 13: `fnvwOqXv8fs` bell and head down at 56-77, ~150 and ~195 s (6 keys; no flag within 3-5 s of any of them), `qFmhhHTn810` bell at 478-511 s, `Mq-e5iKvIGQ` head down ~84 s, `ZTcrE6iruBc` head down ~12 s and leaning back 4-20 s (three players in frame; the slouching rule flags a forward lean, so that key is only the nearest rule), `EaTvWPsHDQ8` head down ~2 s, `tsyKFlBsqZY` head down ~274 s (the trumpeter is not the tracked person), `z9YjzBBIF78` head down 41-49 s. Six of the 13 are hedged or low-confidence mentions in the reviewed lines; the single-time keys (also fnvwOqXv8fs ~150 and ~195 s) have 5 s slack. Not run 2: `92M9zflsh-M` head down ~400 s (past the 290 s analysed), `k2tBufHUIEg` cheeks puffed 6-24 s (no face reading).
- Extra 65, on 15 videos. Most are on talking heads that the review found to show no posture fault (no hips in frame, so the torso and shoulder rules have little to go on): `1CH0EqpWM6U` has 11 flags (`trumpet_head_down` at 166.5-181.2 s, the stretch the review says frames do not confirm), `KSizitxb9ik` 7, `tsyKFlBsqZY` 6 (two people in frame), `JEzh4lyPriM` 6 (not a trumpet). `shoulders_raised` has no key anywhere and flags 12 times, so it is the least supported rule on this set; `trumpet_head_down` flags 17 extra times for 2 found.
- No flags at all: `92M9zflsh-M`, `z9YjzBBIF78`, `O58aoxi2t64`, `k2tBufHUIEg`. `trumpet_bell_angle`, `trumpet_elbows_pinned` and `trumpet_elbows_wide` are skipped as not_visible in most front-view videos, as the table shows.
- Run time: about 0.4 s per second of video (35 s for the 85 s `KSizitxb9ik`); the 21-video batch took about 30 minutes on the Windows laptop.

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

Fixed trumpet limits apply from the first frame; the baseline rules stay for drift. A frame breaks a rule when it crosses the stricter of the baseline threshold and the fixed limit, so one episode gives one flag (same rule names and output shape). The limits live in `backend/app/form/config.py` (each with its source stat in a comment). Trumpet only; violin is unchanged. Source stats: the "Good-posture statistics (YouTube set)" tables above. Pooled p1/p99 of torso_lean and neck_ratio are inflated (probably cropped hips), so those limits rest on per-video medians and pooled p5/p95.

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

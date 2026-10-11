# testdata/form

Example trumpet-form clips. Audio is not meaningful in any of the posture clips below.

- `good_posture_side.mp4`: 7.05 s, 360x640 @ 29.88 fps, side view. Good-posture example: upright head and torso, trumpet roughly horizontal; contains two takes (maroon shirt, then black jacket) with a pause between. Source: Jameson, 2026-10-11. Audio not meaningful.
  - Expected form result: no flags.
  - Measured (AI off, trumpet): view side (view_ratio 0.6443), 71 of 71 frames tracked, no flags. Skipped rules: trumpet_elbows_pinned (not_for_view), trumpet_cheeks_puffed and trumpet_smile_embouchure (not_visible).
- `bad_posture_side.mp4`: 0.26 s, 360x640 @ 30 fps, side view. Bad-posture example, held and static. Source: Jameson, 2026-10-11. Audio not meaningful.
  - Expected form result: flags for forward head, rounded back, forward lean, and the bell dropped to about waist height.
  - Measured (AI off, trumpet): no flags. At 0.26 s the clip is only 3 sampled frames, too short for view detection ("only 3 usable frames, assuming a front view"; view front, view_ratio null), so the side-view rules never ran. Skipped rules: trumpet_cheeks_puffed and trumpet_smile_embouchure (not_visible). The clip needs to be lengthened, or short clips handled in the pipeline, before it can test the posture rules.

"""Tunable settings for the video form analysis (LLD-4). Starting values from the design; change them here only."""
from pathlib import Path

FORM_ENABLED = True  # kill switch: when False the take runner skips form.run and sets form_status 'none'

# Frame sampling
FPS = 10  # sample rate; falls back to FALLBACK_FPS when the time limit would be exceeded
FALLBACK_FPS = 5
MAX_WIDTH = 640  # frames are scaled down to this width before pose detection
TIME_LIMIT_S = 90  # the whole analysis gives up after this long

# MediaPipe (Tasks API: the legacy mp.solutions API needs numpy<2, which the rest of the backend rules out)
MODELS_DIR = Path(__file__).parent / "models"
POSE_MODEL_FILES = {0: "pose_landmarker_lite.task", 1: "pose_landmarker_full.task", 2: "pose_landmarker_heavy.task"}
POSE_MODEL_COMPLEXITY = 1  # key into POSE_MODEL_FILES; only the full model (1) is shipped in models/
POSE_MODEL_PATH = MODELS_DIR / POSE_MODEL_FILES[POSE_MODEL_COMPLEXITY]
HANDS_MAX = 2
VISIBILITY_MIN = 0.5  # landmarks less visible than this count as missing

# Baseline (the player's own relaxed posture at the start of the take)
BASELINE_SECONDS = 2.0
BASELINE_MIN_FRAMES = 5
DEFAULT_NECK_RATIO = 0.55  # used when there are too few baseline frames
DEFAULT_HEAD_DROP = -0.05

# Rule thresholds: a frame breaks a rule when its measure crosses the threshold
VIOLIN_ELBOW_LOW_DEG = 20  # elbow_angle below this
VIOLIN_ELBOW_HIGH_DEG = 85  # elbow_angle above this
VIOLIN_WRIST_COLLAPSED_DEG = 35  # wrist_bend above this
SHOULDERS_RAISED_RATIO = 0.60  # neck_ratio below this fraction of the baseline (0.75 flagged ordinary playing in testdata/trumpet_video2.mp4; 0.70 flagged a bunched hoodie in testdata/form/take5_ode_form_front.mp4)
SLOUCHING_TORSO_LEAN_DEG = 15  # torso_lean above this
SLOUCHING_FALLBACK_NECK_RATIO = 0.85  # fallback when torso_lean is missing: neck_ratio below this x baseline ...
SLOUCHING_FALLBACK_HEAD_DROP = 0.10  # ... and head_drop above baseline plus this
SLOUCHING_FALLBACK_SPAN = 0.2  # severity span for the fallback, which is judged on neck_ratio (a ratio, not degrees)
TRUMPET_HEAD_DOWN_DROP = 0.15  # head_drop above baseline plus this
TRUMPET_ELBOWS_PINNED_GAP = 0.05  # elbow_gap below this (0.10 flagged gaps of 0.07-0.10 in testdata/form/take5_ode_form_front.mp4)

# Severity spans: how far past its threshold a measure must go for severity 1.0 (angles in degrees, others as ratios)
SEVERITY_SPANS = {
    "violin_elbow_low": 20,
    "violin_elbow_high": 20,
    "violin_wrist_collapsed": 20,
    "shoulders_raised": 0.2,
    "slouching": 20,
    "trumpet_head_down": 0.2,
    "trumpet_elbows_pinned": 0.1,
}

# Turning frames into episodes
MISSING_MAX_FRACTION = 0.7  # a rule is skipped when its measure is missing in more than this share of frames
GAP_CLOSE_S = 0.5  # gaps shorter than this inside a run of bad frames are closed
MIN_EPISODE_S = 1.0  # shorter runs are dropped
TRACKING_QUALITY_MIN = 0.5  # below this share of frames with a tracked person, form_status is 'low_quality'

# Tracking (LLD-4 change 2)
HAND_MODEL_PATH = MODELS_DIR / "hand_landmarker.task"
POSE_LANDMARK_COUNT = 25  # landmarks 0-24 are kept: face, shoulders, arms, hands, hips
HAND_LANDMARK_COUNT = 21
LEFT_WRIST = 15  # pose landmark indices; left and right are the learner's own
RIGHT_WRIST = 16
MAX_NATIVE_FPS = 240  # a container reporting more than this (or 0) has a broken frame rate
FALLBACK_NATIVE_FPS = 30  # frame times come from this rate when the video gives no usable timestamps
TRACKS_FILE_SUFFIX = "_tracks.json"
COORDINATE_DECIMALS = 4  # precision kept when saving landmarks

# Camera check (LLD-4 change 6)
CAMERA_CHECK_MAX_BYTES = 2 * 1024 * 1024  # one JPEG frame from the live camera
CAMERA_MIN_SHOULDER_WIDTH = 0.15  # shoulders narrower than this share of the image width: too small
CAMERA_MIN_BRIGHTNESS = 40  # mean brightness (0-255) below this: too dark

# Bars and links (LLD-4 change 4)
LINK_MIN_TIMING_NOTES = 2  # a bar is linked as late / early when at least this many of its notes are
FORM_FILE_SUFFIX = "_form.json"

# Camera view and side-view rules (LLD-4 change 7)
VIEW_SIDE_MAX = 1.7  # median shoulder width / shoulder-to-nose height below this: the camera sees the player from the side; fit on 3 clips: side 1.36, Ode 1.48, front 1.96
VIEW_MIN_FRAMES = 5  # fewer usable frames than this: the view is 'front'
SIDE_HEAD_PITCH_DELTA = 15  # side view: head_pitch above baseline plus this many degrees
SIDE_NECK_RATIO = 0.70  # side view: neck_side below this fraction of the baseline (set on its own; the front ratio is 0.60)
SIDE_NECK_SPAN_FRACTION = 0.35  # severity span for side shoulders_raised, as a share of the baseline (front: 0.2 of a 0.55 baseline)
SIDE_HEAD_PITCH_SPAN_DEG = 20  # severity span for side trumpet_head_down

# Embouchure checks with the Face Landmarker (LLD-4 change 8)
FACE_ENABLED = True  # when False the face is not checked and no face rule appears in take.form
FACE_MODEL_PATH = MODELS_DIR / "face_landmarker.task"
FACE_MIN_QUALITY = 0.3  # below this share of frames (inside notes) with a face, the face rules are skipped as not_visible
CHEEK_PUFF_MAX = 0.45  # 'cheekPuff' blendshape above this
SMILE_MAX = 0.5  # the larger of 'mouthSmileLeft' and 'mouthSmileRight' above this
FACE_SPAN = 0.4  # severity span for both face rules (blendshape scores)
FACE_CROP_MIN_PX = 160  # the face crop is at least this many pixels on a side
FACE_CROP_SHOULDER_RATIO = 1.2  # front view: crop side = this x shoulder width
FACE_CROP_EAR_RATIO = 4  # side view: crop side = this x the near ear-to-nose distance
SEVERITY_SPANS.update({"trumpet_cheeks_puffed": FACE_SPAN, "trumpet_smile_embouchure": FACE_SPAN})

# Face crop that follows the head (LLD-4 change 9)
FACE_BOX_MARGIN = 2.0  # the crop for the next frame is this x the larger side of the face box last found, centred on it

# Fixed trumpet limits (LLD-4 change 11): they apply from the first frame, alongside the baseline rules, which still catch
# drift during a take (a frame breaks a rule when it crosses the stricter of the two). Each is set just outside the good set
# (testdata/youtube/posture_stats.csv, 51 front and 19 side videos; "Good-posture statistics (YouTube set)" and "Fixed limits
# (change 11)" in testdata/RESULTS_form_runs.md), loose enough for camera angle and body build. The pooled p1/p99 tails of
# torso_lean and neck_ratio are inflated (probably cropped hips), so those limits rest on per-video medians and pooled p5/p95.
TRUMPET_HEAD_DROP_MAX = 0.30  # front head_drop above this: pooled p95 0.17, p99 0.27; median of per-video p99 0.17
TRUMPET_NECK_RATIO_MIN = 0.30  # front neck_ratio below this: pooled p5 0.35 (p1 0.09 is inflated); median of per-video p1 0.46
TRUMPET_HEAD_PITCH_MAX = 40  # side head_pitch above this: pooled p95 37.3 (p99 77.6 is noise); median of per-video p99 27.8
TRUMPET_NECK_SIDE_MIN = 0.04  # side neck_side below this: pooled p5 0.06, p1 0.02; median of per-video p1 0.09
# Torso (back) lean is already fixed: SLOUCHING_TORSO_LEAN_DEG = 15 sits above the median of per-video p99, 8.6 (front torso_lean)
# and 13.2 (side_torso_lean); the pooled p95 (68.9 and 85.6) is inflated, so 15 stays.
TRUMPET_ELBOWS_WIDE_GAP = 1.0  # front elbow_gap (either side) above this: pooled p95 0.78 left / 0.89 right; median of per-video p99 0.75 / 0.84
# Bell angle proxy (see bell_measures.py): the front ratio reads opposite to the side degrees
TRUMPET_BELL_HEIGHT_MIN = -0.55  # front: wrists this far ABOVE the mouth (in shoulder widths) is a bell too high; pooled p1 -0.48
TRUMPET_BELL_HEIGHT_MAX = 2.0  # front: wrists below the mouth by more than this is a bell too low; pooled p99 1.89, p95 1.46
TRUMPET_BELL_ANGLE_MAX = -5  # side: degrees above horizontal, above this is a bell too high; pooled p99 -8.7
TRUMPET_BELL_ANGLE_MIN = -100  # side: below this is a bell too low; pooled p1 -100.1, p5 -93.0
SIDE_BELL_ANGLE_SPAN_DEG = 30  # severity span for the side bell rule (degrees)
SEVERITY_SPANS.update({"trumpet_elbows_wide": 0.5, "trumpet_bell_angle": 0.5})  # front: ratios (the side bell rule has its own span in degrees)

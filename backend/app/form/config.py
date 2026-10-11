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
SHOULDERS_RAISED_RATIO = 0.70  # neck_ratio below this fraction of the baseline (0.75 flagged ordinary playing in testdata/trumpet_video2.mp4)
SLOUCHING_TORSO_LEAN_DEG = 15  # torso_lean above this
SLOUCHING_FALLBACK_NECK_RATIO = 0.85  # fallback when torso_lean is missing: neck_ratio below this x baseline ...
SLOUCHING_FALLBACK_HEAD_DROP = 0.10  # ... and head_drop above baseline plus this
SLOUCHING_FALLBACK_SPAN = 0.2  # severity span for the fallback, which is judged on neck_ratio (a ratio, not degrees)
TRUMPET_HEAD_DOWN_DROP = 0.15  # head_drop above baseline plus this
TRUMPET_ELBOWS_PINNED_GAP = 0.10  # elbow_gap below this

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
VIEW_SIDE_MAX = 1.0  # median shoulder width / shoulder-to-nose height below this: the camera sees the player from the side
VIEW_MIN_FRAMES = 5  # fewer usable frames than this: the view is 'front'
SIDE_HEAD_PITCH_DELTA = 15  # side view: head_pitch above baseline plus this many degrees
SIDE_NECK_RATIO = SHOULDERS_RAISED_RATIO  # side view: neck_side below this fraction of the baseline; kept equal to the front ratio (0.70)
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

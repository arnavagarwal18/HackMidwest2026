"""Synthetic tracks-file frames for the form rule tests: geometry built from the measures we want to see."""
import math

FRAME_S = 0.1
SHOULDER_WIDTH = 0.2
SHOULDER_Y = 0.4
CENTRE_X = 0.5
TORSO_LENGTH = 0.3
HIP_HALF_WIDTH = 0.05
ARM_LENGTH = 0.2
HAND_LENGTH = 0.1
POSE_POINTS = 25
HAND_POINTS = 21
UNUSED = [0.5, 0.5, 1.0]

# A relaxed player: nothing here breaks a rule
RELAXED = {"elbow_angle": 45.0, "neck_ratio": 0.55, "head_drop": -0.05, "torso_lean": 0.0,
           "elbow_gap_left": 0.5, "elbow_gap_right": 0.45, "wrist_bend": 0.0, "hip_visibility": 1.0}


def make_frame(t: float, **overrides) -> dict:
    """One frame whose measures equal RELAXED updated with `overrides`. The right elbow follows elbow_angle unless elbow_gap_right is given."""
    m = {**RELAXED, **overrides}
    pose = [list(UNUSED) for _ in range(POSE_POINTS)]
    left_shoulder, right_shoulder = (CENTRE_X + SHOULDER_WIDTH / 2, SHOULDER_Y), (CENTRE_X - SHOULDER_WIDTH / 2, SHOULDER_Y)
    pose[11], pose[12] = [*left_shoulder, 1.0], [*right_shoulder, 1.0]

    ear_y = SHOULDER_Y - m["neck_ratio"] * SHOULDER_WIDTH
    pose[7], pose[8] = [CENTRE_X + 0.05, ear_y, 1.0], [CENTRE_X - 0.05, ear_y, 1.0]
    pose[0] = [CENTRE_X, ear_y + m["head_drop"] * SHOULDER_WIDTH, 1.0]

    lean = math.radians(m["torso_lean"])
    hip_x, hip_y = CENTRE_X - math.sin(lean) * TORSO_LENGTH, SHOULDER_Y + math.cos(lean) * TORSO_LENGTH
    pose[23] = [hip_x + HIP_HALF_WIDTH, hip_y, m["hip_visibility"]]
    pose[24] = [hip_x - HIP_HALF_WIDTH, hip_y, m["hip_visibility"]]

    swing = math.radians(m["elbow_angle"])  # bow arm (right): upper arm from shoulder 12 at this angle from straight down
    pose[14] = [right_shoulder[0] + ARM_LENGTH * math.sin(swing), SHOULDER_Y + ARM_LENGTH * math.cos(swing), 1.0]
    if "elbow_gap_right" in overrides:
        pose[14][0] = pose[24][0] + m["elbow_gap_right"] * SHOULDER_WIDTH
    pose[13] = [pose[23][0] + m["elbow_gap_left"] * SHOULDER_WIDTH, hip_y - 0.1, 1.0]
    pose[15] = [pose[13][0], pose[13][1] + ARM_LENGTH, 1.0]  # forearm points straight down

    bend = math.radians(m["wrist_bend"])
    wrist = (pose[15][0], pose[15][1])
    left_hand = [[0.5, 0.5] for _ in range(HAND_POINTS)]
    left_hand[0] = [*wrist]
    left_hand[9] = [wrist[0] + HAND_LENGTH * math.sin(bend), wrist[1] + HAND_LENGTH * math.cos(bend)]
    return {"t": t, "pose": pose, "left_hand": left_hand, "right_hand": None}


def timeline(*segments: tuple[float, dict]) -> list[dict]:
    """Frames at FRAME_S spacing from t=0: each segment is (seconds, overrides)."""
    frames = []
    for seconds, overrides in segments:
        for _ in range(round(seconds / FRAME_S)):
            frames.append(make_frame(round(len(frames) * FRAME_S, 6), **overrides))
    return frames

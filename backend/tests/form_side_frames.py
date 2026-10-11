"""Synthetic tracks-file frames seen from the side (and shoulder-ratio frames) for the camera view tests."""
import math

from form_frames import FRAME_S, HAND_POINTS, POSE_POINTS, UNUSED

SIDE_POSE = {"head_pitch": 10.0, "neck_side": 0.12, "torso_lean": 0.0, "bell_angle": -40.0, "near_visibility": 1.0, "far_visibility": 0.3}
WRIST_REACH = 0.3  # mouth to the wrists
NOSE_REACH = 0.08  # ear to nose, so the nose sits well in front of the ear
SHOULDER_Y = 0.4
FAR_SHOULDER_OFFSET = 0.03  # the far shoulder is almost behind the near one


def _blank_pose() -> list[list[float]]:
    return [list(UNUSED) for _ in range(POSE_POINTS)]


def _frame(t: float, pose: list[list[float]]) -> dict:
    return {"t": t, "pose": pose, "left_hand": [[0.5, 0.5] for _ in range(HAND_POINTS)], "right_hand": None}


def ratio_frame(t: float, ratio: float, nose_height: float = 0.1) -> dict:
    """Shoulders `ratio` times as wide as the shoulder-midpoint-to-nose height (square pixels)."""
    pose = _blank_pose()
    pose[11], pose[12] = [0.5 + ratio * nose_height / 2, SHOULDER_Y, 1.0], [0.5 - ratio * nose_height / 2, SHOULDER_Y, 1.0]
    pose[0] = [0.5, SHOULDER_Y - nose_height, 1.0]
    return _frame(t, pose)


def side_frame(t: float, near: str = "left", **overrides) -> dict:
    """A player seen from the left or right: head_pitch (degrees, nose below ear), neck_side (ear to shoulder), torso_lean, bell_angle."""
    m = {**SIDE_POSE, **overrides}
    near_shoulder, far_shoulder = (11, 12) if near == "left" else (12, 11)
    near_ear, near_hip = (7, 23) if near == "left" else (8, 24)
    pose = _blank_pose()
    pose[near_shoulder] = [0.5, SHOULDER_Y, m["near_visibility"]]
    pose[far_shoulder] = [0.5 + FAR_SHOULDER_OFFSET, SHOULDER_Y, m["far_visibility"]]
    ear = [0.5, SHOULDER_Y - m["neck_side"]]
    pose[near_ear] = [*ear, m["near_visibility"]]
    pitch = math.radians(m["head_pitch"])
    pose[0] = [ear[0] + NOSE_REACH * math.cos(pitch), ear[1] + NOSE_REACH * math.sin(pitch), 1.0]
    mouth = pose[0][:2]
    pose[9], pose[10] = [*mouth, 1.0], [*mouth, 1.0]
    bell = math.radians(m["bell_angle"])  # degrees above horizontal, the player facing right
    wrists = [mouth[0] + WRIST_REACH * math.cos(bell), mouth[1] - WRIST_REACH * math.sin(bell), 1.0]
    pose[15], pose[16] = list(wrists), list(wrists)
    lean = math.radians(m["torso_lean"])
    pose[near_hip] = [0.5 - math.sin(lean) * 0.3, SHOULDER_Y + math.cos(lean) * 0.3, m["near_visibility"]]
    return _frame(t, pose)


def frames_of(make, *segments: tuple[float, dict]) -> list[dict]:
    """Frames at FRAME_S spacing from t=0: each segment is (seconds, overrides for `make`)."""
    frames = []
    for seconds, overrides in segments:
        for _ in range(round(seconds / FRAME_S)):
            frames.append(make(round(len(frames) * FRAME_S, 6), **overrides))
    return frames

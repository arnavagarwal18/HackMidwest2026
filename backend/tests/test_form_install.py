from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

from app.form import config

PHOTO = Path(__file__).parent / "fixtures" / "pose_person.jpg"
POSE_LANDMARK_COUNT = 33


def test_pose_model_is_shipped():
    assert config.POSE_MODEL_PATH.is_file()


def test_pose_landmarker_finds_a_person_in_a_photo():
    bgr = cv2.imread(str(PHOTO))
    assert bgr is not None, f"could not read {PHOTO}"
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    options = vision.PoseLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(config.POSE_MODEL_PATH)),
                                           running_mode=vision.RunningMode.IMAGE)
    with vision.PoseLandmarker.create_from_options(options) as landmarker:
        result = landmarker.detect(image)
    assert len(result.pose_landmarks) == 1
    landmarks = result.pose_landmarks[0]
    assert len(landmarks) == POSE_LANDMARK_COUNT
    assert landmarks[0].visibility > config.VISIBILITY_MIN  # the nose


def test_config_defaults():
    assert config.FORM_ENABLED is True
    assert set(config.SEVERITY_SPANS) >= {"violin_elbow_low", "shoulders_raised", "trumpet_elbows_pinned"}
    assert config.FALLBACK_FPS < config.FPS

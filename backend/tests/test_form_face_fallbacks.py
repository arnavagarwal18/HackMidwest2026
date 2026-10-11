"""Face crop that follows the head (LLD-4 change 9): the retries after a failed pose crop, on a stubbed Face Landmarker."""
import numpy as np
import pytest

from app.form import config, face
from app.form.face import FaceReader
from app.form.face_crop import NOSE

WIDTH, HEIGHT = 2000, 1000
NEUTRAL = {"cheekPuff": 0.0, "mouthSmileLeft": 0.0, "mouthSmileRight": 0.0}
NOSE_PX = (800, 400)
BLOCK = 8  # frame pixel (x, y) holds (x // BLOCK, y // BLOCK) so a crop says where it was cut from


def encoded_frame() -> np.ndarray:
    bgr = np.zeros((HEIGHT, WIDTH, 3), np.uint8)
    bgr[:, :, 0] = (np.arange(WIDTH) // BLOCK)[None, :]
    bgr[:, :, 1] = (np.arange(HEIGHT) // BLOCK)[:, None]
    return bgr


def pose_at(nose=NOSE_PX, shoulders_visible=True) -> list:
    pose = [[0.5, 0.5, 1.0] for _ in range(25)]
    pose[NOSE] = [nose[0] / WIDTH, nose[1] / HEIGHT, 1.0]
    visibility = 1.0 if shoulders_visible else 0.0
    pose[11], pose[12] = [(nose[0] + 150) / WIDTH, 0.6, visibility], [(nose[0] - 150) / WIDTH, 0.6, visibility]  # 300 px apart: crop 360 px
    return pose


class ScriptedLandmarker:
    """Answers the n-th detect with answers[n] = (blendshapes or None, face box in the crop or None); records each crop's window."""

    def __init__(self, answers):
        self.answers, self.windows, self.last_box = list(answers), [], None

    def detect(self, rgb):
        height, width = rgb.shape[:2]
        left, top = int(rgb[0, 0, 2]) * BLOCK, int(rgb[0, 0, 1]) * BLOCK
        self.windows.append((left, top, left + width, top + height))
        blendshapes, self.last_box = self.answers[len(self.windows) - 1]
        return blendshapes

    def close(self):
        pass


@pytest.fixture
def reader_with(monkeypatch):
    """A FaceReader (no view known, like a first run) whose landmarker gives `answers`; returns (reader, landmarker)."""
    def build(answers, view=None):
        landmarker = ScriptedLandmarker(answers)
        monkeypatch.setattr(face, "_create_landmarker", lambda: landmarker)
        monkeypatch.setattr(face, "_unavailable", False)
        return FaceReader([{"onset_s": 0.0, "offset_s": 100.0}], view), landmarker
    return build


def read_frames(reader, *poses):
    for index, pose in enumerate(poses):
        reader.read(encoded_frame(), float(index), {"pose": pose})
    return list(reader.result.readings.values())


FACE_FOUND = (NEUTRAL, None)
NO_FACE = (None, None)
WHOLE_FRAME = (0, 0, WIDTH, HEIGHT)


def test_a_pose_crop_with_no_face_is_retried_on_the_last_crop_that_found_a_face(reader_with):
    reader, landmarker = reader_with([FACE_FOUND, NO_FACE, FACE_FOUND])
    readings = read_frames(reader, pose_at(), pose_at(nose=(1400, 700)))  # the nose jumps away from the head
    first_pose_window, pose_window_after_jump, retry_window = landmarker.windows
    assert retry_window == first_pose_window  # no face box known, so the window that worked is tried again
    assert pose_window_after_jump != first_pose_window
    assert all(reading is not None for reading in readings)


def test_a_frame_with_no_pose_crop_is_read_on_the_last_crop_that_found_a_face(reader_with):
    reader, landmarker = reader_with([FACE_FOUND, FACE_FOUND])
    readings = read_frames(reader, pose_at(), None)
    assert landmarker.windows[1] == landmarker.windows[0]
    assert all(reading is not None for reading in readings)


def test_when_the_last_crop_finds_no_face_either_the_whole_frame_is_tried(reader_with):
    reader, landmarker = reader_with([FACE_FOUND, NO_FACE, NO_FACE, FACE_FOUND])
    readings = read_frames(reader, pose_at(), pose_at(nose=(1400, 700)))
    assert landmarker.windows[-1] == WHOLE_FRAME and len(landmarker.windows) == 4
    assert all(reading is not None for reading in readings)


def test_a_first_frame_with_no_pose_crop_goes_straight_to_the_whole_frame(reader_with):
    reader, landmarker = reader_with([FACE_FOUND])
    readings = read_frames(reader, None)
    assert landmarker.windows == [WHOLE_FRAME] and readings[0] is not None


def test_a_first_run_front_crop_that_needs_shoulders_falls_back_for_a_side_clip(reader_with):
    """A first run crops as front; a side clip's shoulders are hidden, so no pose crop exists and the whole frame finds the face."""
    reader, landmarker = reader_with([FACE_FOUND], view=None)
    readings = read_frames(reader, pose_at(shoulders_visible=False))
    assert landmarker.windows == [WHOLE_FRAME] and readings[0] is not None


def test_no_face_anywhere_gives_none_after_trying_every_window_once(reader_with):
    reader, landmarker = reader_with([NO_FACE] * 3)
    readings = read_frames(reader, pose_at())
    assert readings == [None] and len(landmarker.windows) == 2  # the pose crop, then the whole frame (no last crop yet)
    assert len(set(landmarker.windows)) == 2


def test_the_next_frames_crop_is_centred_on_the_face_box_found(reader_with):
    # the pose crop is 360 px (1.2 x 300) from (620, 220); the face box is a 90 x 90 px square at (700-790, 300-390) inside it
    box = ((700 - 620) / 360, (300 - 220) / 360, (790 - 620) / 360, (390 - 220) / 360)
    reader, landmarker = reader_with([(NEUTRAL, box), FACE_FOUND])
    read_frames(reader, pose_at(), None)
    left, top, right, bottom = landmarker.windows[1]
    side = max(config.FACE_BOX_MARGIN * 90, config.FACE_CROP_MIN_PX)
    assert ((left + right) / 2, (top + bottom) / 2) == pytest.approx((745, 345), abs=BLOCK)
    assert (right - left, bottom - top) == pytest.approx((side, side), abs=BLOCK)
    assert landmarker.windows[0] != landmarker.windows[1]


def test_the_remembered_face_box_follows_the_head_from_frame_to_frame(reader_with):
    first_box = (0.4, 0.4, 0.6, 0.6)  # centred in the 360 px pose crop: the head is at the nose
    second_box = (0.7, 0.4, 0.9, 0.6)  # inside the next crop, found to the right of its centre
    reader, landmarker = reader_with([(NEUTRAL, first_box), (NEUTRAL, second_box), FACE_FOUND])
    read_frames(reader, pose_at(), None, None)
    first_window, second_window, third_window = landmarker.windows
    centre = lambda window: ((window[0] + window[2]) / 2, (window[1] + window[3]) / 2)  # noqa: E731
    assert centre(second_window)[0] == pytest.approx(centre(first_window)[0], abs=BLOCK)
    assert centre(third_window)[0] > centre(second_window)[0]  # the crop moved right with the head

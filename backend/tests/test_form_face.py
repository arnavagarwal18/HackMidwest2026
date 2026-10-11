"""Embouchure checks (LLD-4 change 8): the face rules on a stubbed Face Landmarker, the crop, and the failure cases."""
import logging

import numpy as np
import pytest

from app import form, store
from app.form import face
from app.form.rules import analyse
from app.takes.take_store import update_take
from tests.form_frames import make_frame
from tests.form_helpers import add_form_take, make_photo_video

FRAMES = 40  # 4 s at 10 fps
FACE_RULE_NAMES = {"trumpet_cheeks_puffed", "trumpet_smile_embouchure"}
NEUTRAL = {"cheekPuff": 0.0, "mouthSmileLeft": 0.0, "mouthSmileRight": 0.0}


class StubLandmarker:
    """Stands in for the Face Landmarker: `shapes(call_index)` gives the blendshapes of the n-th crop (None: no face)."""

    def __init__(self, shapes):
        self.shapes, self.calls, self.closed = shapes, 0, False

    def detect(self, rgb):
        self.calls += 1
        return self.shapes(self.calls - 1)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def fresh_face_state(monkeypatch):
    monkeypatch.setattr(face, "_unavailable", False)
    monkeypatch.setattr("app.diagnosis.rerank", lambda session_id, take_id: None)


@pytest.fixture
def stub_face(monkeypatch):
    """Install a stub landmarker for form.run and return it."""
    def install(shapes):
        stub = StubLandmarker(shapes)
        monkeypatch.setattr(face, "_create_landmarker", lambda: stub)
        return stub
    return install


@pytest.fixture
def run_form(sessions_root):
    """Run form.run on a 4 s trumpet video whose transcribed notes are `notes` (video seconds); returns the stored take."""
    def run(notes, **take_fields):
        session_id, take_id = add_form_take(instrument="trumpet", form_status="none")
        make_photo_video(store.session_dir(session_id) / f"{take_id}.mp4", frames=FRAMES)
        update_take(session_id, take_id, bar_from=1, bar_to=1, notes=[{"onset_s": a, "offset_s": b} for a, b in notes], **take_fields)
        form.run(session_id, take_id)
        return store.get(session_id).takes[take_id]
    return run


def face_flags(take):
    return [flag for flag in take["form"]["flags"] if flag["rule"] in FACE_RULE_NAMES]


def skipped_face_rules(take):
    return {entry["rule"]: entry["reason"] for entry in take["form"]["rules_skipped"] if entry["rule"] in FACE_RULE_NAMES}


def test_cheek_puff_for_two_seconds_inside_a_note_gives_one_flag(run_form, stub_face):
    stub_face(lambda i: {**NEUTRAL, "cheekPuff": 0.7 if 10 <= i < 30 else 0.1})
    take = run_form([(0.0, 4.0)])
    [flag] = face_flags(take)
    assert (flag["rule"], flag["unit"], flag["direction"], flag["label"]) == (
        "trumpet_cheeks_puffed", "score", "high", "cheeks puffing out")
    assert (flag["start_s"], flag["end_s"]) == (1.0, 3.0)
    assert flag["threshold"] == 0.45 and flag["value"] == pytest.approx(0.7)
    assert flag["severity"] == pytest.approx((0.7 - 0.45) / 0.4)
    assert take["form_status"] == "done" and take["form"]["face_quality"] == 1.0
    assert skipped_face_rules(take) == {}


def test_the_same_values_in_a_gap_between_notes_give_no_flag(run_form, stub_face):
    stub = stub_face(lambda i: {**NEUTRAL, "cheekPuff": 0.7})  # puffed whenever the face is looked at
    take = run_form([(0.0, 0.5), (3.5, 4.0)])  # a breath between two short notes
    assert face_flags(take) == []
    assert stub.calls == 10  # only the frames inside the notes were run, none of the 30 in the gap
    assert take["form"]["face_quality"] == 1.0


def test_a_smile_embouchure_inside_a_note_is_flagged(run_form, stub_face):
    stub_face(lambda i: {**NEUTRAL, "mouthSmileLeft": 0.6, "mouthSmileRight": 0.1})
    take = run_form([(0.0, 4.0)])
    [flag] = face_flags(take)
    assert (flag["rule"], flag["unit"], flag["label"]) == (
        "trumpet_smile_embouchure", "score", "mouth corners pulled back (smile embouchure)")
    assert flag["value"] == pytest.approx(0.6) and flag["threshold"] == 0.5


def test_the_larger_smile_side_counts(run_form, stub_face):
    stub_face(lambda i: {**NEUTRAL, "mouthSmileLeft": 0.2, "mouthSmileRight": 0.8})
    [flag] = face_flags(run_form([(0.0, 4.0)]))
    assert flag["value"] == pytest.approx(0.8)


def test_flags_are_numbered_by_start_time_across_pose_and_face_flags(run_form, stub_face):
    stub_face(lambda i: {**NEUTRAL, "cheekPuff": 0.7 if i >= 20 else 0.0})
    take = run_form([(0.0, 4.0)])
    flags = take["form"]["flags"]
    assert [flag["id"] for flag in flags] == [f"f:{take['take_id']}:{k}" for k in range(1, len(flags) + 1)]
    assert [flag["start_s"] for flag in flags] == sorted(flag["start_s"] for flag in flags)


def test_a_face_in_only_20_percent_of_the_note_frames_skips_both_rules_as_not_visible(run_form, stub_face):
    stub_face(lambda i: {**NEUTRAL, "cheekPuff": 0.9, "mouthSmileLeft": 0.9} if i % 5 == 0 else None)
    take = run_form([(0.0, 4.0)])
    assert take["form"]["face_quality"] == pytest.approx(0.2)
    assert skipped_face_rules(take) == {"trumpet_cheeks_puffed": "not_visible", "trumpet_smile_embouchure": "not_visible"}
    assert face_flags(take) == []
    assert take["form_status"] == "done"


def test_a_face_in_30_percent_of_the_note_frames_is_enough(run_form, stub_face):
    stub_face(lambda i: NEUTRAL if i % 10 < 3 else None)
    take = run_form([(0.0, 4.0)])
    assert take["form"]["face_quality"] == pytest.approx(0.3)
    assert skipped_face_rules(take) == {}


def test_a_take_with_no_notes_runs_no_face_and_skips_both_rules_as_not_visible(run_form, stub_face):
    stub = stub_face(lambda i: NEUTRAL)
    take = run_form([])
    assert stub.calls == 0 and take["form"]["face_quality"] is None
    assert set(skipped_face_rules(take).values()) == {"not_visible"}


def test_a_model_that_cannot_load_skips_both_rules_as_unavailable_and_the_take_is_still_done(run_form, monkeypatch, caplog):
    def cannot_load():
        raise FileNotFoundError("face_landmarker.task")
    monkeypatch.setattr(face, "_create_landmarker", cannot_load)
    with caplog.at_level(logging.ERROR, logger="app.form.face"):
        take = run_form([(0.0, 4.0)])
    assert take["form_status"] == "done" and take["form"]["error"] is None and take["form"]["face_quality"] is None
    assert skipped_face_rules(take) == {"trumpet_cheeks_puffed": "face_unavailable", "trumpet_smile_embouchure": "face_unavailable"}
    assert face_flags(take) == []
    assert len(caplog.records) == 1 and "face_landmarker.task" in caplog.text


def test_a_crash_on_first_use_is_logged_once_and_never_retried_until_restart(run_form, monkeypatch, caplog):
    created = []

    def create():
        created.append(1)
        return StubLandmarker(lambda i: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(face, "_create_landmarker", create)
    with caplog.at_level(logging.ERROR, logger="app.form.face"):
        first = run_form([(0.0, 4.0)])
        second = run_form([(0.0, 4.0)])
    for take in (first, second):
        assert take["form_status"] == "done" and take["form"]["face_quality"] is None
        assert set(skipped_face_rules(take).values()) == {"face_unavailable"}
    assert len(created) == 1
    assert len(caplog.records) == 1 and "boom" in caplog.text


def test_pose_rules_still_run_when_the_face_is_unavailable():
    frames = [make_frame(round(i * 0.1, 3), head_drop=0.3 if 10 <= i < 30 else -0.05) for i in range(40)]
    analysis = analyse(frames, "trumpet", "t1", face=face.FaceResult(unavailable=True))
    assert "trumpet_head_down" in {flag["rule"] for flag in analysis["flags"]}
    assert {entry["reason"] for entry in analysis["rules_skipped"]} == {"face_unavailable"}


def test_face_enabled_false_checks_no_face_and_lists_no_face_rule(run_form, stub_face, monkeypatch):
    stub = stub_face(lambda i: {**NEUTRAL, "cheekPuff": 0.9})
    monkeypatch.setattr("app.form.config.FACE_ENABLED", False)
    take = run_form([(0.0, 4.0)])
    assert stub.calls == 0 and take["form"]["face_quality"] is None
    assert face_flags(take) == [] and skipped_face_rules(take) == {}


def person_pose(nose=(0.5, 0.3), shoulders=((0.4, 0.5), (0.6, 0.5)), ears=((0.45, 0.3), (0.55, 0.3)), visibility=(1.0, 1.0)):
    pose = [[0.5, 0.5, 1.0] for _ in range(25)]
    pose[0] = [*nose, 1.0]
    pose[7], pose[8] = [*ears[0], visibility[0]], [*ears[1], visibility[1]]
    pose[11], pose[12] = [*shoulders[0], 1.0], [*shoulders[1], 1.0]
    return pose


def test_front_view_crops_a_square_of_1_2_shoulder_widths_centred_on_the_nose():
    bgr = np.zeros((1000, 2000, 3), np.uint8)  # shoulders 0.2 of the width apart: 400 px; crop 480 px
    crop = face.crop_face(bgr, person_pose(), "front")
    assert crop.shape[:2] == (480, 480)


def test_a_small_person_gets_the_minimum_crop_and_no_view_means_front():
    bgr = np.zeros((600, 800, 3), np.uint8)  # shoulders 80 px apart: 1.2x is 96 px, raised to 160
    assert face.crop_face(bgr, person_pose(shoulders=((0.45, 0.5), (0.55, 0.5))), None).shape[:2] == (160, 160)


def test_side_view_uses_four_times_the_near_ear_to_nose_distance():
    bgr = np.zeros((1000, 1000, 3), np.uint8)
    pose = person_pose(nose=(0.5, 0.3), ears=((0.4, 0.3), (0.45, 0.3)), visibility=(0.6, 0.9))  # near ear: right, 50 px
    assert face.crop_face(bgr, pose, "side").shape[:2] == (200, 200)


def test_the_crop_is_clipped_to_the_frame():
    bgr = np.zeros((1000, 1000, 3), np.uint8)
    crop = face.crop_face(bgr, person_pose(nose=(0.02, 0.5)), "front")
    assert crop.shape[0] == 240 and crop.shape[1] < 240


def test_no_crop_without_a_pose():
    assert face.crop_face(np.zeros((1000, 1000, 3), np.uint8), None, "front") is None


def test_front_view_needs_both_shoulders_visible():
    pose = person_pose()
    pose[11][2] = 0.1
    assert face.crop_face(np.zeros((1000, 1000, 3), np.uint8), pose, "front") is None


def test_side_view_needs_an_ear_visible():
    assert face.crop_face(np.zeros((1000, 1000, 3), np.uint8), person_pose(visibility=(0.1, 0.1)), "side") is None

"""form.run: the whole check on a video take, its failures, the diagnosis re-rank, and reading flags."""
import json
import logging
import sys

import cv2
import numpy as np
import pytest

from app import form, store
from app.errors import AppError
from app.form import config, runner, track
from app.takes.take_store import update_take
from tests.form_helpers import add_form_take, make_photo_video

GRID = {"kind": "metronome", "offset_s": 1.0, "sec_per_beat": 1.0}
BARS = [{"bar": n, "start_beat": 4.0 * (n - 1), "beats": 4.0, "notes": []} for n in range(1, 5)]
FLAG = {"id": "f:t1:1", "rule": "slouching", "label": "Slouching", "start_s": 5.2, "end_s": 9.5, "bars": [], "linked": []}
ANALYSIS = {"view": "side", "view_ratio": 0.42, "baseline": {"neck_ratio": 0.55, "head_drop": -0.05}, "rules_skipped": [{"rule": "x", "reason": "not_visible"}],
            "flags": [FLAG]}


def diagnosis_with_rushing_bar_2(cant_tell=False):
    bars = [{"id": f"b:t1:{n}", "bar": n, "wrong": 0, "missed": 0, "extra": 0, "drift": "rushing" if n == 2 else "steady"}
            for n in range(1, 5)]
    return {"grid": GRID, "cant_tell": cant_tell, "bars": bars, "notes": [], "extras": []}


@pytest.fixture
def video_take(sessions_root):
    """A trumpet session with a score of 4 bars and a video take t1 (a person in view) that has a diagnosis."""
    session_id, take_id = add_form_take(instrument="trumpet", form_status="none")
    folder = store.session_dir(session_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "score.json").write_text(json.dumps({"bars": BARS}), encoding="utf-8")
    update_take(session_id, take_id, bar_from=1, bar_to=4, diagnosis=diagnosis_with_rushing_bar_2())
    make_photo_video(folder / "t1.mp4")
    return session_id, take_id


@pytest.fixture
def reranks(monkeypatch):
    calls = []
    monkeypatch.setattr("app.diagnosis.rerank", lambda session_id, take_id: calls.append((session_id, take_id)))
    return calls


@pytest.fixture
def judged(monkeypatch):
    monkeypatch.setattr(runner, "analyse", lambda *args, **kwargs: json.loads(json.dumps(ANALYSIS)))


def stored(session_id, take_id="t1"):
    return store.get(session_id).takes[take_id]


def test_run_saves_flags_on_bars_with_links_then_reranks_once(video_take, judged, reranks):
    session_id, take_id = video_take
    form.run(session_id, take_id)
    take = stored(session_id)
    saved = take["form"]
    assert take["form_status"] == "done"
    assert (saved["error"], saved["frames_total"], saved["tracking_quality"]) == (None, 12, 1.0)
    assert saved["baseline"] == ANALYSIS["baseline"] and saved["rules_skipped"] == ANALYSIS["rules_skipped"]
    assert (saved["view"], saved["view_ratio"]) == ("side", 0.42)
    assert saved["flags"][0]["bars"] == [2, 3]
    assert saved["flags"][0]["linked"] == [{"kind": "rushing", "bar": 2, "ids": ["b:t1:2"]}]
    assert "warning" not in saved
    assert reranks == [(session_id, take_id)]
    folder = store.session_dir(session_id)
    assert json.loads((folder / "t1_form.json").read_text(encoding="utf-8")) == saved
    assert (folder / "t1_tracks.json").is_file()


def test_run_hands_the_video_size_and_instrument_to_the_rules(video_take, reranks, monkeypatch):
    session_id, take_id = video_take
    seen = {}

    def fake_analyse(frames, instrument, take, width=None, height=None, face=None):
        seen.update(instrument=instrument, take=take, width=width, height=height, frames=len(frames))
        return ANALYSIS

    monkeypatch.setattr(runner, "analyse", fake_analyse)
    form.run(session_id, take_id)
    assert (seen["instrument"], seen["take"], seen["frames"]) == ("trumpet", "t1", 12)
    assert seen["width"] > 0 and seen["height"] > 0


def test_a_take_without_a_usable_grid_still_shows_flags_with_no_bars_and_reranks(video_take, judged, reranks):
    session_id, take_id = video_take
    update_take(session_id, take_id, diagnosis=diagnosis_with_rushing_bar_2(cant_tell=True))
    form.run(session_id, take_id)
    flag = stored(session_id)["form"]["flags"][0]
    assert (flag["bars"], flag["linked"], flag["start_s"]) == ([], [], 5.2)
    assert stored(session_id)["form_status"] == "done"
    assert len(reranks) == 1


def test_a_take_without_a_diagnosis_gets_flags_with_no_bars(video_take, judged, reranks):
    session_id, take_id = video_take
    update_take(session_id, take_id, diagnosis=None)
    form.run(session_id, take_id)
    assert stored(session_id)["form"]["flags"][0]["bars"] == []


def test_a_corrupt_video_is_video_unreadable(video_take, reranks):
    session_id, take_id = video_take
    (store.session_dir(session_id) / "t1.mp4").write_bytes(b"not a video")
    form.run(session_id, take_id)
    take = stored(session_id)
    assert take["form_status"] == "failed"
    assert take["form"]["error"] == {"code": "video_unreadable", "message": "Could not read the video frames."}
    assert take["form"]["flags"] == []
    assert len(reranks) == 1


def test_a_black_video_is_tracking_poor_with_no_flags(video_take, reranks):
    session_id, take_id = video_take
    path = store.session_dir(session_id) / "t1.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
    for _ in range(12):
        writer.write(np.zeros((240, 320, 3), np.uint8))
    writer.release()
    form.run(session_id, take_id)
    take = stored(session_id)
    assert take["form_status"] == "failed"
    assert take["form"]["error"] == {"code": "tracking_poor", "message": "We could not see you clearly in most of the video."}
    assert (take["form"]["flags"], take["form"]["frames_tracked"], take["form"]["tracking_quality"]) == ([], 0, 0.0)


def test_mediapipe_failing_to_load_is_form_unavailable(video_take, reranks, monkeypatch, tmp_path):
    session_id, take_id = video_take
    monkeypatch.setattr(config, "POSE_MODEL_PATH", tmp_path / "missing.task")
    form.run(session_id, take_id)
    take = stored(session_id)
    assert take["form_status"] == "failed"
    assert take["form"]["error"] == {"code": "form_unavailable", "message": "Form check unavailable on this computer."}


def test_an_unexpected_exception_is_form_failed_and_logged_with_the_take(video_take, reranks, monkeypatch, caplog):
    session_id, take_id = video_take

    def explode(*args, **kwargs):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(runner, "analyse", explode)
    form.run(session_id, take_id)  # must not raise
    take = stored(session_id)
    assert take["form_status"] == "failed"
    assert take["form"]["error"] == {"code": "form_failed", "message": "Form check failed on this take."}
    assert f"{session_id}/{take_id}" in caplog.text
    assert "injected failure" in caplog.text and "Traceback" in caplog.text


def test_failures_leave_the_notes_and_the_take_status_alone(video_take, reranks, monkeypatch):
    session_id, take_id = video_take
    update_take(session_id, take_id, status="diagnosed", error=None)
    before = stored(session_id)["diagnosis"]
    monkeypatch.setattr(runner, "analyse", lambda *args, **kwargs: 1 / 0)
    form.run(session_id, take_id)
    take = stored(session_id)
    assert (take["status"], take["error"], take["diagnosis"]) == ("diagnosed", None, before)


def test_a_run_past_the_time_limit_keeps_what_was_checked_with_a_partial_warning(video_take, reranks, monkeypatch):
    session_id, take_id = video_take
    real_track_video = track.track_video
    ticks = iter(range(100))  # a fake clock: one tick per look at the time, so the limit hits after a few frames
    monkeypatch.setattr(track, "track_video", lambda path, with_hands, on_frame=None: real_track_video(
        path, with_hands, time_limit_s=3, clock=lambda: next(ticks), on_frame=on_frame))
    form.run(session_id, take_id)
    take = stored(session_id)
    assert take["form_status"] == "done"
    assert take["form"]["warning"].startswith("partial: first ")
    assert 0 < take["form"]["frames_total"] < 12


def test_a_run_that_fits_the_limit_has_no_warning_key(video_take, judged, reranks):
    session_id, take_id = video_take
    form.run(session_id, take_id)
    assert "warning" not in stored(session_id)["form"]


def test_run_never_raises_when_the_result_cannot_be_saved(video_take, reranks, monkeypatch, caplog):
    session_id, take_id = video_take

    def cannot_save(*args, **kwargs):
        raise AppError(500, "storage_error", "disk full")

    monkeypatch.setattr(runner, "save_form", cannot_save)
    form.run(session_id, take_id)
    take = stored(session_id)
    assert (take["form_status"], take["form"]["error"]["code"]) == ("failed", "form_failed")
    assert "Could not save the form check" in caplog.text


def test_run_never_raises_for_an_unknown_take(sessions_root, reranks, caplog):
    session_id = store.create("trumpet").session_id
    form.run(session_id, "t9")
    assert "t9" in caplog.text


def test_a_missing_diagnosis_rerank_is_skipped_with_a_warning(video_take, judged, monkeypatch, caplog):
    session_id, take_id = video_take
    monkeypatch.delattr("app.diagnosis.rerank")
    with caplog.at_level(logging.WARNING):
        form.run(session_id, take_id)
    assert stored(session_id)["form_status"] == "done"
    assert "app.diagnosis.rerank is not available" in caplog.text


def test_a_diagnosis_module_that_cannot_be_imported_does_not_break_run(video_take, judged, monkeypatch):
    session_id, take_id = video_take
    monkeypatch.setitem(sys.modules, "app.diagnosis", None)
    form.run(session_id, take_id)
    assert stored(session_id)["form_status"] == "done"


def test_a_failing_rerank_is_logged_and_does_not_fail_the_form(video_take, judged, monkeypatch, caplog):
    session_id, take_id = video_take

    def broken_rerank(*args):
        raise RuntimeError("rerank broke")

    monkeypatch.setattr("app.diagnosis.rerank", broken_rerank)
    form.run(session_id, take_id)
    assert stored(session_id)["form_status"] == "done"
    assert "Re-ranking take" in caplog.text


def test_get_flags_and_get_flag(video_take, judged, reranks):
    session_id, take_id = video_take
    assert form.get_flags(session_id, take_id) == []  # before the check has run
    form.run(session_id, take_id)
    flags = form.get_flags(session_id, take_id)
    assert [f["id"] for f in flags] == ["f:t1:1"]
    assert form.get_flag(session_id, "f:t1:1") == flags[0]


@pytest.mark.parametrize("flag_id", ["f:t1:9", "f:t9:1", "n:t1:1:1", "f:t1", "nonsense"])
def test_get_flag_is_none_for_an_unknown_flag(video_take, judged, reranks, flag_id):
    session_id, _ = video_take
    form.run(session_id, "t1")
    assert form.get_flag(session_id, flag_id) is None


def test_get_flag_is_none_for_an_unknown_session(sessions_root):
    assert form.get_flag("nosuchsession", "f:t1:1") is None


def test_get_flags_raises_not_found_for_an_unknown_take(video_take):
    session_id, _ = video_take
    with pytest.raises(AppError) as caught:
        form.get_flags(session_id, "t9")
    assert caught.value.code == "take_not_found"

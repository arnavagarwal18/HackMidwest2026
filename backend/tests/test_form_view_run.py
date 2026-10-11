"""form.run saves the camera view in take.form, for side takes, front takes and takes that could not be analysed."""
import json

import pytest
from form_side_frames import frames_of, ratio_frame, side_frame

from app import form, store
from app.form import runner
from app.form.track import TrackResult
from app.takes.take_store import update_take
from tests.form_helpers import add_form_take

BARS = [{"bar": n, "start_beat": 4.0 * (n - 1), "beats": 4.0, "notes": []} for n in range(1, 5)]


@pytest.fixture
def trumpet_take(sessions_root, monkeypatch):
    """A trumpet video take whose tracking is replaced by the frames a test sets with `track(frames)`."""
    monkeypatch.setattr("app.diagnosis.rerank", lambda session_id, take_id: None)
    session_id, take_id = add_form_take(instrument="trumpet", form_status="none")
    folder = store.session_dir(session_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "score.json").write_text(json.dumps({"bars": BARS}), encoding="utf-8")
    update_take(session_id, take_id, bar_from=1, bar_to=4)

    def track(frames):
        monkeypatch.setattr(runner, "track_take", lambda *_: TrackResult(fps=10.0, width=640, height=480, frames=frames))
        form.run(session_id, take_id)
        return store.get(session_id).takes[take_id]

    return track


def test_a_side_take_saves_view_side_and_its_ratio(trumpet_take):
    take = trumpet_take(frames_of(side_frame, (2.0, {}), (2.0, {"head_pitch": 30.0})))
    saved = take["form"]
    assert take["form_status"] == "done"
    assert saved["view"] == "side" and 0 < saved["view_ratio"] < 1.0
    assert [flag["rule"] for flag in saved["flags"]] == ["trumpet_head_down"]
    assert {"rule": "trumpet_elbows_pinned", "reason": "not_for_view"} in saved["rules_skipped"]


def test_a_front_take_saves_view_front_and_its_ratio(trumpet_take):
    saved = trumpet_take(frames_of(ratio_frame, (3.0, {"ratio": 2.0})))["form"]
    assert saved["view"] == "front" and saved["view_ratio"] == pytest.approx(2.0 * 640 / 480, abs=1e-3)  # pixels: x is stretched by width / height


def test_a_take_that_could_not_be_tracked_reads_as_front_with_no_ratio(trumpet_take):
    untracked = [{"t": i * 0.1, "pose": None, "left_hand": None, "right_hand": None} for i in range(10)]
    saved = trumpet_take(untracked)["form"]
    assert saved["error"]["code"] == "tracking_poor"
    assert (saved["view"], saved["view_ratio"]) == ("front", None)

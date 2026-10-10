"""form.run on the real trumpet videos in testdata/ (about a minute of 1080p each): no false flags, and within the time budget.

The acted take (shoulders raised, slouching, head down, elbows pinned, about 3 s each) is recorded by Xavier; its expected
times go in testdata/form_expectations.json, and its test skips until the video and those times are there.
"""
import json
import shutil
import time
from pathlib import Path

import pytest

from app import form, store
from app.takes.take_store import update_take
from tests.form_helpers import add_form_take

TESTDATA = Path(__file__).parents[2] / "testdata"
EXPECTATIONS = json.loads((TESTDATA / "form_expectations.json").read_text(encoding="utf-8"))
TOLERANCE_S = EXPECTATIONS["flag_time_tolerance_s"]
MAX_RUNTIME_S = EXPECTATIONS["max_runtime_s_for_60s_video"]
SCORE_BARS = [{"bar": n, "start_beat": 4.0 * (n - 1), "beats": 4.0, "notes": []} for n in range(1, 5)]
BUDGET_VIDEO_S = 60  # the time budget is for a video this long; a longer one gets it in proportion


def _acted_params() -> list:
    params = []
    for acted in EXPECTATIONS["acted"]:
        recorded = (TESTDATA / acted["file"]).exists()
        timed = all(problem["start_s"] is not None and problem["end_s"] is not None for problem in acted["problems"])
        reason = f"{acted['file']} is not recorded yet" if not recorded else "its problem times are not in form_expectations.json"
        params.append(pytest.param(acted, id=acted["file"], marks=pytest.mark.skipif(not (recorded and timed), reason=reason)))
    return params


@pytest.fixture
def analysed(sessions_root, monkeypatch):
    """A function that runs form.run on a testdata video as a trumpet take and returns (the stored take, seconds it took)."""
    monkeypatch.setattr("app.diagnosis.rerank", lambda session_id, take_id: None)

    def analyse_video(filename: str):
        session_id, take_id = add_form_take(instrument=EXPECTATIONS["instrument"], form_status="none")
        folder = store.session_dir(session_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "score.json").write_text(json.dumps({"bars": SCORE_BARS}), encoding="utf-8")
        update_take(session_id, take_id, bar_from=1, bar_to=len(SCORE_BARS))
        shutil.copy(TESTDATA / filename, folder / f"{take_id}.mp4")
        started = time.monotonic()
        form.run(session_id, take_id)
        return store.get(session_id).takes[take_id], time.monotonic() - started

    return analyse_video


def _time_budget_s(take: dict) -> float:
    video_s = take["form"]["frames_total"] / take["form"]["fps_sampled"]
    return MAX_RUNTIME_S * max(1.0, video_s / BUDGET_VIDEO_S)


@pytest.mark.parametrize("entry", EXPECTATIONS["good_form"], ids=lambda entry: entry["file"])
def test_good_form_take_has_no_flags_and_is_fast_enough(analysed, entry):
    if not (TESTDATA / entry["file"]).exists():
        pytest.skip(f"{entry['file']} is not in testdata/")
    take, seconds = analysed(entry["file"])
    assert take["form_status"] == "done", take["form"]["error"]
    assert take["form"]["flags"] == [], take["form"]["flags"]
    print(f"{entry['file']}: analysed in {seconds:.1f} s (budget {_time_budget_s(take):.0f} s)")
    assert seconds < _time_budget_s(take)


@pytest.mark.parametrize("acted", _acted_params())
def test_each_acted_problem_is_flagged_when_it_was_acted(analysed, acted):
    take, seconds = analysed(acted["file"])
    assert take["form_status"] == "done", take["form"]["error"]
    flags = take["form"]["flags"]
    for problem in acted["problems"]:
        near = [flag for flag in flags if flag["rule"] == problem["rule"]
                and abs(flag["start_s"] - problem["start_s"]) <= TOLERANCE_S
                and abs(flag["end_s"] - problem["end_s"]) <= TOLERANCE_S]
        assert near, f"{problem} not flagged within {TOLERANCE_S} s; flags: {[(f['rule'], f['start_s'], f['end_s']) for f in flags]}"
    assert seconds < _time_budget_s(take)

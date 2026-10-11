"""The practice loop on the real pipeline, with AI off: scan the sheet, upload the take, then practise bars 7-8 three times.

Real homr scan, real transcription and diagnosis, nothing mocked. The real take plays bars 7-8 far off the grid, so the
reps are that take's own notes re-timed onto their expected onsets (tests/rep_retime.py); they pass the 50 ms mark.
Skipped when the testdata or the heavy dependencies are missing.
"""
import time
from pathlib import Path

import pytest

TESTDATA = Path(__file__).parents[2] / "testdata"
SHEET, VIDEO = TESTDATA / "trumpet_video1_sheet.webp", TESTDATA / "trumpet_video1.mp4"
HEAVY_MODULES = ("homr", "librosa", "soundfile", "imageio_ffmpeg", "cv2")

EXERCISE_ID = "ex1"  # bars 7-8, the take's top tier-1 problem since r4 (second before)
EXERCISE_SETTINGS = {"bar_from": 7, "bar_to": 8, "start_bpm": 62, "target_bpm": 90, "step_bpm": 4, "reps_to_pass": 2}
PASS_MARK = {"max_errors": 0, "max_mean_timing_ms": 50, "form_rule": None}
START_BPM, STEPPED_BPM = 62, 66
SCAN_TIMEOUT_S, TAKE_TIMEOUT_S, POLL_S = 300, 600, 1.0
REP_RESULT_LIMIT_S, REP_POLL_S = 10, 0.1
TAKE_BARS = (1, 8)


def skip_unless_ready() -> None:
    missing = [path.name for path in (SHEET, VIDEO) if not path.is_file()]
    if missing:
        pytest.skip(f"test data missing from {TESTDATA}: {', '.join(missing)}")
    for module in HEAVY_MODULES:
        pytest.importorskip(module, reason=f"heavy dependency {module} is not installed")


@pytest.fixture
def client(tmp_path, monkeypatch):
    skip_unless_ready()
    from fastapi.testclient import TestClient

    from app import store
    from app.agents import config as agents_config
    from app.main import app

    monkeypatch.setattr(store, "SESSIONS_ROOT", tmp_path / "sessions")
    monkeypatch.setenv("AI_ENABLED", "false")
    agents_config.get_settings.cache_clear()
    store._sessions.clear()
    yield TestClient(app, raise_server_exceptions=False)
    store._sessions.clear()
    agents_config.get_settings.cache_clear()


def poll(client, route: str, settled, timeout_s: float, poll_s: float = POLL_S) -> dict:
    deadline = time.monotonic() + timeout_s
    while True:
        response = client.get(route)
        assert response.status_code == 200, f"GET {route}: {response.status_code} {response.text}"
        if settled(response.json()):
            return response.json()
        if time.monotonic() >= deadline:
            pytest.fail(f"GET {route} still not settled after {timeout_s} s: {response.text[:300]}")
        time.sleep(poll_s)


def scan_and_confirm(client) -> tuple[str, float]:
    session_id = client.post("/sessions", json={"instrument": "trumpet"}).json()["session_id"]
    posted = client.post(f"/sessions/{session_id}/score/photo", files={"file": (SHEET.name, SHEET.read_bytes(), "image/webp")})
    assert posted.status_code == 202, posted.text
    scanned = poll(client, f"/sessions/{session_id}/score/status", lambda body: body["score_status"] != "scanning", SCAN_TIMEOUT_S)
    assert scanned["score_status"] == "scanned", scanned
    confirmed = client.post(f"/sessions/{session_id}/score/confirm")
    assert confirmed.status_code == 200, confirmed.text
    return session_id, confirmed.json()["tempo_bpm"]


def upload_take(client, session_id: str, tempo_bpm: float) -> str:
    form = {"kind": "video", "source": "uploaded", "bar_from": TAKE_BARS[0], "bar_to": TAKE_BARS[1],
            "tempo_bpm": tempo_bpm, "count_in_beats": 0}
    posted = client.post(f"/sessions/{session_id}/takes", data={k: str(v) for k, v in form.items()},
                         files={"file": (VIDEO.name, VIDEO.read_bytes(), "video/mp4")})
    assert posted.status_code == 202, posted.text
    take_id = posted.json()["take_id"]
    settled = poll(client, f"/sessions/{session_id}/takes/{take_id}/analysis",
                   lambda a: a["status"] in ("done", "failed") and a["form_status"] in ("done", "failed", "none"), TAKE_TIMEOUT_S)
    assert settled["status"] == "done", settled["error"]
    return take_id


def play_rep(client, session_id: str, rep_wav: Path) -> tuple[dict, dict, float]:
    """Upload one rep; returns what the upload answered, the settled RepResult and the seconds it took to settle."""
    started = time.monotonic()
    posted = client.post(f"/sessions/{session_id}/exercises/{EXERCISE_ID}/reps", data={"kind": "mic", "source": "uploaded"},
                         files={"file": (rep_wav.name, rep_wav.read_bytes(), "audio/wav")})
    assert posted.status_code == 202, posted.text
    accepted = posted.json()
    result = poll(client, f"/sessions/{session_id}/exercises/{EXERCISE_ID}/reps/{accepted['rep_id']}",
                  lambda rep: rep["status"] != "processing", REP_RESULT_LIMIT_S, REP_POLL_S)
    return accepted, result, time.monotonic() - started


def test_two_passes_step_the_tempo_up_and_the_third_rep_runs_at_the_new_tempo(client, tmp_path):
    from app import store
    from tests.rep_retime import retimed_rep_wav

    session_id, tempo_bpm = scan_and_confirm(client)
    take_id = upload_take(client, session_id, tempo_bpm)

    exercise = client.get(f"/sessions/{session_id}/exercises/{EXERCISE_ID}").json()
    assert {key: exercise["exercise"][key] for key in EXERCISE_SETTINGS} == EXERCISE_SETTINGS, exercise["exercise"]
    assert exercise["exercise"]["pass_mark"] == PASS_MARK, exercise["exercise"]["pass_mark"]
    assert exercise["state"]["current_bpm"] == START_BPM, exercise["state"]

    rep_wav = retimed_rep_wav(store.session_dir(session_id), take_id, EXERCISE_SETTINGS["bar_from"], EXERCISE_SETTINGS["bar_to"],
                              tmp_path / "rep.wav")

    first_accepted, first, first_s = play_rep(client, session_id, rep_wav)
    assert first_accepted["tempo_bpm"] == START_BPM
    assert first["status"] == "scored" and first["passed"] is True, first
    assert first["streak"] == 1 and first["next_bpm"] == START_BPM, first

    second_accepted, second, second_s = play_rep(client, session_id, rep_wav)
    assert second_accepted["tempo_bpm"] == START_BPM
    assert second["status"] == "scored" and second["passed"] is True, second
    assert second["next_bpm"] == STEPPED_BPM and second["streak"] == 0, second
    state = client.get(f"/sessions/{session_id}/exercises/{EXERCISE_ID}").json()["state"]
    assert state["current_bpm"] == STEPPED_BPM and state["best_passed_bpm"] == START_BPM, state

    third_accepted, third, third_s = play_rep(client, session_id, rep_wav)
    assert third_accepted["tempo_bpm"] == STEPPED_BPM and third["tempo_bpm"] == STEPPED_BPM, (third_accepted, third)
    assert third["status"] in ("scored", "not_counted", "failed"), third

    for seconds in (first_s, second_s, third_s):
        assert seconds < REP_RESULT_LIMIT_S, f"a rep took {seconds:.1f} s to come back"

"""The whole trumpet flow through the real FastAPI app, with AI off, so the seams between modules get exercised.

Slow (real homr scans, real transcription and pose tracking), so it only runs with RUN_E2E=1:

    RUN_E2E=1 .venv/bin/python -m pytest tests/test_e2e_trumpet_flow.py -q -s

The steps are tests that run in file order and share one flow; a step whose input step failed is skipped. Each step
prints how long it took. Nothing is mocked and nothing needs AWS: AI_ENABLED=false makes the Score reader, the Feedback
agents and the Instructor use their deterministic fallbacks.
"""
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import store
from app.agents import config as agents_config
from app.main import app

TESTDATA = Path(__file__).parents[2] / "testdata"
MAIN_SHEET, MAIN_VIDEO = "trumpet_video1_sheet.webp", "trumpet_video1.mp4"
EXTRA_SHEETS = ("ode_to_joy_photo.jpg", "trumpet_video2_sheet.webp")
SCAN_TIMEOUT_S, TAKE_TIMEOUT_S, POLL_S = 300, 600, 1.0
FEEDBACK_TAKE_BARS = 8
FORM_SETTLED = ("done", "failed", "none")
IMAGE_TYPES = {".webp": "image/webp", ".jpg": "image/jpeg"}

pytestmark = pytest.mark.skipif(os.environ.get("RUN_E2E") != "1", reason="set RUN_E2E=1 to run the end-to-end trumpet flow")


class Flow:
    """What the steps share: the HTTP client, the main session and take, and every step's timing."""

    def __init__(self, client: TestClient):
        self.client = client
        self.session_id: str | None = None
        self.score: dict | None = None
        self.tempo_bpm: float | None = None
        self.take_id: str | None = None
        self.analysis: dict | None = None
        self.feedback: dict | None = None

    def need(self, value, what: str):
        if value is None:
            pytest.skip(f"needs {what}, which an earlier step did not produce")
        return value

    def create_session(self) -> str:
        response = self.client.post("/sessions", json={"instrument": "trumpet"})
        assert response.status_code == 201, response.text
        assert response.json()["instrument"] == "trumpet"
        return response.json()["session_id"]

    def scan(self, session_id: str, sheet: str) -> dict:
        path = TESTDATA / sheet
        posted = self.client.post(f"/sessions/{session_id}/score/photo",
                                  files={"file": (path.name, path.read_bytes(), IMAGE_TYPES[path.suffix])})
        assert posted.status_code == 202, posted.text
        assert posted.json() == {"score_status": "scanning"}
        return self.poll(f"/sessions/{session_id}/score/status", lambda b: b["score_status"] != "scanning", SCAN_TIMEOUT_S)

    def poll(self, route: str, settled, timeout_s: float) -> dict:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            response = self.client.get(route)
            assert response.status_code == 200, f"GET {route}: {response.status_code} {response.text}"
            if settled(response.json()):
                return response.json()
            time.sleep(POLL_S)
        pytest.fail(f"GET {route} still not settled after {timeout_s} s: {json.dumps(response.json())[:300]}")


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    patch.setattr(store, "SESSIONS_ROOT", tmp_path_factory.mktemp("e2e") / "sessions")
    patch.setenv("AI_ENABLED", "false")
    agents_config.get_settings.cache_clear()
    store._sessions.clear()
    yield Flow(TestClient(app, raise_server_exceptions=False))
    store._sessions.clear()
    agents_config.get_settings.cache_clear()
    patch.undo()


@pytest.fixture(autouse=True)
def timed(request):
    started = time.monotonic()
    yield
    print(f"\n[step time] {request.node.name}: {time.monotonic() - started:.1f} s")


def test_1_create_session(flow):
    flow.session_id = flow.create_session()
    got = flow.client.get(f"/sessions/{flow.session_id}")
    assert got.status_code == 200, got.text
    assert got.json()["score_status"] == "none"
    assert got.json()["take_ids"] == []


def test_2a_photo_scan_confirms_the_main_score(flow):
    session_id = flow.need(flow.session_id, "a session")
    status = flow.scan(session_id, MAIN_SHEET)
    print("scan status:", json.dumps(status))
    assert status["score_status"] == "scanned", status
    assert status["bars"] and status["bars"] > 0

    confirmed = flow.client.post(f"/sessions/{session_id}/score/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["bars"] == status["bars"]
    flow.tempo_bpm = confirmed.json()["tempo_bpm"]
    flow.score = flow.client.get(f"/sessions/{session_id}/score", params={"format": "json"}).json()
    assert len(flow.score["bars"]) == status["bars"]
    assert flow.score["bars"][0]["notes"], "bar 1 has no notes"
    assert flow.client.get(f"/sessions/{session_id}").json()["score_status"] == "confirmed"


@pytest.mark.parametrize("sheet", EXTRA_SHEETS)
def test_2b_other_photos_scan(flow, sheet):
    session_id = flow.create_session()
    status = flow.scan(session_id, sheet)
    print(f"{sheet}: {json.dumps(status)}")
    assert status["score_status"] == "scanned", status
    assert status["bars"] and status["bars"] > 0


def test_3_video_take_runs_the_whole_pipeline(flow):
    session_id = flow.need(flow.session_id, "a session")
    score = flow.need(flow.score, "a confirmed score")
    video = TESTDATA / MAIN_VIDEO
    form = {"kind": "video", "source": "uploaded", "bar_from": 1, "bar_to": min(len(score["bars"]), FEEDBACK_TAKE_BARS),
            "tempo_bpm": flow.tempo_bpm, "count_in_beats": 0}
    posted = flow.client.post(f"/sessions/{session_id}/takes", data={k: str(v) for k, v in form.items()},
                              files={"file": (video.name, video.read_bytes(), "video/mp4")})
    assert posted.status_code == 202, posted.text
    assert posted.json()["status"] == "processing"
    flow.take_id = posted.json()["take_id"]

    route = f"/sessions/{session_id}/takes/{flow.take_id}/analysis"
    settled = flow.poll(route, lambda a: a["status"] in ("done", "failed") and a["form_status"] in FORM_SETTLED,
                        TAKE_TIMEOUT_S)
    flow.analysis = settled
    print("form flags:", json.dumps(settled["form"])[:300])
    print("analysis:", {k: settled[k] for k in ("status", "error", "alignment_quality", "form_status", "calibrated",
                                                 "cant_tell", "tempo")})

    assert settled["status"] == "done", settled["error"]  # transcription + diagnosis + feedback finished
    assert settled["notes"], "transcription and diagnosis produced no note results"
    assert settled["alignment_quality"] is not None
    assert settled["problems"], "diagnosis found no problems on a take that is known to have some"
    assert settled["tempo"]["played_bpm"] and settled["tempo"]["target_bpm"]
    assert settled["calibrated"] in (True, False)  # these videos hold no reference notes, so False is expected
    assert isinstance(settled["form"], list), "form flags are a list"
    assert settled["form_status"] == "done", settled["form_status"]

    tracks = flow.client.get(f"/sessions/{session_id}/takes/{flow.take_id}/tracks")
    assert tracks.status_code == 200, tracks.text
    assert tracks.json(), "empty tracks"


def test_4_feedback_is_flat_with_a_plan(flow):
    session_id = flow.need(flow.session_id, "a session")
    take_id = flow.need(flow.take_id, "a finished take")
    route = f"/sessions/{session_id}/takes/{take_id}/feedback"
    for method in (flow.client.get, flow.client.post):
        response = method(route)
        assert response.status_code == 200, f"{method.__name__.upper()} {route}: {response.text}"
        feedback = response.json()
        assert feedback["plan"], "feedback carries no plan"
        assert feedback["plan_id"] == feedback["plan"]["id"]
        assert feedback["plan"]["feedback_id"] == feedback["id"]
        assert feedback["plan"]["exercises"], "the plan has no exercises"
        assert feedback["take_id"] == take_id
        assert feedback["mode"] == "fallback", feedback["mode"]
        assert "feedback" not in feedback, "feedback is meant to be flat, not nested"
    print("feedback keys:", sorted(feedback), "| plan keys:", sorted(feedback["plan"]))
    flow.feedback = feedback


def test_5_practice_routes():
    pytest.skip("the practice routes (reps, exercise, progress) are not in app/main.py yet: only app/practice/ helpers exist")


def test_6_instructor_chat_falls_back(flow):
    session_id = flow.need(flow.session_id, "a session")
    take_id = flow.need(flow.take_id, "a finished take")
    posted = flow.client.post(f"/sessions/{session_id}/chat", json={"message": "What should I work on first?"})
    assert posted.status_code == 200, posted.text
    reply = posted.json()["instructor_turn"]
    assert posted.json()["user_turn"]["role"] == "user"
    assert reply["role"] == "instructor" and reply["text"]
    assert reply["mode"] == "fallback", reply["mode"]
    assert reply["take_id"] == take_id

    history = flow.client.get(f"/sessions/{session_id}/chat")
    assert history.status_code == 200, history.text
    assert [t["role"] for t in history.json()["turns"]] == ["user", "instructor"]


def test_7_trace_route(flow):
    session_id = flow.need(flow.session_id, "a session")
    feedback = flow.need(flow.feedback, "feedback")
    response = flow.client.get(f"/sessions/{session_id}/feedback/{feedback['id']}/trace")
    print("trace:", response.status_code, response.text[:200])
    assert response.status_code == 200, response.text  # run_feedback always saves a trace
    body = response.json()
    assert body["feedback_id"] == feedback["id"]
    assert body["events"], "the trace has no events"
    assert any(event["agent"] == "orchestrator" for event in body["events"]), body["events"]

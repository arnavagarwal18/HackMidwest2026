"""End to end through the real HTTP routes: a synthesized take goes in, the real transcription, diagnosis and
fallback feedback run, and the analysis and feedback routes are read back. Nothing in the chain is mocked."""
import json
import time

import pytest

from app import store
from synth_audio import synthesize, write_wav

PIECE = "twinkle"
INSTRUMENT = "violin"
BAR_FROM, BAR_TO = 1, 4
BPM = 90.0
DOWNBEAT_S = 1.0
WRONG_BAR = 2  # bar 2 is A A G: the missing G has no identical neighbour, which the alignment can't tell apart
WRONG_IDX, MISSING_IDX = 0, 2
TIMEOUT_S = 120
POLL_S = 0.5
FINISHED = ("diagnosed", "done", "failed")


def expected_notes(session_id: str) -> list[dict]:
    """The score's notes for the chosen bars as {bar, idx, midi, onset_beats, dur_beats}, read straight from score.json."""
    score = json.loads((store.session_dir(session_id) / "score.json").read_text(encoding="utf-8"))
    bars = [b for b in score["bars"] if BAR_FROM <= b["bar"] <= BAR_TO]
    first_beat = bars[0]["start_beat"]
    return [
        {"bar": b["bar"], "idx": n["idx"], "midi": n["pitch_midi"],
         "onset_beats": n["start_beat"] - first_beat, "dur_beats": n["dur_beats"]}
        for b in bars for n in b["notes"] if n["pitch_midi"] is not None
    ]


@pytest.fixture
def session_id(client):
    created = client.post("/sessions", json={"instrument": INSTRUMENT})
    assert created.status_code == 201, created.text
    sid = created.json()["session_id"]
    assert client.post(f"/sessions/{sid}/score/file", json={"builtin": PIECE}).status_code == 200
    assert client.post(f"/sessions/{sid}/score/confirm").status_code == 200
    return sid


def upload_and_wait(client, session_id: str, notes: list[dict], tmp_path) -> tuple[str, dict]:
    """Upload the synthesized notes as a recorded take, poll the analysis until it settles; (take_id, analysis)."""
    wav = write_wav(tmp_path / "take.wav", synthesize(notes, 60.0 / BPM, DOWNBEAT_S))
    form = {"kind": "mic", "source": "recorded", "bar_from": BAR_FROM, "bar_to": BAR_TO,
            "tempo_bpm": BPM, "count_in_beats": 0, "downbeat_s": DOWNBEAT_S}
    posted = client.post(f"/sessions/{session_id}/takes", data={k: str(v) for k, v in form.items()},
                         files={"file": ("take.wav", wav.read_bytes(), "audio/wav")})
    assert posted.status_code == 202, posted.text
    take_id = posted.json()["take_id"]

    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        analysis = client.get(f"/sessions/{session_id}/takes/{take_id}/analysis").json()
        if analysis["status"] in FINISHED and analysis["status"] != "diagnosed":
            return take_id, analysis
        time.sleep(POLL_S)
    pytest.fail(f"Take still '{analysis['status']}' after {TIMEOUT_S} s")


def get_feedback(client, session_id: str, take_id: str) -> dict:
    response = client.get(f"/sessions/{session_id}/takes/{take_id}/feedback")
    assert response.status_code == 200, response.text
    return response.json()


def tier1_problems(analysis: dict) -> list[dict]:
    return [p for p in analysis["problems"] if p["tier"] == 1]


def test_clean_take_is_diagnosed_clean(client, session_id, tmp_path):
    notes = expected_notes(session_id)
    take_id, analysis = upload_and_wait(client, session_id, notes, tmp_path)
    print("clean take: quality", analysis["alignment_quality"], "problems", analysis["problems"],
          "tempo", analysis["tempo"])

    assert analysis["status"] in ("diagnosed", "done"), analysis["error"]
    assert analysis["alignment_quality"] >= 0.8
    assert analysis["cant_tell"] is False
    assert tier1_problems(analysis) == []
    feedback = get_feedback(client, session_id, take_id)
    assert feedback["take_id"] == take_id and feedback["plan"]["exercises"]  # a clean take has no tier 1 sentences to say


def test_wrong_and_missing_note_are_reported_on_that_bar(client, session_id, tmp_path):
    notes = expected_notes(session_id)
    played = []
    for note in notes:
        if note["bar"] == WRONG_BAR and note["idx"] == MISSING_IDX:
            continue
        wrong = note["bar"] == WRONG_BAR and note["idx"] == WRONG_IDX
        played.append({**note, "midi": note["midi"] + 1} if wrong else note)
    take_id, analysis = upload_and_wait(client, session_id, played, tmp_path)
    print("faulty take: quality", analysis["alignment_quality"], "problems", analysis["problems"],
          "tier1", analysis["tier1"])

    assert analysis["status"] in ("diagnosed", "done"), analysis["error"]
    assert analysis["cant_tell"] is False
    bar_problems = [p for p in analysis["problems"] if p["kind"] == "notes" and WRONG_BAR in p["bars"]]
    assert len(bar_problems) == 1
    assert bar_problems[0]["numbers"]["wrong"] == 1 and bar_problems[0]["numbers"]["missed"] == 1
    assert bar_problems[0]["tier"] == 1
    assert any(f"Bar {WRONG_BAR}" in sentence["text"] for sentence in analysis["tier1"])

    feedback = get_feedback(client, session_id, take_id)
    cited = [s for s in feedback["sentences"] if bar_problems[0]["id"] in s["cites"]]
    assert cited and f"Bar {WRONG_BAR}" in cited[0]["text"]

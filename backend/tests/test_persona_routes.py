"""Coach-style routes (POST /sessions, GET /sessions/{id}, PATCH /sessions/{id}, GET /personas) and the rollback script."""
import json
import sys
from pathlib import Path

import pytest

from app import store
from tests.test_sessions import assert_error

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import strip_session_persona  # noqa: E402

PICK_A_STYLE = "Pick a coach style from the list."


def new_session(client, **body):
    return client.post("/sessions", json={"instrument": "trumpet", **body})


def test_a_session_made_without_a_persona_is_standard(client):
    response = new_session(client)
    assert response.status_code == 201 and response.json()["persona"] == "standard"
    assert client.get(f"/sessions/{response.json()['session_id']}").json()["persona"] == "standard"


@pytest.mark.parametrize("persona", ["standard", "concert", "marching", "beginner"])
def test_a_session_can_start_with_a_persona(client, sessions_root, persona):
    body = new_session(client, persona=persona).json()
    assert body["persona"] == persona
    assert client.get(f"/sessions/{body['session_id']}").json()["persona"] == persona
    assert json.loads((sessions_root / body["session_id"] / "session.json").read_text())["persona"] == persona


@pytest.mark.parametrize("persona", ["jazz", ""])
def test_creating_a_session_with_an_unknown_persona_is_a_clear_422(client, persona):
    response = new_session(client, persona=persona)
    assert_error(response, 422, "bad_request")
    assert response.json()["error"]["message"] == PICK_A_STYLE


def test_a_persona_that_is_not_text_is_a_422_in_the_usual_error_format(client):
    assert_error(new_session(client, persona=5), 422, "bad_request")


def test_patch_changes_the_persona_and_the_new_one_is_saved(client, sessions_root):
    session_id = new_session(client).json()["session_id"]
    response = client.patch(f"/sessions/{session_id}", json={"persona": "marching"})
    assert (response.status_code, response.json()) == (200, {"session_id": session_id, "persona": "marching"})
    assert client.get(f"/sessions/{session_id}").json()["persona"] == "marching"
    assert json.loads((sessions_root / session_id / "session.json").read_text())["persona"] == "marching"


def test_patch_with_an_unknown_persona_is_422_and_changes_nothing(client):
    session_id = new_session(client, persona="concert").json()["session_id"]
    response = client.patch(f"/sessions/{session_id}", json={"persona": "jazz"})
    assert_error(response, 422, "bad_request")
    assert response.json()["error"]["message"] == PICK_A_STYLE
    assert client.get(f"/sessions/{session_id}").json()["persona"] == "concert"


def test_patch_without_a_persona_is_a_bad_request_not_a_server_error(client):
    session_id = new_session(client).json()["session_id"]
    assert client.patch(f"/sessions/{session_id}", json={}).status_code == 422


def test_patch_on_a_missing_session_is_404(client):
    assert_error(client.patch("/sessions/nope", json={"persona": "concert"}), 404, "session_not_found")


def test_the_persona_list_has_standard_first_with_hints_and_tempo_rules(client):
    body = client.get("/personas").json()
    assert body["default"] == "standard"
    assert [p["id"] for p in body["personas"]] == ["standard", "concert", "marching", "beginner"]
    assert body["personas"][0] == {"id": "standard", "label": "Standard", "hint": "The usual coach, no particular style",
                                   "tempo": {"kind": "written_factor", "value": 1.0}}
    by_id = {p["id"]: p for p in body["personas"]}
    assert by_id["marching"]["tempo"] == {"kind": "fixed_bpm", "value": 120}
    assert by_id["beginner"]["tempo"] == {"kind": "written_factor", "value": 0.7}
    assert all(set(p) == {"id", "label", "hint", "tempo"} for p in body["personas"])


def test_a_session_file_from_before_personas_loads_as_standard(client, sessions_root):
    session_id = new_session(client).json()["session_id"]
    session_file = sessions_root / session_id / "session.json"
    data = json.loads(session_file.read_text())
    del data["persona"]
    session_file.write_text(json.dumps(data))
    store._sessions.clear()
    assert client.get(f"/sessions/{session_id}").json()["persona"] == "standard"


# ---- rollback script ----

def test_rollback_strips_the_persona_key_and_leaves_the_rest(client, sessions_root):
    with_persona = new_session(client, persona="marching").json()["session_id"]
    without = new_session(client).json()["session_id"]
    del_file = sessions_root / without / "session.json"
    data = json.loads(del_file.read_text())
    del data["persona"]
    del_file.write_text(json.dumps(data))
    before = json.loads((sessions_root / with_persona / "session.json").read_text())

    assert strip_session_persona.strip_all(sessions_root) == (1, 0)
    after = json.loads((sessions_root / with_persona / "session.json").read_text())
    assert "persona" not in after and after == {k: v for k, v in before.items() if k != "persona"}
    assert strip_session_persona.strip_all(sessions_root) == (0, 0)  # running it again changes nothing


def test_rollback_reports_an_unreadable_file_and_still_strips_the_others(client, sessions_root, caplog):
    good = new_session(client, persona="concert").json()["session_id"]
    bad = sessions_root / "broken"
    bad.mkdir()
    (bad / "session.json").write_text("not json")
    assert strip_session_persona.strip_all(sessions_root) == (1, 1)
    assert "persona" not in json.loads((sessions_root / good / "session.json").read_text())
    assert "Could not strip the persona" in caplog.text


def test_rollback_main_exits_with_a_message_for_a_missing_folder_and_1_when_a_file_failed(sessions_root, tmp_path, caplog):
    assert strip_session_persona.main(["script", str(tmp_path / "nope")]) == 2
    assert "No sessions folder" in caplog.text
    broken = tmp_path / "root" / "x"
    broken.mkdir(parents=True)
    (broken / "session.json").write_text("[]")
    assert strip_session_persona.main(["script", str(tmp_path / "root")]) == 1

import json

import pytest

from app.agents.tools import MAX_JSON_CHARS, fit_json, make_tools


@pytest.fixture
def tools(fixture_data):
    return make_tools(
        fixture_data["session_id"],
        fixture_data["take_id"],
        get_diagnosis=lambda s, t: fixture_data["diagnosis"],
        get_form=lambda s, t: fixture_data["form"],
        get_earlier_takes=lambda s, t: fixture_data["history"],
    )


def call(tool, *args):
    return json.loads(tool(*args))


def test_tool_names(tools):
    assert set(tools) == {
        "get_take_overview", "list_problems", "get_bar", "get_measurement", "list_form_flags", "get_history",
    }
    assert all(tool.__doc__ for tool in tools.values())


def test_overview(tools):
    overview = call(tools["get_take_overview"])
    assert overview["counts"] == {"ok": 8, "wrong": 2, "missed": 1, "uncertain": 1, "extra": 1}
    assert (overview["bar_from"], overview["bar_to"]) == (1, 4)
    assert overview["clean_bpm"] == 60
    assert overview["instrument"] == "violin"
    assert overview["form_status"] == "ok"
    assert overview["cant_tell"] is False
    assert len(overview["tier1"]) == 2


def test_list_problems_default_tier_and_order(tools):
    ids = [p["id"] for p in call(tools["list_problems"])["problems"]]
    assert ids == ["p:t1:0", "p:t1:1", "p:t1:2"]
    assert [p["id"] for p in call(tools["list_problems"], 1)["problems"]] == ["p:t1:0", "p:t1:1"]
    assert len(call(tools["list_problems"], 3)["problems"]) == 4


@pytest.mark.parametrize("bad", [0, 4, "x", None, 1.5])
def test_list_problems_bad_tier_returns_error(tools, bad):
    assert "max_tier" in call(tools["list_problems"], bad)["error"]


def test_get_bar(tools):
    result = call(tools["get_bar"], 4)
    assert result["bar"]["id"] == "b:t1:4"
    assert [n["idx"] for n in result["notes"]] == [0, 1, 2]
    assert [f["id"] for f in result["form_flags"]] == ["f:t1:0"]


@pytest.mark.parametrize("bad", [0, 5, -1])
def test_get_bar_out_of_range_returns_error(tools, bad):
    assert call(tools["get_bar"], bad) == {"error": "bar out of range 1-4"}


@pytest.mark.parametrize("bad", ["two", None, [1], True])
def test_get_bar_bad_input_returns_error(tools, bad):
    assert "error" in call(tools["get_bar"], bad)


def test_get_measurement(tools):
    assert call(tools["get_measurement"], "n:t1:2:1")["item"]["played_name"] == "F#5"
    assert call(tools["get_measurement"], "f:t1:0")["item"]["rule"] == "elbow_height"


@pytest.mark.parametrize("bad", ["n:t1:99:0", "nonsense", "", None, 7])
def test_get_measurement_unknown_id_returns_error(tools, bad):
    assert call(tools["get_measurement"], bad) == {"error": "unknown id"}


def test_form_flags(tools):
    result = call(tools["list_form_flags"])
    assert [f["id"] for f in result["flags"]] == ["f:t1:0"]
    assert result["rules_skipped"][0]["rule"] == "bow_angle"


def test_history(tools):
    result = call(tools["get_history"])
    assert result["clean_bpm"] == 60
    assert result["takes"][0] == {"take_id": "t0", "error_rate": 0.03, "played_bpm": 60}


def test_clean_tempo_counts_this_take_when_clean(fixture_data):
    fixture_data["diagnosis"]["error_rate"] = 0.0
    tools = make_tools("s1", "t1", get_diagnosis=lambda s, t: fixture_data["diagnosis"])
    assert call(tools["get_take_overview"])["clean_bpm"] == 76
    assert call(tools["get_history"]) == {"takes": [], "clean_bpm": 76}


def test_missing_diagnosis_returns_error(fixture_data):
    tools = make_tools("s1", "t9", get_diagnosis=lambda s, t: None)
    assert call(tools["get_take_overview"]) == {"error": "no diagnosis for take t9"}


def test_failing_data_access_returns_error_and_logs(caplog):
    def broken(session_id, take_id):
        raise RuntimeError("disk gone")

    tools = make_tools("s1", "t1", get_diagnosis=broken)
    assert "disk gone" in call(tools["get_bar"], 1)["error"]
    assert "disk gone" in caplog.text


def test_injected_lookup_is_used(fixture_data):
    seen = []

    def lookup(session_id, take_id, item_id):
        seen.append((session_id, take_id, item_id))
        return {"id": item_id, "custom": True}

    tools = make_tools("s1", "t1", get_diagnosis=lambda s, t: fixture_data["diagnosis"], lookup=lookup)
    assert call(tools["get_measurement"], "n:t1:1:0") == {"item": {"id": "n:t1:1:0", "custom": True}}
    assert seen == [("s1", "t1", "n:t1:1:0")]


def test_list_problems_truncates_at_8000_chars(fixture_data):
    diagnosis = fixture_data["diagnosis"]
    template = diagnosis["problems"][0]
    diagnosis["problems"] = [
        {**template, "id": f"p:t1:{k}", "score": k / 1000, "tier": 1, "measurement_ids": [f"n:t1:1:{i}" for i in range(5)]}
        for k in range(200)
    ]
    tools = make_tools("s1", "t1", get_diagnosis=lambda s, t: diagnosis)
    text = tools["list_problems"]()
    result = json.loads(text)
    assert len(text) <= MAX_JSON_CHARS
    kept = len(result["problems"])
    assert 0 < kept < 200
    assert result["truncated"] == {"problems": 200 - kept}
    assert result["problems"][0]["id"] == "p:t1:199"  # highest score kept first
    scores = [p["score"] for p in result["problems"]]
    assert scores == sorted(scores, reverse=True)


def test_small_result_is_not_marked_truncated(tools):
    assert "truncated" not in call(tools["list_problems"])


def test_fit_json_without_lists_to_cut_returns_error(caplog):
    result = json.loads(fit_json({"blob": "x" * 9000}))
    assert "too large" in result["error"]
    assert "nothing left to cut" in caplog.text

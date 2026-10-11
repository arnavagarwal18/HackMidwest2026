"""Wrong / missed notes outrank rushing / dragging, which outrank small timing slips; the AI time limit is 45 s."""
from types import SimpleNamespace

from app.agents import ai_run, fallback, tools
from app.diagnosis import rank as rank_module
from app.diagnosis.priority import priority_key


def problem(kind, bars, score, first_time_s=0.0, **extra):
    return {"kind": kind, "bars": bars, "score": score, "first_time_s": first_time_s,
            "certainty": 0.9, "size": 0.5, "measurement_ids": [], "numbers": {}, **extra}


# The planted take: slips score highest, then rushing in bars 9-10, then bar 3 wrong and bar 6 missed.
SLIP = problem("late", [1, 2], 0.9, 1.0)
RUSHING = problem("rushing", [9, 10], 0.5, 20.0)
WRONG = problem("notes", [3], 0.2, 5.0, numbers={"wrong": 1, "missed": 0, "extra": 0})
MISSED = problem("notes", [6], 0.2, 12.0, numbers={"wrong": 0, "missed": 1, "extra": 0})
EXPECTED_KINDS = ["notes", "notes", "rushing", "late"]


def kinds(problems):
    return [p["kind"] for p in problems]


def test_priority_key_orders_notes_then_rushing_then_slips():
    ordered = sorted([SLIP, RUSHING, MISSED, WRONG], key=priority_key)

    assert kinds(ordered) == EXPECTED_KINDS
    assert [p["bars"] for p in ordered[:2]] == [[3], [6]]  # same group: earlier in the take first


def test_dragging_ranks_with_rushing_and_early_with_late():
    dragging, early = problem("dragging", [4], 0.3), problem("early", [5], 0.8)

    assert kinds(sorted([early, dragging, SLIP], key=priority_key)) == ["dragging", "late", "early"]  # one slip group, by score


def test_rank_puts_notes_before_rushing_before_slips_in_tier_one_and_ids(monkeypatch):
    monkeypatch.setattr(rank_module, "find_problems", lambda diagnosis, flags: [SLIP, RUSHING, MISSED, WRONG])
    monkeypatch.setattr(rank_module, "build_sentence", lambda p: {"problem_id": p["id"], "kind": p["kind"]})
    diagnosis = {"cant_tell": False, "not_played_count": 0}

    ranking = rank_module.rank("t1", diagnosis, [])

    assert kinds(ranking["problems"]) == EXPECTED_KINDS
    assert [p["id"] for p in ranking["problems"]] == [f"p:t1:{k}" for k in range(4)]
    assert [p["tier"] for p in ranking["problems"]] == [1, 1, 1, 2]
    assert [s["kind"] for s in ranking["tier1"]] == ["notes", "notes", "rushing"]


def with_ids(problems):
    return [{"id": f"p:t1:{k}", "tier": 1, **p} for k, p in enumerate(problems)]


def test_fallback_plan_focuses_on_notes_then_rushing_before_slips():
    diagnosis = {"problems": with_ids([SLIP, RUSHING, MISSED, WRONG])}

    focus = fallback._tier1_problems(diagnosis)

    assert kinds(focus) == ["notes", "notes", "rushing"]
    assert fallback._strongest_problem_ids(diagnosis) == ["p:t1:3"]


def test_list_problems_tool_gives_notes_then_rushing_then_slips():
    ctx = SimpleNamespace(diagnosis={"problems": with_ids([SLIP, RUSHING, MISSED, WRONG])})

    assert kinds(tools._problems(ctx, 1)["problems"]) == EXPECTED_KINDS


def test_ai_time_limit_is_45_seconds():
    assert ai_run.TIME_LIMIT_S == 45

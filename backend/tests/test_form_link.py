"""Steps 7 and 8: flags on bars, and links to the bar results (pure functions)."""
import pytest

from app.form.link import add_bars_and_links, bars_between, links_for_bar

GRID = {"kind": "metronome", "offset_s": 1.0, "sec_per_beat": 1.0}  # 60 BPM: bar n starts at 1 + 4 * (n - 1) s
SPANS = [{"bar": n, "start_beat": 4.0 * (n - 1), "beats": 4.0} for n in range(1, 5)]


def bar_result(bar, **fields):
    return {"id": f"b:t1:{bar}", "bar": bar, "expected": 4, "ok": 4, "wrong": 0, "missed": 0, "extra": 0, "uncertain": 0,
            "mean_timing_ms": 0, "local_bpm": 60, "drift_pct": 0, "drift": "steady", **fields}


def note(bar, idx, status="ok", timing_ms=0):
    return {"id": f"n:t1:{bar}:{idx}", "bar": bar, "idx": idx, "status": status, "timing_ms": timing_ms}


def diagnosis(bars=(), notes=(), extras=(), grid=GRID, cant_tell=False):
    return {"grid": grid, "cant_tell": cant_tell, "bars": [*bars], "notes": [*notes], "extras": [*extras]}


def flag(start_s, end_s):
    return {"id": "f:t1:1", "rule": "slouching", "start_s": start_s, "end_s": end_s, "bars": [], "linked": []}


def test_a_flag_inside_one_bar_gets_that_bar():
    assert bars_between(5.2, 6.5, GRID, SPANS) == [2]


def test_a_flag_across_a_barline_gets_every_bar_it_touches():
    assert bars_between(5.2, 9.5, GRID, SPANS) == [2, 3]
    assert bars_between(2.0, 13.5, GRID, SPANS) == [1, 2, 3, 4]


def test_times_outside_the_take_give_no_bar():
    assert bars_between(0.0, 0.9, GRID, SPANS) == []  # before the first beat
    assert bars_between(17.5, 20.0, GRID, SPANS) == []  # after the last bar


def test_a_flag_running_past_the_ends_is_clipped_to_the_take_bars():
    assert bars_between(0.0, 6.0, GRID, SPANS) == [1, 2]
    assert bars_between(15.0, 30.0, GRID, SPANS) == [4]


def test_bars_follow_the_first_bar_of_the_take():
    later = [{"bar": n, "start_beat": 4.0 * (n - 1), "beats": 4.0} for n in (3, 4)]  # a take of bars 3-4
    assert bars_between(1.5, 2.0, GRID, later) == [3]
    assert bars_between(5.0, 6.0, GRID, later) == [4]


def test_a_rushing_bar_links_the_flag_to_it():
    placed = add_bars_and_links([flag(5.2, 9.5)], diagnosis(bars=[bar_result(2, drift="rushing"), bar_result(3)]), SPANS)
    assert placed[0]["bars"] == [2, 3]
    assert placed[0]["linked"] == [{"kind": "rushing", "bar": 2, "ids": ["b:t1:2"]}]


def test_a_dragging_bar_links_by_its_drift_only():
    links = links_for_bar(bar_result(2, drift="dragging"), [], [])
    assert links == [{"kind": "dragging", "bar": 2, "ids": ["b:t1:2"]}]
    assert links_for_bar(bar_result(2, drift=None), [], []) == []


def test_wrong_missed_and_extra_notes_make_a_notes_link():
    notes = [note(2, 1, "wrong"), note(2, 2, "missed"), note(2, 3, "ok"), note(2, 4, "uncertain")]
    extras = [{"id": "x:t1:7", "bar": 2}]
    links = links_for_bar(bar_result(2, wrong=1, missed=1, extra=1), notes, extras)
    assert links == [{"kind": "notes", "bar": 2, "ids": ["b:t1:2", "n:t1:2:1", "n:t1:2:2", "x:t1:7"]}]


def test_an_extra_note_alone_makes_a_notes_link():
    links = links_for_bar(bar_result(2, extra=1), [note(2, 1)], [{"id": "x:t1:3", "bar": 2}])
    assert links == [{"kind": "notes", "bar": 2, "ids": ["b:t1:2", "x:t1:3"]}]


def test_two_late_notes_link_as_late_and_one_does_not():
    two = [note(2, 1, timing_ms=120), note(2, 2, timing_ms=95), note(2, 3, timing_ms=10)]
    assert links_for_bar(bar_result(2), two, []) == [{"kind": "late", "bar": 2, "ids": ["b:t1:2", "n:t1:2:1", "n:t1:2:2"]}]
    assert links_for_bar(bar_result(2), [note(2, 1, timing_ms=120), note(2, 2, timing_ms=10)], []) == []


def test_two_early_notes_link_as_early_and_the_threshold_is_the_diagnosis_one():
    early = [note(2, 1, timing_ms=-120), note(2, 2, timing_ms=-81)]
    assert [link["kind"] for link in links_for_bar(bar_result(2), early, [])] == ["early"]
    assert links_for_bar(bar_result(2), [note(2, 1, timing_ms=80), note(2, 2, timing_ms=-80)], []) == []  # 80 ms is on time


def test_notes_late_early_and_drift_all_link_in_order():
    notes = [note(2, 1, "wrong", 120), note(2, 2, timing_ms=100), note(2, 3, timing_ms=-100), note(2, 4, timing_ms=-90)]
    links = links_for_bar(bar_result(2, wrong=1, drift="rushing"), notes, [])
    assert [link["kind"] for link in links] == ["notes", "late", "early", "rushing"]


def test_each_flag_bar_is_linked_from_its_own_notes():
    notes = [note(2, 1, "wrong"), note(3, 1, "missed")]
    placed = add_bars_and_links([flag(5.2, 9.5)], diagnosis(bars=[bar_result(2), bar_result(3)], notes=notes), SPANS)
    assert [(link["bar"], link["ids"]) for link in placed[0]["linked"]] == [
        (2, ["b:t1:2", "n:t1:2:1"]), (3, ["b:t1:3", "n:t1:3:1"])]


@pytest.mark.parametrize("bad", [
    diagnosis(bars=[bar_result(2, drift="rushing")], cant_tell=True),
    diagnosis(bars=[bar_result(2, drift="rushing")], grid=None),
    None,
    {},
])
def test_without_a_usable_grid_the_flag_keeps_its_time_and_gets_no_bars_or_links(bad):
    placed = add_bars_and_links([flag(5.2, 6.5)], bad, SPANS)
    assert placed == [flag(5.2, 6.5)]


def test_a_bar_without_a_result_gets_no_links():
    placed = add_bars_and_links([flag(5.2, 6.5)], diagnosis(bars=[bar_result(3, drift="rushing")]), SPANS)
    assert (placed[0]["bars"], placed[0]["linked"]) == ([2], [])

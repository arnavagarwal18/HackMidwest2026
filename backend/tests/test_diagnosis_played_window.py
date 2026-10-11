"""Step 3 time map and step 4 played window: a sped-up phrase, a tempo far from the goal, and partial plays."""
import pytest

from app.diagnosis.align import TimeMap, build_time_map, fit_line
from app.diagnosis.expected import ExpectedNote
from app.diagnosis.rank import rank
from app.diagnosis.sentences import sentence_text
from app.diagnosis.take_alignment import align_take
from app.diagnosis.timing import add_timing
from diagnosis_samples import long_scale_midis, make_long_score, make_take, perfect_played, tempo_by_bar_played

GOAL_BPM = 120
RUSH_BARS = [5, 6, 7, 8]
RUSH_FACTOR = 1.15


def timed(played, take=None):
    take = take or make_take(bar_from=1, bar_to=16, tempo_bpm=GOAL_BPM)
    return add_timing(align_take(make_long_score(), played, take, 0), played, take)


def rushed_phrase(fraction_of_goal: float, factor: float = RUSH_FACTOR) -> list[dict]:
    base = 60 / (GOAL_BPM * fraction_of_goal)
    return tempo_by_bar_played(long_scale_midis(), lambda bar: base / factor if bar in RUSH_BARS else base)


@pytest.mark.parametrize("fraction_of_goal, vs_goal", [(0.7, -27.6), (1.2, 24.2)])
def test_sped_up_phrase_is_one_rushing_problem_on_exactly_those_bars(fraction_of_goal, vs_goal):
    diagnosis = timed(rushed_phrase(fraction_of_goal))

    problems = rank("t1", diagnosis, [])["problems"]

    rushing = [p for p in problems if p["kind"] == "rushing"]
    assert [p["bars"] for p in rushing] == [RUSH_BARS]
    assert rushing[0]["numbers"]["drift_pct"] == pytest.approx(15, abs=1)
    assert not [p for p in problems if p["kind"] == "dragging"]
    # played tempo is the whole take's: 4 of 16 bars are 15% faster, so it sits a little above fraction x goal
    assert diagnosis["tempo_vs_goal_pct"] == pytest.approx(vs_goal, abs=2)
    assert diagnosis["reference_bpm"] == pytest.approx(GOAL_BPM * fraction_of_goal, abs=0.2)
    bars_drift = {b["bar"]: b["drift"] for b in diagnosis["bars"]}
    assert [bar for bar, drift in bars_drift.items() if drift == "rushing"] == RUSH_BARS


def test_rushing_sentence_names_the_players_own_tempo():
    ranking = rank("t1", timed(rushed_phrase(0.7)), [])

    rushing = next(p for p in ranking["problems"] if p["kind"] == "rushing")
    assert sentence_text(rushing) == "Bars 5-8: rushing, about 15% faster than your own tempo (84 BPM)."


@pytest.mark.parametrize("factor", [RUSH_FACTOR, 1.3])  # 1.3 pushes the old single straight line past +-1 beat
def test_sped_up_phrase_with_every_note_right_has_no_missed_notes_and_no_extras(factor):
    diagnosis = timed(rushed_phrase(1.0, factor))

    assert [n["status"] for n in diagnosis["notes"]].count("ok") == 64
    assert diagnosis["extras"] == []
    assert diagnosis["alignment_quality"] == 1.0
    assert diagnosis["not_played_count"] == 0


def test_only_the_first_half_played_leaves_the_rest_not_played():
    played = perfect_played(long_scale_midis()[:32])

    diagnosis = timed(played)
    ranking = rank("t1", diagnosis, [])

    assert diagnosis["played_bars"] == [1, 8]
    assert diagnosis["not_played_count"] == 32
    later = [n for n in diagnosis["notes"] if n["bar"] > 8]
    assert {n["status"] for n in later} == {"not_played"} and all(n["timing_ms"] is None for n in later)
    assert not [n for n in diagnosis["notes"] if n["status"] == "missed"]
    assert diagnosis["cant_tell"] is False
    assert diagnosis["alignment_quality"] == 1.0 and diagnosis["error_rate"] == 0
    assert [b["expected"] for b in diagnosis["bars"][8:]] == [0] * 8
    range_note = ranking["problems"][-1]
    assert (range_note["kind"], range_note["tier"], range_note["text"]) == ("range", 3, "You played bars 1-8 of 1-16.")
    assert ranking["tier1"] == [] and len(ranking["problems"]) == 1


def test_a_whole_take_has_no_range_note():
    ranking = rank("t1", timed(perfect_played(long_scale_midis())), [])

    assert ranking["problems"] == []


def test_a_bar_missing_in_the_middle_is_still_missed():
    played = [p for p in perfect_played(long_scale_midis()) if not 16 <= p["i"] < 20]  # bar 5 is never played

    diagnosis = timed(played)

    assert diagnosis["played_bars"] == [1, 16] and diagnosis["not_played_count"] == 0
    missed = [n for n in diagnosis["notes"] if n["status"] == "missed"]
    assert [n["bar"] for n in missed] == [5] * 4
    assert not [p for p in rank("t1", diagnosis, [])["problems"] if p["kind"] == "range"]


def test_notes_before_the_first_played_bar_are_not_played():
    played = [p for p in perfect_played(long_scale_midis()) if p["i"] >= 16]  # bars 1-4 are never played

    diagnosis = timed(played)

    assert diagnosis["played_bars"] == [5, 16]
    assert diagnosis["not_played_count"] == 16
    assert not [n for n in diagnosis["notes"] if n["status"] == "missed"]
    assert rank("t1", diagnosis, [])["problems"][-1]["text"] == "You played bars 5-16 of 1-16."


def expected_note(beat: float, midi: int) -> ExpectedNote:
    return ExpectedNote(id=f"n:{beat}", bar=1, idx=0, name="x", midi=midi, onset_beats=beat, dur_beats=1.0)


def test_time_map_interpolates_between_anchors_and_extends_with_the_least_squares_line():
    anchors = [(0.0, 1.0), (4.0, 3.0), (8.0, 4.0)]
    line = fit_line(anchors)
    time_map = TimeMap(anchors, line)

    assert time_map.time_at(2.0) == pytest.approx(2.0)  # halfway between the first two anchors
    assert time_map.time_at(6.0) == pytest.approx(3.5)
    assert time_map.time_at(4.0) == pytest.approx(3.0)  # on an anchor
    assert time_map.time_at(8.0) == pytest.approx(4.0)  # the last anchor itself, not the line
    assert time_map.time_at(-2.0) == pytest.approx(line.offset_s - 2.0 * line.sec_per_beat)
    assert time_map.time_at(10.0) == pytest.approx(line.offset_s + 10.0 * line.sec_per_beat)


def test_anchor_whose_onset_is_not_later_than_the_previous_one_is_dropped():
    expected = [expected_note(beat, 60 + beat) for beat in range(5)]
    played = [
        {"midi": 60, "onset_s": 1.0}, {"midi": 61, "onset_s": 1.5}, {"midi": 62, "onset_s": 1.4},
        {"midi": 63, "onset_s": 2.0}, {"midi": 64, "onset_s": 2.5},
    ]

    time_map = build_time_map(expected, played, [(i, i) for i in range(5)])

    assert time_map.anchors == [(0, 1.0), (1, 1.5), (3, 2.0), (4, 2.5)]


def test_fewer_than_three_anchors_leaves_pass_one_standing():
    expected = [expected_note(beat, 60 + beat) for beat in range(3)]
    played = [{"midi": 60, "onset_s": 1.0}, {"midi": 99, "onset_s": 1.5}, {"midi": 62, "onset_s": 2.0}]

    assert build_time_map(expected, played, [(i, i) for i in range(3)]) is None


def test_anchor_off_the_line_of_its_neighbours_by_over_half_a_beat_is_dropped():
    expected = [expected_note(beat, 60 + beat) for beat in range(8)]
    onsets = [1.0 + 0.5 * beat for beat in range(8)]
    onsets[4] += 0.3  # 0.6 beat late: pass 1 paired the wrong copy of a repeated note
    played = [{"midi": 60 + beat, "onset_s": onset_s} for beat, onset_s in enumerate(onsets)]

    time_map = build_time_map(expected, played, [(i, i) for i in range(8)])

    assert [beat for beat, _ in time_map.anchors] == [0, 1, 2, 3, 5, 6, 7]


def test_anchor_off_by_less_than_half_a_beat_is_kept():
    expected = [expected_note(beat, 60 + beat) for beat in range(8)]
    onsets = [1.0 + 0.5 * beat for beat in range(8)]
    onsets[4] += 0.2  # 0.4 beat late: ordinary playing
    played = [{"midi": 60 + beat, "onset_s": onset_s} for beat, onset_s in enumerate(onsets)]

    time_map = build_time_map(expected, played, [(i, i) for i in range(8)])

    assert len(time_map.anchors) == 8


def test_a_steady_seven_percent_rush_over_sixteen_bars_keeps_every_anchor():
    midis = long_scale_midis()
    total_beats = len(midis)
    # the beat gets shorter in a straight line, ending 7% faster than it began
    seconds, onset_s = [], 1.0
    for beat in range(total_beats):
        seconds.append(onset_s)
        onset_s += 0.5 / (1 + 0.07 * beat / (total_beats - 1))
    played = [{"midi": midi, "onset_s": at} for midi, at in zip(midis, seconds)]
    expected = [expected_note(beat, midi) for beat, midi in enumerate(midis)]

    time_map = build_time_map(expected, played, [(i, i) for i in range(total_beats)])

    assert len(time_map.anchors) == total_beats


def test_a_steady_seven_percent_rush_is_all_ok_and_not_a_rushing_problem():
    played = tempo_by_bar_played(long_scale_midis(), lambda bar: 0.5 / (1 + 0.07 * (bar - 1) / 15))

    diagnosis = timed(played)

    assert [n["status"] for n in diagnosis["notes"]].count("ok") == 64
    assert not [p for p in rank("t1", diagnosis, [])["problems"] if p["kind"] in ("rushing", "dragging")]

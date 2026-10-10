import io

import pytest
from PIL import Image

from app.agents.trace import Trace
from app.score.referee import config
from app.score.referee.tools import RefereeSession
from tests.referee_helpers import FOUR_QUARTERS, compare_of, make_reading, make_score, photo  # noqa: F401

D5_QUARTERS = [("D5", "quarter")] * 4
C5_QUARTERS = [("C5", "quarter")] * 4


def session_for(score, reading_bars, photo_path, **kwargs) -> RefereeSession:
    reading = make_reading(reading_bars)
    return RefereeSession(score, reading, compare_of(score, reading), photo_path, **kwargs)


@pytest.fixture
def session(photo):
    # bar 2: homr is a quarter short, the reader has four beats; bar 3: both have four beats but different notes
    score = make_score([FOUR_QUARTERS, [("E5", "quarter")] * 3, C5_QUARTERS, FOUR_QUARTERS, FOUR_QUARTERS])
    bars = {1: FOUR_QUARTERS, 2: D5_QUARTERS, 3: D5_QUARTERS, 4: FOUR_QUARTERS, 5: FOUR_QUARTERS}
    return session_for(score, bars, photo, trace=Trace())


def test_list_doubtful_bars(session):
    assert session.list_doubtful_bars() == [
        {"bar": 2, "homr_text": "E5 quarter, E5 quarter, E5 quarter",
         "reader_text": "D5 quarter, D5 quarter, D5 quarter, D5 quarter"},
        {"bar": 3, "homr_text": "C5 quarter, C5 quarter, C5 quarter, C5 quarter",
         "reader_text": "D5 quarter, D5 quarter, D5 quarter, D5 quarter"},
    ]


def test_get_bar_shows_both_readings_with_checks(session):
    bar = session.get_bar(2)
    assert bar["homr"]["checks"]["length_ok"] is False and bar["homr"]["checks"]["beats"] == 3.0
    assert bar["reader"]["checks"]["length_ok"] is True
    assert bar["time_signature"] == [4, 4] and bar["key_signature"] is None


def test_unknown_bars_give_an_error_from_every_tool(session):
    for number in (1, 9):  # bar 1 agrees, bar 9 does not exist
        assert session.get_bar(number) == {"error": "unknown_bar"}
        assert session.look_at_bar(number) == {"error": "unknown_bar"}
        assert session.submit_ruling(number, "reader", "x", 0.9) == {"accepted": False, "rejected_because": "unknown_bar"}


def test_reader_is_accepted_when_its_checks_pass_and_confidence_is_high(session):
    assert session.submit_ruling(2, "reader", "reader counts four beats", 0.9) == {"accepted": True, "rejected_because": None}
    [ruling] = session.close()
    assert ruling == {"bar": 2, "pick": "reader", "why": "reader counts four beats", "confidence": 0.9,
                      "accepted": True, "rejected_because": None}


def test_a_reading_with_the_wrong_length_is_rejected(session):
    assert session.submit_ruling(2, "homr", "x", 0.95) == {"accepted": False, "rejected_because": "length"}


def test_low_confidence_is_rejected_and_the_floor_itself_is_accepted(session):
    assert session.submit_ruling(2, "reader", "x", 0.5) == {"accepted": False, "rejected_because": "low_confidence"}
    assert session.submit_ruling(3, "reader", "x", config.CONFIDENCE_FLOOR)["accepted"] is True


def test_neither_is_never_accepted_and_keeps_the_reason(session):
    assert session.submit_ruling(3, "neither", "cannot tell", 0.9) == {"accepted": False, "rejected_because": "neither"}
    [ruling] = session.close()
    assert ruling["pick"] == "neither" and ruling["why"] == "cannot tell"


def test_an_unknown_pick_counts_as_neither(session):
    assert session.submit_ruling(3, "banana", "x", 0.9)["rejected_because"] == "neither"


def test_a_bar_can_only_be_ruled_once(session):
    session.submit_ruling(2, "reader", "x", 0.9)
    assert session.submit_ruling(2, "reader", "again", 0.9) == {"accepted": False, "rejected_because": "already_ruled"}
    assert session.submit_ruling(2, "homr", "again", 0.9)["rejected_because"] == "already_ruled"
    assert len(session.close()) == 1


def test_a_pitch_out_of_range_is_rejected(photo):
    score = make_score([FOUR_QUARTERS, FOUR_QUARTERS])
    session = session_for(score, {1: FOUR_QUARTERS, 2: [("C7", "quarter")] * 4}, photo)
    assert session.submit_ruling(2, "reader", "x", 0.9) == {"accepted": False, "rejected_because": "range"}


def test_a_key_contradiction_is_shown_but_does_not_reject(photo):
    score = make_score([FOUR_QUARTERS, FOUR_QUARTERS], key_fifths=1)
    session = session_for(score, {1: FOUR_QUARTERS, 2: [("F4", "quarter")] * 4}, photo)
    assert session.get_bar(2)["reader"]["checks"]["key_ok"] is False
    assert session.submit_ruling(2, "reader", "x", 0.9)["accepted"] is True


def test_a_missing_reading_is_rejected(photo):
    score = make_score([FOUR_QUARTERS] * 4)
    session = session_for(score, {1: FOUR_QUARTERS, 2: FOUR_QUARTERS, 4: FOUR_QUARTERS}, photo)  # no reader bar 3
    assert session.get_bar(3)["reader"] is None
    assert session.submit_ruling(3, "reader", "x", 0.9) == {"accepted": False, "rejected_because": "no_reading"}


def test_rulings_after_close_are_refused(session):
    session.close()
    assert session.submit_ruling(2, "reader", "late", 0.9) == {"accepted": False, "rejected_because": "run_over"}
    assert session.close() == []


def test_bad_confidence_counts_as_zero(session):
    assert session.submit_ruling(2, "reader", "x", "high")["rejected_because"] == "low_confidence"  # type: ignore[arg-type]


def test_at_most_twenty_bars_are_refereed(photo):
    score = make_score([FOUR_QUARTERS] * 60)
    reading = {n: D5_QUARTERS if n <= 25 else FOUR_QUARTERS for n in range(1, 61)}
    session = session_for(score, reading, photo)
    assert [e["bar"] for e in session.list_doubtful_bars()] == list(range(1, config.MAX_BARS_REFEREED + 1))
    assert session.get_bar(21) == {"error": "unknown_bar"}


def test_every_tool_call_and_ruling_is_traced(session):
    session.list_doubtful_bars()
    session.get_bar(2)
    session.submit_ruling(2, "reader", "four beats", 0.9)
    events = [(e["agent"], e["event"], e["name"]) for e in session._trace.events]
    assert events == [("referee", "tool", "list_doubtful_bars"), ("referee", "tool", "get_bar"),
                      ("referee", "ruling", "bar 2")]
    assert "accepted" in session._trace.events[-1]["detail"]


def test_look_at_bar_sends_the_whole_photo_when_bar_positions_are_unknown(session, photo):
    result = session.look_at_bar(2)
    assert result["status"] == "success"
    assert result["content"] == [{"image": {"format": "png", "source": {"bytes": photo.read_bytes()}}}]


def test_look_at_bar_crops_to_the_bar_when_its_position_is_known(tmp_path):
    picture = tmp_path / "photo.png"
    Image.new("RGB", (200, 100), "white").save(picture)
    score = make_score([FOUR_QUARTERS, FOUR_QUARTERS])
    session = session_for(score, {1: FOUR_QUARTERS, 2: D5_QUARTERS}, picture, bar_boxes={2: (100, 0, 200, 50)})
    block = session.look_at_bar(2)["content"][0]["image"]
    assert block["format"] == "png"
    assert Image.open(io.BytesIO(block["source"]["bytes"])).size == (100, 50)


def test_a_failed_crop_falls_back_to_the_whole_photo(session, photo):
    session._bar_boxes = {2: (0, 0, 10, 10)}  # the photo is not a real image, so cropping fails
    assert session.look_at_bar(2)["content"][0]["image"]["source"]["bytes"] == photo.read_bytes()


def test_no_photo_at_all_gives_no_image(session, photo):
    photo.unlink()
    assert session.look_at_bar(2) == {"error": "no_image"}


def test_strands_tools_are_bound_to_the_session(session):
    tools = {t.tool_name: t for t in session.strands_tools()}
    assert set(tools) == {"list_doubtful_bars", "get_bar", "look_at_bar", "submit_ruling"}
    assert tools["submit_ruling"].tool_spec["inputSchema"]["json"]["required"] == ["bar", "pick", "why", "confidence"]

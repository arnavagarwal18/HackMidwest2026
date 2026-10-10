import pytest

from app.agents.checker import check_feedback

LATE_TEXT = "Bar 3 is late by about 88 ms on 2 notes."


def claim(type, id, value, field=None, time_s=None):
    return {"type": type, "id": id, "field": field, "value": value, "time_s": time_s}


def late_claims():
    return [
        claim("timing_ms", "p:t1:1", 88),
        claim("direction", "p:t1:1", "late"),
        claim("count", "p:t1:1", 2, field="late"),
        claim("bar", "p:t1:1", 3),
    ]


def sentence(text=LATE_TEXT, cites=("p:t1:1",), claims=None, jump=None):
    return {
        "text": text,
        "cites": list(cites),
        "claims": late_claims() if claims is None else claims,
        "jump": {"bar": 3, "time_s": None} if jump is None else jump,
    }


def output(*sentences, problem_ids=("p:t1:1",)):
    return {"sentences": list(sentences), "problem_ids": list(problem_ids)}


def reasons(result):
    return [p["reason"] for p in result["problems"]]


def assert_fails_with(result, prefix):
    assert not result["ok"]
    assert any(r.startswith(prefix) for r in reasons(result)), reasons(result)


def test_correct_sentence_passes(check_ctx):
    result = check_feedback(output(sentence()), check_ctx)
    assert result == {"ok": True, "problems": [], "claims_checked": 4, "claims_failed": 0}


def test_wrong_count_fails(check_ctx):
    bad = sentence(
        text="Bars 2 and 4 have 3 wrong notes.",
        cites=["p:t1:0"],
        claims=[claim("count", "p:t1:0", 3, field="wrong"), claim("bar", "p:t1:0", 2), claim("bar", "p:t1:0", 4)],
        jump={"bar": 2, "time_s": None},
    )
    result = check_feedback(output(bad, problem_ids=("p:t1:0",)), check_ctx)
    assert_fails_with(result, "count mismatch")
    assert result["claims_failed"] == 1
    assert result["problems"][0]["index"] == 0
    assert result["problems"][0]["claim"]["value"] == 3


def test_wrong_direction_claim_fails(check_ctx):
    bad = sentence(text="Bar 3 is early.", claims=[claim("direction", "p:t1:1", "early")])
    assert_fails_with(check_feedback(output(bad), check_ctx), "direction mismatch")


def test_direction_word_without_claim_fails(check_ctx):
    bad = sentence(text="Bar 3 is late.", claims=[claim("bar", "p:t1:1", 3)])
    assert_fails_with(check_feedback(output(bad), check_ctx), "unclaimed direction")


def test_direction_synonym_matches_claim(check_ctx):
    good = sentence(
        text="Bar 4 is fast by 6%.",
        cites=["b:t1:4"],
        claims=[claim("direction", "b:t1:4", "rushing"), claim("tempo_pct", "b:t1:4", 6)],
        jump={"bar": 4, "time_s": None},
    )
    assert check_feedback(output(good), check_ctx)["ok"]


def test_timing_off_by_thirty_percent_fails(check_ctx):
    bad = sentence(
        text="Bar 3 is late by about 114 ms on 2 notes.",
        claims=[claim("timing_ms", "p:t1:1", 114), claim("direction", "p:t1:1", "late"), claim("count", "p:t1:1", 2, "late")],
    )
    assert_fails_with(check_feedback(output(bad), check_ctx), "timing mismatch")


def test_timing_within_tolerance_passes(check_ctx):
    near = sentence(
        text="Bar 3 is late by about 95 ms.",
        claims=[claim("timing_ms", "p:t1:1", 95), claim("direction", "p:t1:1", "late")],
    )
    assert check_feedback(output(near), check_ctx)["ok"]


def test_unknown_id_fails(check_ctx):
    bad = sentence(cites=["n:t1:9:9"], claims=[], text="Bar 3 needs work.")
    assert_fails_with(check_feedback(output(bad), check_ctx), "unknown id")


def test_unknown_claimed_id_is_reported_once(check_ctx):
    bad = sentence(claims=[*late_claims(), claim("count", "n:t1:9:9", 1, "wrong")], text=LATE_TEXT + " 1")
    result = check_feedback(output(bad), check_ctx)
    assert reasons(result).count("unknown id: n:t1:9:9") == 1


def test_uncited_sentence_fails(check_ctx):
    bad = sentence(cites=[], claims=[], text="Keep practising.")
    assert_fails_with(check_feedback(output(bad), check_ctx), "uncited")


def test_stray_number_in_text_fails(check_ctx):
    bad = sentence(text="Bar 3 is late by about 88 ms on 7 notes.")
    result = check_feedback(output(bad), check_ctx)
    assert_fails_with(result, "stray number: 7")
    assert result["claims_failed"] == 0


def test_time_in_text_matches_jump_time(check_ctx):
    good = sentence(
        text="Your elbow drops around 0:10.",
        cites=["f:t1:0"],
        claims=[claim("form", "f:t1:0", "elbow_height", time_s=10.2), claim("direction", "f:t1:0", "low")],
        jump={"bar": None, "time_s": 10.2},
    )
    assert check_feedback(output(good, problem_ids=("p:t1:2",)), check_ctx)["ok"]


def test_form_time_outside_flag_fails(check_ctx):
    bad = sentence(
        text="Your elbow drops around 0:20.",
        cites=["f:t1:0"],
        claims=[claim("form", "f:t1:0", "elbow_height", time_s=20)],
        jump={"bar": None, "time_s": None},
    )
    assert_fails_with(check_feedback(output(bad, problem_ids=("p:t1:2",)), check_ctx), "form mismatch")


def test_citing_uncertain_note_fails(check_ctx):
    bad = sentence(text="Bar 3 note 3 is off.", cites=["n:t1:3:2"], claims=[claim("bar", "n:t1:3:2", 3)])
    assert_fails_with(check_feedback(output(bad), check_ctx), "uncertain note")


def test_claiming_uncertain_note_fails(check_ctx):
    bad = sentence(claims=[*late_claims(), claim("pitch", "n:t1:3:2", "D6")], text=LATE_TEXT)
    assert_fails_with(check_feedback(output(bad), check_ctx), "uncertain note")


def test_jump_to_uncited_bar_fails(check_ctx):
    bad = sentence(jump={"bar": 1, "time_s": None})
    assert_fails_with(check_feedback(output(bad), check_ctx), "bad jump")


def test_jump_to_time_outside_flags_fails(check_ctx):
    bad = sentence(jump={"bar": 3, "time_s": 50.0})
    assert_fails_with(check_feedback(output(bad), check_ctx), "bad jump")


def test_pitch_and_bar_claims_checked(check_ctx):
    good = sentence(
        text="In bar 2 you played F#5 instead of G5.",
        cites=["n:t1:2:1"],
        claims=[claim("pitch", "n:t1:2:1", "F#5"), claim("bar", "n:t1:2:1", 2)],
        jump={"bar": 2, "time_s": None},
    )
    assert check_feedback(output(good, problem_ids=("p:t1:0",)), check_ctx)["ok"]
    wrong_pitch = sentence(
        text="In bar 2 you played G#5.",
        cites=["n:t1:2:1"],
        claims=[claim("pitch", "n:t1:2:1", "G#5"), claim("bar", "n:t1:2:1", 2)],
        jump={"bar": 2, "time_s": None},
    )
    assert_fails_with(check_feedback(output(wrong_pitch, problem_ids=("p:t1:0",)), check_ctx), "pitch mismatch")
    wrong_bar = sentence(
        text="In bar 3 you played F#5.",
        cites=["n:t1:2:1"],
        claims=[claim("pitch", "n:t1:2:1", "F#5"), claim("bar", "n:t1:2:1", 3)],
        jump={"bar": 3, "time_s": None},
    )
    assert_fails_with(check_feedback(output(wrong_bar, problem_ids=("p:t1:0",)), check_ctx), "bar mismatch")


def test_note_direction_follows_sign_of_cents(check_ctx):
    sharp = sentence(
        text="The first note in bar 4 is sharp.",
        cites=["n:t1:4:0"],
        claims=[claim("direction", "n:t1:4:0", "sharp"), claim("bar", "n:t1:4:0", 4)],
        jump={"bar": 4, "time_s": None},
    )
    assert check_feedback(output(sharp), check_ctx)["ok"]
    flat = {**sharp, "text": "The first note in bar 4 is flat.", "claims": [claim("direction", "n:t1:4:0", "flat")]}
    assert_fails_with(check_feedback(output(flat), check_ctx), "direction mismatch")


def test_tempo_pct_tolerance(check_ctx):
    def run(value):
        s = sentence(
            text=f"Bar 3 drags by {value}%.",
            cites=["b:t1:3"],
            claims=[claim("tempo_pct", "b:t1:3", value), claim("direction", "b:t1:3", "dragging")],
            jump={"bar": 3, "time_s": None},
        )
        return check_feedback(output(s), check_ctx)

    assert run(8)["ok"]
    assert_fails_with(run(5), "tempo mismatch")


def test_sentence_over_thirty_words_fails(check_ctx):
    long = sentence(text="Bar 3 " + "really " * 30 + "matters.", claims=[claim("bar", "p:t1:1", 3)])
    assert_fails_with(check_feedback(output(long), check_ctx), "text too long")


@pytest.mark.parametrize(
    "bad_output",
    [
        None,
        {"sentences": [], "problem_ids": ["p:t1:1"]},
        {"sentences": [sentence()] * 7, "problem_ids": ["p:t1:1"]},
        {"sentences": [sentence()], "problem_ids": []},
        {"sentences": [sentence()], "problem_ids": ["p:t1:1", "p:t1:0", "p:t1:2", "p:t1:3"]},
    ],
)
def test_output_shape_limits(check_ctx, bad_output):
    assert not check_feedback(bad_output, check_ctx)["ok"]


def test_problem_id_must_exist(check_ctx):
    assert_fails_with(check_feedback(output(sentence(), problem_ids=("p:t1:99",)), check_ctx), "unknown id")


def test_malformed_claim_is_reported_not_raised(check_ctx):
    bad = sentence(claims=[{"type": "count", "id": "b:t1:2", "field": "wrong", "value": "two"}, "nonsense"])
    result = check_feedback(output(bad), check_ctx)
    assert_fails_with(result, "bad claim")
    assert result["claims_failed"] == 2


def test_failing_lookup_is_logged_and_rejected(check_ctx, caplog):
    def broken(item_id):
        raise RuntimeError("store offline")

    check_ctx.lookup = broken
    result = check_feedback(output(sentence()), check_ctx)
    assert_fails_with(result, "unknown id")
    assert "lookup failed" in caplog.text

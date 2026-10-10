import pytest

from app.agents.chat_checker import check_reply, states_a_measurement
from tests.test_checker_feedback import assert_fails_with, sentence
from tests.test_coach_hook import wrong_sentence


def plain(text="Keep your breath steady and your lips relaxed."):
    return {"text": text, "cites": [], "claims": [], "jump": {"bar": None, "time_s": None}}


def reply(*sentences):
    return {"sentences": list(sentences)}


def test_an_uncited_plain_sentence_passes(check_ctx):
    assert check_reply(reply(plain()), check_ctx) == {"ok": True, "problems": [], "claims_checked": 0, "claims_failed": 0}


def test_a_cited_and_claimed_sentence_passes(check_ctx):
    assert check_reply(reply(plain(), sentence()), check_ctx)["ok"]


@pytest.mark.parametrize("text", [
    "You played 3 notes wrong.", "Bar three was rough.", "That was a little late.", "Try it slower than that, so slow.",
    "Your top note was too high.", "The F# was a bit off.", "Watch the C in the middle.", "The Bb came out thin.",
])
def test_an_uncited_sentence_with_a_number_direction_or_note_fails(check_ctx, text):
    assert_fails_with(check_reply(reply(plain(text)), check_ctx), "uncited")


@pytest.mark.parametrize("text", [
    "A good warm-up helps.", "Be gentle with your embouchure.", "Breathe from your belly.", "Well done on that run.",
])
def test_words_that_only_look_like_notes_or_directions_stay_plain(text):
    assert not states_a_measurement(text)


def test_a_plain_sentence_citing_an_unknown_id_is_still_checked(check_ctx):
    bad = {**plain(), "cites": ["p:t1:99"]}
    assert_fails_with(check_reply(reply(bad), check_ctx), "unknown id")


def test_a_plain_sentence_over_the_word_limit_fails(check_ctx):
    assert_fails_with(check_reply(reply(plain(" ".join(["calm"] * 31))), check_ctx), "text too long")


def test_a_wrong_claim_fails_like_coach_feedback(check_ctx):
    assert_fails_with(check_reply(reply(wrong_sentence()), check_ctx), "count mismatch")


@pytest.mark.parametrize("sentences", [[], [plain()] * 7])
def test_the_sentence_count_is_1_to_6(check_ctx, sentences):
    assert_fails_with(check_reply(reply(*sentences), check_ctx), "bad sentence count")


def test_a_malformed_reply_is_rejected_not_raised(check_ctx):
    assert_fails_with(check_reply("nope", check_ctx), "bad sentence count")
    assert_fails_with(check_reply(reply({"cites": []}), check_ctx), "bad sentence")

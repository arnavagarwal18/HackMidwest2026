"""The Checker's rule for the Instructor's chat replies.

Each sentence gets the Coach's sentence checks, except that a sentence which states no number, no direction
and no note may have no citation. Anything that states one of those is checked exactly like Coach feedback.
"""
import re
from typing import Any

from app.agents.checker import SENTENCE_COUNT, check_sentence
from app.agents.context import CheckContext
from app.agents.report import Report

UNCITED_PREFIX = "uncited"  # the start of the Coach rule's reason for a sentence with no citation
DIRECTION_WORDS = ("late", "early", "sharp", "flat", "rushing", "dragging", "fast", "slow", "high", "low")
NUMBER_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
                "twice", "thrice", "half", "double")

_DIRECTION = re.compile(rf"\b(?:{'|'.join(DIRECTION_WORDS)})\b", re.IGNORECASE)
_NUMBER = re.compile(rf"\d|\b(?:{'|'.join(NUMBER_WORDS)})\b", re.IGNORECASE)
# A note name is a capital letter A-G with an accidental or an octave ("F#", "Bb", "C5"); a bare B-G also counts, a bare A is the article.
_NOTE_NAME = re.compile(r"(?<![\w#♯♭])(?:[B-G][#♯♭b]?|A[#♯♭b])(?![\w#♯♭])")


def states_a_measurement(text: str) -> bool:
    """True when the text has a number, a direction word or a note name, so it must be cited and claimed."""
    return bool(_NUMBER.search(text) or _DIRECTION.search(text) or _NOTE_NAME.search(text))


def _may_be_uncited(sentence: Any) -> bool:
    if not isinstance(sentence, dict) or not isinstance(sentence.get("text"), str):
        return False
    return not sentence.get("cites") and not sentence.get("claims") and not states_a_measurement(sentence["text"])


def check_reply(output: Any, ctx: CheckContext) -> dict:
    """Check the Instructor's reply { sentences }.

    Returns { ok, problems: [{ index, claim, reason }], claims_checked, claims_failed }.
    """
    report = Report()
    sentences = output.get("sentences") if isinstance(output, dict) else None
    if not isinstance(sentences, list) or not SENTENCE_COUNT[0] <= len(sentences) <= SENTENCE_COUNT[1]:
        report.add(None, f"bad sentence count: need {SENTENCE_COUNT[0]} to {SENTENCE_COUNT[1]} sentences")
        sentences = sentences if isinstance(sentences, list) else []
    for index, sentence in enumerate(sentences):
        with report.guard(index, "sentence"):
            check_sentence(index, sentence, ctx, report)
        if _may_be_uncited(sentence):
            report.problems = [p for p in report.problems if not (p["index"] == index and p["reason"].startswith(UNCITED_PREFIX))]
    return report.as_result()

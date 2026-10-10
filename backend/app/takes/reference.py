"""Reference notes the calibration page asks the learner to play, per instrument, at sounding pitch."""
from dataclasses import dataclass

from ..errors import AppError


@dataclass(frozen=True)
class ReferenceNote:
    name: str
    midi: int

    @property
    def hz(self) -> float:
        return 440.0 * 2 ** ((self.midi - 69) / 12)


REFERENCE_NOTES: dict[str, tuple[ReferenceNote, ...]] = {
    "violin": (ReferenceNote("D4", 62), ReferenceNote("A4", 69), ReferenceNote("E5", 76)),
    "trumpet": (ReferenceNote("Bb3", 58), ReferenceNote("F4", 65), ReferenceNote("Bb4", 70)),
}


def reference_notes(instrument: str | None) -> tuple[ReferenceNote, ...]:
    """The three reference notes (low, mid, high) for an instrument, or a 422 bad_request if it's unknown."""
    if instrument not in REFERENCE_NOTES:
        raise AppError(422, "bad_request", f"Pick an instrument: {', '.join(REFERENCE_NOTES)}.")
    return REFERENCE_NOTES[instrument]

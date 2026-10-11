"""Judging the Face Landmarker's readings: one Sample per sampled frame, for the embouchure rules in rules.py."""
from .episodes import Sample
from .face import FaceResult

FACE_UNAVAILABLE = "face_unavailable"  # reason in rules_skipped when the Face Landmarker could not run
CHEEK_PUFF, SMILE = "cheek_puff", "smile"  # FaceReading fields the rules measure
FOUND_VISIBILITY = 1.0  # the face was found in the frame, so the sample is as visible as it gets


def face_samples(measure: str, threshold: float, times: list[float], result: FaceResult) -> list[Sample]:
    """The frames judged against a rule that fires when `measure` is above `threshold`.

    Frames outside the notes are not past the threshold (a breath never flags); a frame inside a note where no face was
    found is missing.
    """
    samples = []
    for seconds in times:
        if seconds not in result.readings:
            samples.append(Sample(None, 0.0, 0.0))
            continue
        reading = result.readings[seconds]
        if reading is None:
            samples.append(Sample(None, None, 0.0))
        else:
            value = getattr(reading, measure)
            samples.append(Sample(value, value - threshold, FOUND_VISIBILITY))
    return samples

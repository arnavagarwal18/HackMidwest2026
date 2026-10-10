"""Error type for bad input to note diagnosis."""
import logging

logger = logging.getLogger("app.diagnosis")


class DiagnosisInputError(ValueError):
    """The score, played notes or take can't be diagnosed; the message says what to fix."""


def input_error(message: str) -> DiagnosisInputError:
    """Log the problem durably and return the error to raise."""
    logger.warning("diagnosis input error: %s", message)
    return DiagnosisInputError(message)

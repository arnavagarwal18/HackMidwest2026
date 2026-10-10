"""Error type for bad input to note diagnosis."""
import logging

from app.errors import AppError

logger = logging.getLogger("app.diagnosis")

BAD_INPUT_STATUS = 422
BAD_INPUT_CODE = "bad_diagnosis_input"


class DiagnosisInputError(AppError, ValueError):
    """The score, played notes or take can't be diagnosed; the message says what to fix."""

    def __init__(self, message: str):
        super().__init__(BAD_INPUT_STATUS, BAD_INPUT_CODE, message)


def input_error(message: str) -> DiagnosisInputError:
    """Log the problem durably and return the error to raise."""
    logger.warning("diagnosis input error: %s", message)
    return DiagnosisInputError(message)

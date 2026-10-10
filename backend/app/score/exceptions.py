"""Errors raised by the score package."""


class BadScoreFile(Exception):
    """The uploaded file can't be parsed as a score, or contains no notes."""


class NotConfirmed(Exception):
    """The session's score has not been confirmed by the user yet."""


class BuiltinNotFound(Exception):
    """No built-in piece has the requested piece_id."""


class NoNotes(BadScoreFile):
    """The file was read but holds no notes."""


class ScanError(Exception):
    """A photo scan failed; `code` is the score_error value the front end sees."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code

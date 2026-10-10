"""Errors raised by the score package."""


class BadScoreFile(Exception):
    """The uploaded file can't be parsed as a score, or contains no notes."""


class NotConfirmed(Exception):
    """The session's score has not been confirmed by the user yet."""

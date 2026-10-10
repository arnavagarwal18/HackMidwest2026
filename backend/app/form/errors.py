"""Errors the form analysis raises; the caller maps `code` onto take.form."""


class FormError(Exception):
    """A failure the learner can be told about: `code` is stable, `message` is for the screen."""

    code = "form_error"
    message = "Form analysis failed."

    def __init__(self, detail: str = ""):
        super().__init__(detail or self.message)


class VideoUnreadable(FormError):
    code = "video_unreadable"
    message = "Could not read the video frames."


class FormUnavailable(FormError):
    code = "form_unavailable"
    message = "Form analysis isn't available on this computer."

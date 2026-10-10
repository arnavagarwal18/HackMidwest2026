"""Errors the form analysis raises; the caller maps `code` and `message` onto take.form.error."""


class FormError(Exception):
    """A failure the learner can be told about: `code` is stable, `message` is for the screen."""

    code = "form_error"
    message = "Form analysis failed."

    def __init__(self, detail: str = ""):
        super().__init__(detail or self.message)

    @classmethod
    def as_dict(cls) -> dict:
        """The take.form.error value for this kind of failure."""
        return {"code": cls.code, "message": cls.message}


class VideoUnreadable(FormError):
    code = "video_unreadable"
    message = "Could not read the video frames."


class FormUnavailable(FormError):
    code = "form_unavailable"
    message = "Form check unavailable on this computer."


class TrackingPoor(FormError):
    code = "tracking_poor"
    message = "We could not see you clearly in most of the video."


class FormFailed(FormError):
    """Any unexpected failure; the cause is logged, not shown."""

    code = "form_failed"
    message = "Form check failed on this take."

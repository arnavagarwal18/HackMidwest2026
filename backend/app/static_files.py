"""Static file serving that makes browsers revalidate on every load."""
from starlette.staticfiles import StaticFiles


class RevalidatingStaticFiles(StaticFiles):
    """Marks every file response `Cache-Control: no-cache`.

    The browser still keeps its copy, but must ask first; ETag/Last-Modified
    turn that ask into a cheap 304 when nothing changed. This stops a stale
    cached module from pairing with a newer one after a git pull.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response

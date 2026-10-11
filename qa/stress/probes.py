"""One-off requests whose answer we read (not time): each is kept as a row with the status and the start of the body."""
from dataclasses import asdict, dataclass

from client import StressClient

BODY_SNIPPET_CHARS = 120


@dataclass
class ProbeResult:
    group: str
    case: str
    status: int | None
    body: str


class Prober:
    def __init__(self, client: StressClient, group: str):
        self.client = client
        self.group = group
        self.results: list[ProbeResult] = []
        self.after_5xx_checks = 0  # throwaway requests sent right after a 5xx
        self.after_5xx_dropped = 0  # ...of which found the connection closed (ReadError / disconnect)

    async def probe(self, case: str, method: str, path: str, **kwargs):
        response = await self.client.call(f"probe: {self.group}", method, path, **kwargs)
        body = "(no response: timeout or connection error)" if response is None else response.text[:BODY_SNIPPET_CHARS].replace("\n", " ")
        status = None if response is None else response.status_code
        self.results.append(ProbeResult(self.group, case, status, body))
        if status is not None and status >= 500:
            await self._check_connection_after_5xx()
        return response

    async def _check_connection_after_5xx(self) -> None:
        """The server drops the kept-alive connection after an unhandled error; a throwaway GET absorbs that so the next probe isn't blamed."""
        reply = await self.client.call("probe: throwaway GET /builtins right after a 5xx", "GET", "/builtins")
        self.after_5xx_checks += 1
        self.after_5xx_dropped += reply is None

    def as_dicts(self) -> list[dict]:
        return [asdict(r) for r in self.results]

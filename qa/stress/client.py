"""One shared HTTP client: caps concurrency, times every request, never lets an error escape unrecorded."""
import asyncio
import logging
import time

import httpx

from config import KEEPALIVE_EXPIRY_S, MAX_CONCURRENCY, REQUEST_TIMEOUT_S, check_base_url
from stats import Recorder, Sample

logger = logging.getLogger("stress.client")


class StressClient:
    def __init__(self, base_url: str, recorder: Recorder):
        self.recorder = recorder
        self._slots = asyncio.Semaphore(MAX_CONCURRENCY)
        # uvicorn closes idle keep-alive connections after 5 s; expiring ours sooner stops stale-connection ReadErrors being blamed on the server
        self._http = httpx.AsyncClient(base_url=check_base_url(base_url), timeout=REQUEST_TIMEOUT_S,
                                       limits=httpx.Limits(keepalive_expiry=KEEPALIVE_EXPIRY_S))

    async def close(self) -> None:
        await self._http.aclose()

    async def call(self, route: str, method: str, path: str, **kwargs) -> httpx.Response | None:
        """Send one request, record (route, status, latency); None when no response came back."""
        async with self._slots:
            started = time.monotonic()
            try:
                response = await self._http.request(method, path, **kwargs)
            except httpx.HTTPError as exc:
                error = f"{type(exc).__name__}"
                logger.warning("%s %s failed: %s %s", method, path[:80], error, exc)
                self.recorder.add(Sample(route, None, time.monotonic() - started, error))
                return None
            self.recorder.add(Sample(route, response.status_code, time.monotonic() - started))
            return response

    async def json(self, route: str, method: str, path: str, **kwargs) -> dict | None:
        """Like call, but the parsed JSON body (None when there was no usable response)."""
        response = await self.call(route, method, path, **kwargs)
        if response is None:
            return None
        try:
            return response.json()
        except ValueError:
            logger.warning("%s %s returned non-JSON (%s): %r", method, path[:80], response.status_code, response.text[:100])
            return None

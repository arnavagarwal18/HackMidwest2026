"""Limits and addresses for the stress run. Refuses the owner's live servers outright."""
from pathlib import Path
from urllib.parse import urlparse

OWNER_PORTS = (8000, 8001)
BASE_URL = "http://127.0.0.1:8110"
MAX_CONCURRENCY = 20  # owner's cap on simultaneous requests
HANG_THRESHOLD_S = 30.0
KEEPALIVE_EXPIRY_S = 2.0  # below uvicorn's 5 s keep-alive timeout
REQUEST_TIMEOUT_S = 60.0  # lets a hang show up as a >30 s sample instead of a client-side cut
MEMORY_SAMPLE_INTERVAL_S = 2.0
OUT_DIR = Path(__file__).resolve().parent / "out"
RESULTS_JSON = OUT_DIR / "results.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = REPO_ROOT / "data" / "sessions"
MIB = 1024 * 1024


def check_base_url(url: str) -> str:
    """Return url if it targets this machine on a port that isn't one of the owner's live servers."""
    parsed = urlparse(url)
    if parsed.hostname != "127.0.0.1" or parsed.port in OWNER_PORTS or parsed.port is None:
        raise SystemExit(f"Refusing {url}: use 127.0.0.1 on your own port (never {OWNER_PORTS}).")
    return url

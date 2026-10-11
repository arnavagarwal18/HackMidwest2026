"""Live Bedrock smoke test: run each AI path of the app once and report pass or fail, seconds and the Checker's verdict.

    RUN_LIVE_BEDROCK=1 .venv/bin/python scripts/live_bedrock_smoke.py [--out results.json]

Without RUN_LIVE_BEDROCK=1 it prints a skip message and exits 0, so nothing reaches Bedrock by accident. With it, from backend/:
  1. settings: AI_ENABLED is true and the BEDROCK_ names are set (names only are printed, never a value);
  2. the Ode to Joy take (testdata/ode_to_joy) through the FastAPI app, whose pipeline runs the Coach, Planner and Checker;
  3. one Instructor chat turn on that take.
Everything runs in this process against a temporary data folder. A row passes only when the AI's output was used, so
a fallback fails with its reason code (checker_rejected, timeout, model_error ...). The results go to a JSON file
(default backend/.venv/scratch/live_bedrock_smoke.json, errors in the .log next to it) and a table on stdout.
Exit code: 0 when every row passed, 1 otherwise. One run costs one feedback run and one chat turn.
"""
import argparse
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
for folder in (SCRIPTS_DIR, BACKEND_DIR):  # the sibling helpers, and the app package
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from live_smoke_report import PASS, StepResult, payload_of, skipped, table_lines, write_json  # noqa: E402

FLAG = "RUN_LIVE_BEDROCK"
DEFAULT_OUT = BACKEND_DIR / ".venv" / "scratch" / "live_bedrock_smoke.json"
REQUIRED_SETTINGS = {"BEDROCK_REGION": "region", "BEDROCK_TEXT_MODEL": "text_model", "BEDROCK_VISION_MODEL": "vision_model"}
logger = logging.getLogger("live_bedrock_smoke")


def _load_settings():
    from app.agents.config import get_settings
    return get_settings()


def check_settings() -> tuple[StepResult, dict[str, bool]]:
    """The settings row, and which required names are set. Names only: no value is read out or printed."""
    from app.agents.config import ENV_FILE, ConfigError
    print(f"backend/.env: {'found' if ENV_FILE.is_file() else 'not found (the process environment is used)'}")
    result = StepResult("settings")
    try:
        settings = _load_settings()
    except ConfigError:
        logger.exception("The AI settings could not be loaded")
        result.reason, result.note = "bad_settings", "a setting is missing or wrong; see backend/.env.example"
        return result, {}
    present = {name: bool(getattr(settings, attribute)) for name, attribute in REQUIRED_SETTINGS.items()}
    print("settings present: " + ", ".join(f"{name}={'yes' if ok else 'NO'}" for name, ok in present.items())
          + f", AWS_PROFILE={'yes' if settings.aws_profile else 'no (default credential chain)'}, AI_ENABLED={'true' if settings.ai_enabled else 'false'}")
    if not settings.ai_enabled:
        result.reason = "ai_disabled"
    elif not all(present.values()):
        result.reason = "settings_missing"
    else:
        result.status = PASS
    return result, present


def run_steps(work_dir: Path, take_source: Callable | None = None) -> list[StepResult]:
    """The feedback and chat rows, run against a temporary sessions folder inside `work_dir`."""
    import live_smoke_steps as steps
    from fastapi.testclient import TestClient

    from app import store
    from app.main import app

    original_root = store.SESSIONS_ROOT
    store.SESSIONS_ROOT = work_dir / "sessions"
    store._sessions.clear()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        taken, crashed = steps.guarded("take flow", lambda: (take_source or steps.take_flow)(client))
        if crashed:
            return [crashed, skipped("feedback: coach", "no take"), skipped("feedback: planner", "no take"), skipped("instructor chat", "no take")]
        session_id, take_id = taken
        return [*steps.feedback_step(client, session_id, take_id), steps.chat_step(client, session_id)]
    finally:
        store.SESSIONS_ROOT = original_root
        store._sessions.clear()


def run_live(out: Path, take_source: Callable | None = None) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    log_handler = logging.FileHandler(out.with_suffix(".log"), mode="w", encoding="utf-8")
    log_handler.setLevel(logging.ERROR)
    logging.getLogger().addHandler(log_handler)  # every error the app logs during the run, for the reason codes
    try:
        return _run_and_report(out, take_source)
    finally:
        logging.getLogger().removeHandler(log_handler)
        log_handler.close()


def _run_and_report(out: Path, take_source: Callable | None) -> int:
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    settings_row, present = check_settings()
    results = [settings_row]
    if settings_row.passed:
        with tempfile.TemporaryDirectory(prefix="live_bedrock_smoke_") as work_dir:
            results += run_steps(Path(work_dir), take_source)
    print("\n".join(table_lines(results)))
    if not write_json(out, payload_of(results, present, started_at)):
        print(f"FAILED: could not write the results to {out} (details: {out.with_suffix('.log').name})", file=sys.stderr)
        return 1
    print(f"results: {out}")
    return 0 if all(r.passed for r in results) else 1


def main(argv: list[str] | None = None) -> int:
    if os.environ.get(FLAG) != "1":
        print(f"Skipped: set {FLAG}=1 to run the live Bedrock smoke test (it calls AWS and uses quota).")
        return 0
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where to save the results JSON (default: %(default)s)")
    return run_live(parser.parse_args(argv).out)


if __name__ == "__main__":
    sys.exit(main())

"""Rollback for instrument personas: remove the 'persona' key from every stored session file.

Code from before personas can't load a session file with the key (the Session record has no such field), so run this
before rolling the backend back. Run from backend/: python scripts/strip_session_persona.py [sessions_root]
"""
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import store  # noqa: E402

log = logging.getLogger("strip_session_persona")


def strip_persona(session_file: Path) -> bool:
    """Remove the persona key from one session file, in place. True when the file had one; raises OSError or ValueError if it can't be read or written."""
    data = json.loads(session_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{session_file} does not hold a session object")
    if "persona" not in data:
        return False
    del data["persona"]
    temp = session_file.with_name(session_file.name + ".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp, session_file)
    return True


def strip_all(sessions_root: Path) -> tuple[int, int]:
    """Strip every session under the root; returns (files changed, files that could not be processed)."""
    changed = failed = 0
    for session_file in sorted(sessions_root.glob(f"*/{store.SESSION_FILE}")):
        try:
            changed += strip_persona(session_file)
        except (OSError, ValueError):
            log.exception("Could not strip the persona from %s; fix or remove that file and run again", session_file)
            failed += 1
    return changed, failed


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO)
    root = Path(argv[1]) if len(argv) > 1 else store.SESSIONS_ROOT
    if not root.is_dir():
        log.error("No sessions folder at %s; pass the folder that holds the session folders", root)
        return 2
    changed, failed = strip_all(root)
    log.info("Stripped the persona from %d session file(s); %d could not be processed", changed, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

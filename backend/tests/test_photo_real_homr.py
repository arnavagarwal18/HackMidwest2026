"""Scans a real photo with real homr. Slow (model load plus inference), so it only runs with RUN_REAL_HOMR=1:

    RUN_REAL_HOMR=1 pytest tests/test_photo_real_homr.py -s
"""
import os
import time
from pathlib import Path

import pytest

from tests.test_score_photo import post_photo, status, wait_until_done

PHOTO = Path(__file__).parents[2] / "testdata" / "ode_to_joy_photo.jpg"

pytestmark = pytest.mark.skipif(os.environ.get("RUN_REAL_HOMR") != "1", reason="set RUN_REAL_HOMR=1 to run real homr")


def test_real_photo_scans_end_to_end(client):
    session_id = client.post("/sessions", json={"instrument": "violin"}).json()["session_id"]
    started = time.time()
    assert post_photo(client, session_id, data=PHOTO.read_bytes(), name=PHOTO.name).status_code == 202
    done = wait_until_done(client, session_id, seconds=300)
    print(f"real homr scan took {time.time() - started:.1f} s: {done}")
    assert done["score_status"] == "scanned", done
    assert done["bars"] == 16
    score = client.get(f"/sessions/{session_id}/score", params={"format": "json"}).json()
    names = [note["name"] for bar in score["bars"] for note in bar["notes"]]
    assert names[:4] == ["E4", "E4", "F4", "G4"]

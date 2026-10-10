"""Stands in for `python -m homr.main <image>` in tests. Behaviour comes from the STUB_HOMR_MODE env var.

ok:     copy STUB_HOMR_MUSICXML next to the image as <image stem>.musicxml
slow:   sleep 1 s, then do what ok does
hang:   sleep 30 s (the runner's time limit must kill it)
fail:   print an error and exit with code 3
silent: exit 0 without writing anything
"""
import os
import shutil
import sys
import time
from pathlib import Path

image = Path(sys.argv[1])
mode = os.environ["STUB_HOMR_MODE"]
if mode == "fail":
    print("homr stub: pretending to crash", file=sys.stderr)
    sys.exit(3)
if mode == "hang":
    time.sleep(30)
if mode == "slow":
    time.sleep(1)
if mode in ("ok", "slow"):
    shutil.copy(os.environ["STUB_HOMR_MUSICXML"], image.with_suffix(".musicxml"))

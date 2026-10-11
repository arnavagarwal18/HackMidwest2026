import sys
from pathlib import Path

import pytest

pytest.importorskip("yt_dlp")
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import fetch_youtube  # noqa: E402


def test_default_list_is_the_good_posture_set():
    assert fetch_youtube.pick_list(None) is fetch_youtube.GOOD_LIST
    assert fetch_youtube.GOOD_LIST.videos_dir.name == "videos"


def test_fault_list_has_its_own_folder_and_manifest():
    fault = fetch_youtube.pick_list(str(fetch_youtube.FAULT_CSV))
    assert fault is fetch_youtube.FAULT_LIST
    assert fault.videos_dir.name == "fault_videos"
    assert fault.manifest_path.name == "fault_manifest.csv"
    assert fault.group_column == "Scenario"


def test_unknown_list_is_refused():
    with pytest.raises(SystemExit, match="unknown --list"):
        fetch_youtube.pick_list("somewhere/else.csv")


def test_fault_csv_rows_all_have_a_video_id():
    rows = fetch_youtube.read_rows(fetch_youtube.FAULT_LIST, None, None)
    assert len(rows) == 21
    assert all(fetch_youtube.video_id(r["URL"]) for r in rows)

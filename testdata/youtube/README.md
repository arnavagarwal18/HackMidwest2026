# YouTube trumpet test videos

`videos.csv` is the owner's list of approved trumpet videos (mostly-perfect playing and posture); `manifest.csv` records what
each download produced (status, duration, resolution, size). The videos themselves are big, so `videos/` is **git-ignored**.

Fetch them all (mp4, up to 720p, into `testdata/youtube/videos/<id>.mp4`; existing files are skipped):

    backend/.venv/Scripts/python backend/scripts/fetch_youtube.py

Options: `--limit N`, `--only-group "Search group"`. Needs `pip install -r backend/requirements.txt -r backend/requirements-dev.txt`.

## Posture-fault candidates

`fault_candidates.csv` is the owner's sheet of videos that may show trumpet posture faults (21 rows; the original is
`trumpet_posture_fault_candidates.xlsx`, and the CSV keeps every column and the owner's wording; "Length" is shown as m:ss).
The "you verify" and "Fault one-liner" columns are still empty, so check each video before using it. Pass the sheet to the same
script with `--list`; the videos go into the git-ignored `testdata/youtube/fault_videos/<id>.mp4` and
`fault_manifest.csv` records each result (the good set's `videos/` and `manifest.csv` are untouched):

    # Windows
    backend/.venv/Scripts/python backend/scripts/fetch_youtube.py --list testdata/youtube/fault_candidates.csv

    # macOS
    backend/.venv/bin/python backend/scripts/fetch_youtube.py --list testdata/youtube/fault_candidates.csv

`--only-group` matches the sheet's "Scenario" column here. Some videos may be unavailable; they show as `failed: ...` in the
manifest and the run exits with code 1.

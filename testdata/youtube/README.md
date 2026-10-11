# YouTube trumpet test videos

`videos.csv` is the owner's list of approved trumpet videos (mostly-perfect playing and posture); `manifest.csv` records what
each download produced (status, duration, resolution, size). The videos themselves are big, so `videos/` is **git-ignored**.

Fetch them all (mp4, up to 720p, into `testdata/youtube/videos/<id>.mp4`; existing files are skipped):

    backend/.venv/Scripts/python backend/scripts/fetch_youtube.py

Options: `--limit N`, `--only-group "Search group"`. Needs `pip install -r backend/requirements.txt -r backend/requirements-dev.txt`.

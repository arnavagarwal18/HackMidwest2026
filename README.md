# Practice Coach (HackMidwest2026)

A music practice coach for violin and trumpet.

## Run

```
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000. On Windows, allow the app through Windows Firewall on private networks the first time it starts so other devices can reach it.

Copy `backend/.env.example` to `backend/.env` to configure AWS/Bedrock (`.env` is git-ignored).

## Test

```
cd backend
python -m pytest
```

## Layout

- `backend/app/` FastAPI app (`main.py`), session store (`store.py`), errors (`errors.py`), and packages `score/ takes/ diagnosis/ form/ agents/ practice/`
- `frontend/` static files served at `/`
- `data/sessions/` per-session JSON and files (git-ignored)
- `testdata/` sample videos and sheet music
- `docs/designs/` approved design notes

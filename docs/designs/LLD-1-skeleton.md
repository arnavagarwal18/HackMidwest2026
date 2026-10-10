# LLD-1 change 1: Back-end skeleton (approved design, verbatim)

LAYOUT: backend/app/main.py (FastAPI app), backend/app/store.py, backend/app/errors.py, backend/app/score/, takes/, diagnosis/, form/, agents/, practice/ (each a package with __init__.py), backend/tests/, frontend/ (static files served at /), testdata/, data/sessions/ (git-ignored). backend/requirements.txt pins every library version. Python 3.12.

SESSION (store.py): a dataclass held in a dict keyed by session_id, written to data/sessions/{session_id}/session.json after every change. Fields: session_id: str (uuid4 hex); instrument: 'violin'|'trumpet'; created_at: ISO-8601 str; score_status: 'none'|'scanning'|'scanned'|'failed'|'confirmed' (starts 'none'); score_error: str|null; doubtful_bars: list; double_checked: bool; calibration: dict|null; takes: dict[str,dict]; feedback: dict[str,dict]; plans: dict[str,dict]; progress: dict. Each part writes only its own key through store.update(session_id, key, value), which takes a per-session lock. Session files sit in the same folder. No database. Also provide store.get(session_id) (raise a SessionNotFound) and store.session_dir(session_id).

SHARED RULES: JSON in/out; uploads multipart with field 'file'. Server listens on 0.0.0.0:8000. Errors: HTTP 4xx/5xx with body {"error": {"code": str, "message": str (plain words a learner can read)}}. Common codes: 404 session_not_found, 413 file_too_large, 415 unsupported_type, 409 wrong_state, 422 bad_request (also map FastAPI validation errors to this shape), 500 storage_error. errors.py: an AppError(status, code, message) exception + handler.

ROUTES: POST /sessions {instrument:'violin'|'trumpet'} -> 201 {session_id, instrument}; other instrument -> 422 bad_request. GET /sessions/{id} -> 200 {session_id, instrument, score_status, has_calibration: bool, take_ids: [str]}; unknown -> 404 session_not_found.
Session folder can't be written -> 500 storage_error, message 'The app couldn't save your work. Tell the team.', log the path.

TESTS: POST /sessions violin -> 201 + session_id; 'piano' -> 422 bad_request; GET unknown id -> 404 session_not_found in the error shape. Storage failure -> 500 storage_error.

DONE: static serving of frontend/ at / (placeholder index.html ok), README with run command `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000` (note: allow Windows Firewall on private networks at first start), session tests pass, other parts can import store.update. Plus the testdata/ media copy.

LIBRARIES: fastapi, uvicorn, httpx, pytest, python-multipart, pinned in backend/requirements.txt.

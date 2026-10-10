"""Calibration routes: reference notes, live calibration from recorded clips, skip, and read back."""
import logging
import tempfile
from pathlib import Path

import librosa
import numpy as np
from fastapi import APIRouter, File, Form, UploadFile

from .. import store
from ..errors import AppError, storage_error
from . import calibrate, media_tools
from .reference import reference_notes
from .transcribe import SAMPLE_RATE
from .validation import ACCEPTED_TYPES, normalise_content_type

logger = logging.getLogger("app.takes.calibration")
router = APIRouter()

CLIP_TYPES = {content_type: ext for content_type, ext in ACCEPTED_TYPES.items() if ext in (".webm", ".ogg", ".wav")}
MAX_CLIP_S = 6.5  # clips are 1 to 6 seconds; a little slack for recorder timing
REF_FIELDS = ("ref_0", "ref_1", "ref_2")
INST_FIELDS = ("inst_0", "inst_1", "inst_2")


def _decode_clip(upload: UploadFile, field_name: str, max_seconds: float | None = None) -> np.ndarray:
    """Decode an uploaded clip to 16 kHz mono samples via ffmpeg."""
    content_type = normalise_content_type(upload.content_type)
    if content_type not in CLIP_TYPES:
        raise AppError(415, "unsupported_type", f"{field_name} isn't a supported audio type. Use webm, ogg or wav audio.")
    try:
        with tempfile.TemporaryDirectory(prefix="calibration-") as folder:
            source, wav = Path(folder) / f"upload{CLIP_TYPES[content_type]}", Path(folder) / "clip.wav"
            source.write_bytes(upload.file.read())
            media_tools.extract_wav(source, wav)
            audio, _ = librosa.load(str(wav), sr=SAMPLE_RATE, mono=True)
    except media_tools.MediaError as exc:
        logger.error("Could not decode calibration clip %s: %s", field_name, exc)
        raise AppError(422, "audio_unreadable", f"We couldn't read the recording for {field_name}. Record it again.") from exc
    except OSError as exc:
        logger.exception("Could not read calibration clip %s", field_name)
        raise storage_error() from exc
    if max_seconds is not None and len(audio) / SAMPLE_RATE > max_seconds:
        raise AppError(422, "bad_request", f"{field_name} is too long. Record 1 to 6 seconds of each note.")
    return audio


def _required(upload: UploadFile | None, field_name: str) -> UploadFile:
    if upload is None:
        raise AppError(422, "bad_request", f"Missing {field_name}.")
    return upload


def _parse_click_at_s(raw: str | None) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise AppError(422, "bad_request", "click_at_s must be a number of seconds.")
    if not np.isfinite(value) or value < 0:
        raise AppError(422, "bad_request", "click_at_s must be a number of seconds, 0 or more.")
    return value


def _fail(measurements: list[calibrate.NoteMeasurement]) -> AppError:
    failing = [m for m in measurements if m.problem]
    logger.info("Calibration failed: %s", [(m.asked, m.problem) for m in failing])
    return AppError(
        422, "calibration_failed", " ".join(calibrate.problem_message(m) for m in failing),
        {"notes": [{"asked": m.asked, "problem": m.problem, "cents": None if m.cents is None else round(m.cents, 2)}
                   for m in failing]},
    )


@router.get("/reference-notes")
def get_reference_notes(instrument: str | None = None) -> list[dict]:
    return [{"name": note.name, "hz": round(note.hz, 2)} for note in reference_notes(instrument)]


@router.post("/sessions/{session_id}/calibration")
def create_calibration(
    session_id: str,
    ref_0: UploadFile | None = File(None),
    ref_1: UploadFile | None = File(None),
    ref_2: UploadFile | None = File(None),
    click: UploadFile | None = File(None),
    click_at_s: str | None = Form(None),
    inst_0: UploadFile | None = File(None),
    inst_1: UploadFile | None = File(None),
    inst_2: UploadFile | None = File(None),
) -> dict:
    session = store.get(session_id)
    refs = [_required(upload, name) for upload, name in zip((ref_0, ref_1, ref_2), REF_FIELDS)]
    click_upload = _required(click, "click")
    click_at = _parse_click_at_s(click_at_s)
    instrument_uploads = [(u, n) for u, n in zip((inst_0, inst_1, inst_2), INST_FIELDS) if u is not None]

    notes = reference_notes(session.instrument)
    measurements = calibrate.measure_notes(
        [_decode_clip(upload, name, MAX_CLIP_S) for upload, name in zip(refs, REF_FIELDS)], session.instrument, notes
    )
    if any(m.problem for m in measurements):
        raise _fail(measurements)

    latency_ms = calibrate.measure_latency_ms(_decode_clip(click_upload, "click"), click_at)
    instrument_measurements = [
        calibrate.measure_note(_decode_clip(upload, name, MAX_CLIP_S), session.instrument, notes[int(name[-1])])
        for upload, name in instrument_uploads
    ]
    profile = calibrate.build_live_profile(
        measurements, latency_ms, calibrate.instrument_offset_cents(instrument_measurements)
    )
    store.update(session_id, "calibration", profile)
    return {"profile": profile}


@router.post("/sessions/{session_id}/calibration/skip")
def skip_calibration(session_id: str) -> dict:
    store.get(session_id)
    profile = calibrate.default_profile()
    store.update(session_id, "calibration", profile)
    return {"profile": profile}


@router.get("/sessions/{session_id}/calibration")
def get_calibration(session_id: str) -> dict:
    return {"profile": store.get(session_id).calibration}

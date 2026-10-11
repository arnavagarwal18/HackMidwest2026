"""Frames and tracking: sample a take's video, track the learner in each sampled frame, save {take}_tracks.json."""
import json
import logging
import os
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from .. import store
from ..errors import storage_error
from ..takes.take_store import get_take
from . import config
from .errors import VideoUnreadable
from .face import FaceReader, FaceResult
from .tracker import Tracker, downscale

logger = logging.getLogger("app.form.track")

SLOT_TOLERANCE = 1e-6  # keeps 0.1 s * 10 fps in slot 1 despite float error


@dataclass
class TrackResult:
    fps: float  # sampled frames per second of video
    width: int
    height: int
    frames: list[dict] = field(default_factory=list)  # {t, pose, left_hand, right_hand}
    warning: str | None = None  # set when the time limit cut the analysis short
    face: FaceResult | None = None  # embouchure readings; None when the face is not checked

    @property
    def frames_total(self) -> int:
        return len(self.frames)

    @property
    def frames_tracked(self) -> int:
        return sum(1 for frame in self.frames if frame["pose"] is not None)

    @property
    def tracking_quality(self) -> float:
        return self.frames_tracked / self.frames_total if self.frames_total else 0.0

    def to_file_dict(self) -> dict:
        return {"fps": self.fps, "width": self.width, "height": self.height, "frames": self.frames}


def tracks_path(session_id: str, take_id: str) -> Path:
    return store.session_dir(session_id) / f"{take_id}{config.TRACKS_FILE_SUFFIX}"


def _open_video(video_path: Path) -> tuple[cv2.VideoCapture, float]:
    """The opened video and the frame rate to use when its frames carry no timestamps (the reported rate if sane)."""
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        capture.release()
        raise VideoUnreadable(f"{video_path.name} can't be opened")
    reported_fps = capture.get(cv2.CAP_PROP_FPS)
    return capture, reported_fps if 0 < reported_fps <= config.MAX_NATIVE_FPS else config.FALLBACK_NATIVE_FPS


def _frame_time(capture: cv2.VideoCapture, index: int, fallback_fps: float, previous: float) -> float | None:
    """Video seconds of the frame just grabbed: its own timestamp, else index / fallback_fps.

    Browser recordings have variable frame rates, so the timestamp is the truth. None if neither grows past `previous`.
    """
    stamp_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
    for seconds in (stamp_ms / 1000 if stamp_ms == stamp_ms else None, index / fallback_fps):  # stamp_ms == stamp_ms drops NaN
        if seconds is not None and seconds > previous:
            return seconds
    return None


def _sample_slot(seconds: float) -> int:
    """Which 1 / FPS-second slot of the video this time falls in; the first frame of each slot is tracked."""
    return int(seconds * config.FPS + SLOT_TOLERANCE)


def _sampled_fps(frames: list[dict]) -> float:
    if len(frames) < 2:
        return float(config.FPS)
    return round((len(frames) - 1) / (frames[-1]["t"] - frames[0]["t"]), 2)


def track_video(video_path: Path, with_hands: bool, time_limit_s: float = config.TIME_LIMIT_S,
                clock: Callable[[], float] = time.monotonic,
                on_frame: Callable[[np.ndarray, float, dict], None] | None = None) -> TrackResult:
    """Track one frame per 1 / FPS seconds of video time, stopping early once time_limit_s of wall time has passed.

    `on_frame(full_resolution_bgr, seconds, tracked_frame)` is called for each tracked frame, before it is saved.

    Raises VideoUnreadable if the video can't be opened or has no frames, FormUnavailable if MediaPipe can't load.
    """
    capture, fallback_fps = _open_video(video_path)
    result = TrackResult(fps=float(config.FPS), width=0, height=0)
    started = clock()
    index, previous_time, previous_slot, previous_stamp_ms = 0, -1.0, -1, -1
    try:
        with Tracker(with_hands, video=True) as tracker:
            while capture.grab():
                seconds = _frame_time(capture, index, fallback_fps, previous_time)
                index += 1
                if seconds is None:
                    continue
                previous_time = seconds
                if _sample_slot(seconds) == previous_slot:
                    continue
                if clock() - started > time_limit_s:
                    result.warning = f"partial: first {round(seconds)} s checked"
                    logger.warning("Tracking %s hit the %s s limit after %d frames", video_path.name, time_limit_s, result.frames_total)
                    break
                ok, bgr = capture.retrieve()
                if not ok:
                    break
                previous_slot = _sample_slot(seconds)
                full_bgr, bgr = bgr, downscale(bgr)
                result.height, result.width = bgr.shape[:2]
                previous_stamp_ms = max(round(seconds * 1000), previous_stamp_ms + 1)  # MediaPipe needs strictly growing timestamps
                frame = tracker.track(bgr, previous_stamp_ms)
                result.frames.append({"t": round(seconds, 3), **frame})
                if on_frame is not None:
                    on_frame(full_bgr, result.frames[-1]["t"], frame)
    finally:
        capture.release()
    if not result.frames:
        raise VideoUnreadable(f"{video_path.name} has no readable frames")
    result.fps = _sampled_fps(result.frames)
    return result


def save_tracks(session_id: str, take_id: str, result: TrackResult) -> None:
    """Write data/sessions/{id}/{take}_tracks.json (atomically); raises storage_error if it can't."""
    target = tracks_path(session_id, take_id)
    temp = target.with_name(target.name + ".tmp")
    try:
        temp.write_text(json.dumps(result.to_file_dict(), separators=(",", ":")), encoding="utf-8")
        os.replace(temp, target)
    except OSError:
        logger.exception("Could not write tracks file at %s", target)
        temp.unlink(missing_ok=True)
        raise storage_error()


def track_take(session_id: str, take_id: str) -> TrackResult:
    """Track a video take (hands too for violin; the trumpet face inside its notes) and save its tracks file.

    The caller records result.warning in take.form. result.face is set for a trumpet take when FACE_ENABLED.
    """
    take = get_take(session_id, take_id)
    instrument = store.get(session_id).instrument
    video_path = store.session_dir(session_id) / take["file"]
    view = (take.get("form") or {}).get("view")  # known only when the take was analysed before; a first run crops as front
    reader = FaceReader(take.get("notes") or [], view) if config.FACE_ENABLED and instrument == "trumpet" else None
    with reader or nullcontext():
        result = track_video(video_path, instrument == "violin", on_frame=reader.read if reader else None)
    result.face = reader.result if reader else None
    save_tracks(session_id, take_id, result)
    logger.info("Tracked %s/%s: %d of %d frames", session_id, take_id, result.frames_tracked, result.frames_total)
    return result

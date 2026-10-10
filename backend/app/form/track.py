"""Frames and tracking: sample a take's video, track the learner in each sampled frame, save {take}_tracks.json."""
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2

from .. import store
from ..errors import storage_error
from ..takes.take_store import get_take
from . import config
from .errors import VideoUnreadable
from .tracker import Tracker, downscale

logger = logging.getLogger("app.form.track")


@dataclass
class TrackResult:
    fps: float  # sampled frames per second of video
    width: int
    height: int
    frames: list[dict] = field(default_factory=list)  # {t, pose, left_hand, right_hand}
    warning: str | None = None  # set when the time limit cut the analysis short

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
    capture = cv2.VideoCapture(str(video_path))
    native_fps = capture.get(cv2.CAP_PROP_FPS) if capture.isOpened() else 0
    if not 0 < native_fps <= config.MAX_NATIVE_FPS:
        capture.release()
        raise VideoUnreadable(f"{video_path.name} can't be opened or reports frame rate {native_fps}")
    return capture, native_fps


def track_video(video_path: Path, with_hands: bool, time_limit_s: float = config.TIME_LIMIT_S,
                clock: Callable[[], float] = time.monotonic) -> TrackResult:
    """Track every round(native_fps / FPS)-th frame of the video, stopping early once time_limit_s of wall time has passed.

    Raises VideoUnreadable if the video can't be opened or has no frames, FormUnavailable if MediaPipe can't load.
    """
    capture, native_fps = _open_video(video_path)
    step = max(1, round(native_fps / config.FPS))
    result = TrackResult(fps=native_fps / step, width=0, height=0)
    started = clock()
    index = 0
    try:
        with Tracker(with_hands, video=True) as tracker:
            while capture.grab():
                if index % step == 0:
                    if clock() - started > time_limit_s:
                        result.warning = f"partial: first {round(index / native_fps)} s checked"
                        logger.warning("Tracking %s hit the %s s limit after %d frames", video_path.name, time_limit_s, result.frames_total)
                        break
                    ok, bgr = capture.retrieve()
                    if not ok:
                        break
                    bgr = downscale(bgr)
                    result.height, result.width = bgr.shape[:2]
                    seconds = index / native_fps
                    frame = tracker.track(bgr, round(seconds * 1000))
                    result.frames.append({"t": round(seconds, 3), **frame})
                index += 1
    finally:
        capture.release()
    if not result.frames:
        raise VideoUnreadable(f"{video_path.name} has no readable frames")
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
    """Track a video take (hands too for violin) and save its tracks file; the caller records result.warning in take.form."""
    take = get_take(session_id, take_id)
    with_hands = store.get(session_id).instrument == "violin"
    result = track_video(store.session_dir(session_id) / take["file"], with_hands)
    save_tracks(session_id, take_id, result)
    logger.info("Tracked %s/%s: %d of %d frames", session_id, take_id, result.frames_tracked, result.frames_total)
    return result

"""Shared test setup for the form analysis: a short video made from the fixture photo, and takes to fetch tracks for."""
from pathlib import Path

import cv2

from app import store
from app.takes.take_store import add_take, update_take

PHOTO = Path(__file__).parent / "fixtures" / "pose_person.jpg"
VIDEO_FPS = 10


def make_photo_video(path: Path, frames: int = 12, fps: int = VIDEO_FPS) -> Path:
    """An mp4 that shows the fixture photo (a person) for `frames` frames."""
    photo = cv2.imread(str(PHOTO))
    assert photo is not None, f"could not read {PHOTO}"
    height, width = photo.shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    assert writer.isOpened(), "OpenCV could not open a video writer"
    for _ in range(frames):
        writer.write(photo)
    writer.release()
    return path


def add_form_take(instrument: str = "violin", kind: str = "video", form_status: str = "done") -> tuple[str, str]:
    """A session with one take of this kind; returns (session_id, take_id). Its file is t1.mp4 in the session folder."""
    session_id = store.create(instrument).session_id
    take = add_take(session_id, lambda take_id: {"kind": kind, "file": f"{take_id}.mp4"}, lambda take: None)
    update_take(session_id, take["take_id"], form_status=form_status)
    return session_id, take["take_id"]

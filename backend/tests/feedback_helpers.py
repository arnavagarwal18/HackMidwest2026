"""A session with one diagnosed take built from the shared diagnosis fixture, for the feedback tests."""
from app import store
from app.takes.take_store import add_take, update_take
from app.takes.validation import TakeRequest, new_take_fields


def add_diagnosed_take(fixture_data: dict, status: str = "diagnosed", **diagnosis_changes) -> tuple[str, str]:
    """Create take t1 (bars 1-4, 80 BPM) with the fixture's diagnosis and form; returns (session_id, take_id)."""
    session_id = store.create("violin").session_id
    request = TakeRequest(kind="mic", source="recorded", bar_from=1, bar_to=4, tempo_bpm=80, count_in_beats=4, downbeat_s=0.5)
    take = add_take(session_id, lambda take_id: new_take_fields(take_id, request, f"{take_id}_upload.wav"), lambda take: None)
    diagnosis = {**fixture_data["diagnosis"], **diagnosis_changes}
    update_take(session_id, take["take_id"], diagnosis=diagnosis, form=fixture_data["form"], status=status)
    return session_id, take["take_id"]

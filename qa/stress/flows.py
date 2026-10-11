"""Building blocks shared by the scenarios: make a session, give it a score, confirm it, upload things."""
import json

import fixtures
from client import StressClient

VIOLIN_BUILTIN = "ode_to_joy"
TAKE_FIELDS = {"kind": "mic", "source": "recorded", "bar_from": "1", "bar_to": "4", "tempo_bpm": "80",
               "count_in_beats": "0", "downbeat_s": "0.5"}


async def new_session(client: StressClient, instrument: str = "violin") -> str | None:
    body = await client.json("POST /sessions", "POST", "/sessions", json={"instrument": instrument})
    return body.get("session_id") if body else None


async def pick_builtin(client: StressClient, session_id: str, piece: str = VIOLIN_BUILTIN):
    return await client.call("POST /sessions/{id}/score/file (builtin)", "POST", f"/sessions/{session_id}/score/file", json={"builtin": piece})


async def confirm(client: StressClient, session_id: str):
    return await client.call("POST /sessions/{id}/score/confirm", "POST", f"/sessions/{session_id}/score/confirm")


async def confirmed_session(client: StressClient, instrument: str = "violin") -> str | None:
    """A fresh session whose built-in score is picked and confirmed (None if any step failed)."""
    session_id = await new_session(client, instrument)
    if not session_id:
        return None
    picked = await pick_builtin(client, session_id, VIOLIN_BUILTIN if instrument == "violin" else "ode_to_joy_trumpet")
    if picked is None or picked.status_code != 200:
        return None
    confirmed = await confirm(client, session_id)
    return session_id if confirmed is not None and confirmed.status_code == 200 else None


def wav_files(wav: bytes, content_type: str = "audio/wav", name: str = "take.wav", field: str = "file") -> dict:
    return {field: (name, wav, content_type)}


async def post_take(client: StressClient, session_id: str, route: str = "POST /sessions/{id}/takes", fields: dict | None = None,
                    files: dict | None = None, **kwargs):
    return await client.call(route, "POST", f"/sessions/{session_id}/takes", data=fields or TAKE_FIELDS,
                             files=files or wav_files(fixtures.sine_wav()), **kwargs)


async def calibration_files(client: StressClient) -> dict:
    """Valid calibration uploads (reference notes for violin, a click clip), built from the server's own reference list."""
    notes = json.loads((await client.call("GET /reference-notes", "GET", "/reference-notes", params={"instrument": "violin"})).text)
    files = {f"ref_{i}": (f"ref_{i}.wav", fixtures.sine_wav(note["hz"]), "audio/wav") for i, note in enumerate(notes)}
    files["click"] = ("click.wav", fixtures.sine_wav(burst_at_s=0.62, seconds=1.5), "audio/wav")
    return files


async def required_session(client: StressClient, instrument: str = "violin") -> str:
    """Like new_session, but a failure stops the scenario instead of letting 'None' leak into URLs."""
    session_id = await new_session(client, instrument)
    if session_id is None:
        raise RuntimeError("Could not create a session; see the client warnings above for why.")
    return session_id


async def required_confirmed_session(client: StressClient, instrument: str = "violin") -> str:
    session_id = await confirmed_session(client, instrument)
    if session_id is None:
        raise RuntimeError("Could not create a confirmed session; see the client warnings above for why.")
    return session_id

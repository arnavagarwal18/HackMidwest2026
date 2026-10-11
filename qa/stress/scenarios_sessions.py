"""Phase 12: session edge cases: odd ids, wrong order, double actions, and many writers on one session."""
import asyncio
import json
from collections import Counter

import fixtures
import flows
from client import StressClient
from config import SESSIONS_DIR
from probes import Prober

WRITERS = 20
UNKNOWN_ID_ROUTES = (
    ("GET", "/sessions/{id}", {}), ("POST", "/sessions/{id}/score/confirm", {}), ("GET", "/sessions/{id}/score", {}),
    ("GET", "/sessions/{id}/score/status", {}), ("POST", "/sessions/{id}/calibration/skip", {}), ("GET", "/sessions/{id}/calibration", {}),
    ("GET", "/sessions/{id}/chat", {}), ("POST", "/sessions/{id}/chat", {"json": {"message": "hi"}}),
    ("POST", "/sessions/{id}/transposition", {"json": {"semitones": 1}}), ("GET", "/sessions/{id}/takes/t1/analysis", {}),
    ("GET", "/sessions/{id}/takes/t1/media", {}), ("GET", "/sessions/{id}/takes/t1/feedback", {}),
    ("GET", "/sessions/{id}/takes/t1/tracks", {}), ("GET", "/sessions/{id}/feedback/f1/trace", {}),
    ("POST", "/sessions/{id}/score/file", {"json": {"builtin": "ode_to_joy"}}),
)
ODD_IDS = {"unknown hex": "0" * 32, "unicode": "séssion🎻", "unicode digits": "١٢٣", "encoded traversal": "..%2F..%2Fetc",
           "percent-NUL": "abc%00def", "300 chars": "a" * 300, "5000 chars": "a" * 5000, "spaces": "a%20b", "empty segment": ""}


async def _unknown_ids(client: StressClient, p: Prober) -> None:
    for case, odd_id in ODD_IDS.items():
        await p.probe(f"GET /sessions/<{case}>", "GET", f"/sessions/{odd_id}")
    for method, template, kwargs in UNKNOWN_ID_ROUTES:
        await p.probe(f"{method} {template} (unknown id)", method, template.format(id="0" * 32), **kwargs)
    for case in ("300 chars", "5000 chars"):
        await p.probe(f"POST score/confirm <{case}>", "POST", f"/sessions/{ODD_IDS[case]}/score/confirm")


async def _case_sensitivity(client: StressClient, p: Prober) -> None:
    sid = await flows.required_session(client)
    await p.probe("GET lowercase id", "GET", f"/sessions/{sid}")
    upper = sid.upper()
    await p.probe("GET UPPERCASE id", "GET", f"/sessions/{upper}")
    await p.probe("skip calibration via UPPERCASE id", "POST", f"/sessions/{upper}/calibration/skip")
    await p.probe("GET calibration via lowercase id", "GET", f"/sessions/{sid}/calibration")
    await p.probe("GET calibration via UPPERCASE id", "GET", f"/sessions/{upper}/calibration")


async def _wrong_order(client: StressClient, p: Prober) -> None:
    sid = await flows.required_session(client)
    wav = fixtures.sine_wav()
    await p.probe("confirm before any score", "POST", f"/sessions/{sid}/score/confirm")
    await p.probe("take before confirm", "POST", f"/sessions/{sid}/takes", data=flows.TAKE_FIELDS, files=flows.wav_files(wav))
    await p.probe("transposition before confirm", "POST", f"/sessions/{sid}/transposition", json={"semitones": 1})
    await p.probe("read score before any score", "GET", f"/sessions/{sid}/score")
    await p.probe("status before any score", "GET", f"/sessions/{sid}/score/status")
    await p.probe("calibration (live) with no clips", "POST", f"/sessions/{sid}/calibration", data={"click_at_s": "0.5"})
    await p.probe("chat with no takes", "POST", f"/sessions/{sid}/chat", json={"message": "hi"})
    await flows.pick_builtin(client, sid)
    await p.probe("first confirm", "POST", f"/sessions/{sid}/score/confirm")
    await p.probe("second confirm (double)", "POST", f"/sessions/{sid}/score/confirm")
    await p.probe("pick builtin after confirm", "POST", f"/sessions/{sid}/score/file", json={"builtin": "twinkle"})
    await p.probe("photo after confirm", "POST", f"/sessions/{sid}/score/photo", files={"file": ("p.jpg", b"\xff\xd8\xff" + b"0" * 20, "image/jpeg")})
    await p.probe("feedback for unknown take", "GET", f"/sessions/{sid}/takes/t1/feedback")
    await p.probe("rerun feedback for unknown take", "POST", f"/sessions/{sid}/takes/t1/feedback")
    await p.probe("trace for unknown feedback", "GET", f"/sessions/{sid}/feedback/f1/trace")
    await p.probe("bar range beyond the score", "POST", f"/sessions/{sid}/takes", data={**flows.TAKE_FIELDS, "bar_to": "9999"}, files=flows.wav_files(wav))
    await p.probe("feedback while take still processing", "POST", f"/sessions/{sid}/takes", data=flows.TAKE_FIELDS, files=flows.wav_files(wav))
    await p.probe("rerun feedback right after upload", "POST", f"/sessions/{sid}/takes/t1/feedback")


def _disk_session(sid: str) -> dict:
    return json.loads((SESSIONS_DIR / sid / "session.json").read_text(encoding="utf-8"))


async def _concurrent_writers(client: StressClient) -> dict:
    """20 clients write the same session at once; returns how the answers split and whether disk agrees with the API."""
    report: dict = {}
    sid = await flows.required_session(client)
    pick = await asyncio.gather(*(client.call("same session: builtin pick", "POST", f"/sessions/{sid}/score/file", json={"builtin": "ode_to_joy"}) for _ in range(WRITERS)))
    report["builtin pick x20"] = dict(Counter(r.status_code if r else None for r in pick))
    confirm = await asyncio.gather(*(client.call("same session: confirm", "POST", f"/sessions/{sid}/score/confirm") for _ in range(WRITERS)))
    report["confirm x20"] = dict(Counter(r.status_code if r else None for r in confirm))
    skip = await asyncio.gather(*(client.call("same session: calibration skip", "POST", f"/sessions/{sid}/calibration/skip") for _ in range(WRITERS)))
    report["calibration skip x20"] = dict(Counter(r.status_code if r else None for r in skip))
    wav = fixtures.sine_wav()
    takes = await asyncio.gather(*(client.call("same session: take upload", "POST", f"/sessions/{sid}/takes", data=flows.TAKE_FIELDS, files=flows.wav_files(wav)) for _ in range(WRITERS)))
    report["take upload x20"] = dict(Counter(r.status_code if r else None for r in takes))
    ids = [r.json().get("take_id") for r in takes if r is not None and r.status_code == 202]
    report["take ids unique"] = f"{len(set(ids))} unique of {len(ids)} accepted"
    chats = await asyncio.gather(*(client.call("same session: chat", "POST", f"/sessions/{sid}/chat", json={"message": f"q{i}"}) for i in range(WRITERS)))
    report["chat x20"] = dict(Counter(r.status_code if r else None for r in chats))
    transpose = await asyncio.gather(*(client.call("same session: transposition", "POST", f"/sessions/{sid}/transposition", json={"semitones": i % 5}) for i in range(WRITERS)))
    report["transposition x20"] = dict(Counter(r.status_code if r else None for r in transpose))
    await asyncio.sleep(20)  # let the background take pipelines and reruns finish
    api = (await client.json("GET same session after writers", "GET", f"/sessions/{sid}")) or {}
    try:
        disk = _disk_session(sid)
    except (OSError, ValueError) as exc:
        report["disk check"] = f"session.json unreadable: {exc}"
        return report
    statuses = Counter(take.get("status") for take in disk["takes"].values())
    report["API vs disk take count"] = f"api {len(api.get('take_ids', []))}, disk {len(disk['takes'])}"
    report["take statuses on disk"] = dict(statuses)
    report["chat turns stored"] = len((await client.json("GET same session chat", "GET", f"/sessions/{sid}/chat") or {}).get("turns", []))
    return report


async def run_sessions(client: StressClient) -> dict:
    results: list[dict] = []
    after_5xx = [0, 0]
    for group, cases in (("unknown/odd ids", _unknown_ids), ("id case sensitivity", _case_sensitivity), ("out of order / double actions", _wrong_order)):
        prober = Prober(client, group)
        await cases(client, prober)
        results.extend(prober.as_dicts())
        after_5xx[0] += prober.after_5xx_checks
        after_5xx[1] += prober.after_5xx_dropped
    return {"probes": results, "after_5xx_connection_checks": {"sent": after_5xx[0], "dropped": after_5xx[1]}, "concurrent_writers": await _concurrent_writers(client)}

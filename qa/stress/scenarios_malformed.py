"""Phase 11: malformed and hostile inputs. Anything other than a clean 4xx is worth a look; a 5xx is a bug."""
import fixtures
import flows
from client import StressClient
from probes import Prober

JSON_HEADERS = {"content-type": "application/json"}
HUGE_TEXT = "x" * (5 * 1024 * 1024)
LONG_ID = "a" * 300


async def _take_cases(client: StressClient, p: Prober) -> None:
    sid = await flows.required_confirmed_session(client)
    wav, webm = fixtures.sine_wav(), fixtures.wav_to_webm(fixtures.sine_wav())
    base = f"/sessions/{sid}/takes"
    await p.probe("wrong content-type text/plain", "POST", base, data=flows.TAKE_FIELDS, files=flows.wav_files(wav, "text/plain"))
    await p.probe("content-type missing/odd", "POST", base, data=flows.TAKE_FIELDS, files=flows.wav_files(wav, "audio/wav; codecs=\"x\"; =="))
    await p.probe("truncated webm (1000 bytes)", "POST", base, data=flows.TAKE_FIELDS, files=flows.wav_files(webm[:1000], "audio/webm", "t.webm"))
    await p.probe("truncated wav (header + half)", "POST", base, data=flows.TAKE_FIELDS, files=flows.wav_files(wav[:len(wav) // 2]))
    await p.probe("zero-byte wav", "POST", base, data=flows.TAKE_FIELDS, files=flows.wav_files(b""))
    await p.probe("no file field", "POST", base, data=flows.TAKE_FIELDS)
    await p.probe("filename path traversal", "POST", base, data=flows.TAKE_FIELDS, files=flows.wav_files(wav, name="../../../../tmp/evil.wav"))
    await p.probe("filename unicode + NUL", "POST", base, data=flows.TAKE_FIELDS, files=flows.wav_files(wav, name="音楽\u0000🎻.wav"))
    await p.probe("mp4 type but wav bytes", "POST", base, data=flows.TAKE_FIELDS, files=flows.wav_files(wav, "video/mp4", "t.mp4"))
    for field, value in (("bar_from", "abc"), ("bar_from", "99999999999999999999999999"), ("bar_to", "-1"), ("tempo_bpm", "nan"),
                         ("tempo_bpm", "1e999"), ("downbeat_s", "inf"), ("count_in_beats", "2.5"), ("kind", "x" * 100000),
                         ("bar_from", "١٢"), ("tempo_bpm", HUGE_TEXT)):
        await p.probe(f"field {field}={value[:12]!r}", "POST", base, data={**flows.TAKE_FIELDS, field: value}, files=flows.wav_files(wav))
    await p.probe("unknown take media", "GET", f"{base}/t999/media")
    await p.probe("take id traversal media", "GET", f"{base}/..%2F..%2Fsession.json/media")


async def _score_cases(client: StressClient, p: Prober) -> None:
    sid = await flows.required_session(client)
    path = f"/sessions/{sid}/score/file"
    xml = fixtures.SCORE_PATH.read_bytes()
    await p.probe("wrong extension .exe", "POST", path, files={"file": ("x.exe", xml, "application/octet-stream")})
    await p.probe("zero-byte .musicxml", "POST", path, files={"file": ("x.musicxml", b"", "application/xml")})
    await p.probe("truncated musicxml", "POST", path, files={"file": ("x.musicxml", xml[:len(xml) // 2], "application/xml")})
    await p.probe("not xml", "POST", path, files={"file": ("x.xml", b"\x00\x01binary", "application/xml")})
    await p.probe("entity expansion XML", "POST", path, files={"file": ("x.xml", _entity_bomb(), "application/xml")})
    await p.probe("filename path traversal", "POST", path, files={"file": ("../../evil.musicxml", xml, "application/xml")})
    await p.probe("filename unicode", "POST", path, files={"file": ("楽譜🎻.musicxml", xml, "application/xml")})
    await p.probe("no file field", "POST", path, files={"other": ("x.musicxml", xml, "application/xml")})
    await p.probe("multipart without boundary", "POST", path, content=b"abc", headers={"content-type": "multipart/form-data"})
    for case, body in (("bad JSON", b"{"), ("JSON list", b"[1]"), ("builtin number", b'{"builtin": 5}'), ("builtin null", b'{"builtin": null}'),
                       ("builtin traversal", b'{"builtin": "../../../etc/passwd"}'), ("builtin unknown", b'{"builtin": "nope"}'),
                       ("builtin 5 MB string", b'{"builtin": "' + HUGE_TEXT.encode() + b'"}'), ("empty body", b""),
                       ("invalid UTF-8", b'{"builtin": "\xff\xfe"}'), ("deeply nested", b"[" * 100000)):
        await p.probe(case, "POST", path, content=body, headers=JSON_HEADERS)


def _entity_bomb() -> bytes:
    """Nested-entity XML that expands about 10^4 times, to see that parsing stays bounded."""
    entities = ['<!ENTITY a "lol">'] + [f'<!ENTITY {child} "{("&" + parent + ";") * 10}">' for parent, child in zip("abcd", "bcde")]
    return f"<?xml version='1.0'?><!DOCTYPE s [{''.join(entities)}]><score-partwise>&e;</score-partwise>".encode()


async def _photo_cases(client: StressClient, p: Prober) -> None:
    path = f"/sessions/{await flows.required_session(client)}/score/photo"
    photo = fixtures.PHOTO_PATH.read_bytes()
    for case, content in (("zero bytes", b""), ("text file", b"hello"), ("GIF", b"GIF89a" + b"\x00" * 50), ("PDF", b"%PDF-1.4 x"),
                          ("RIFF but not WEBP", b"RIFF\x00\x00\x00\x00WAVEfmt "), ("1-byte JPEG magic only", b"\xff\xd8\xff")):
        await p.probe(case, "POST", path, files={"file": ("p.jpg", content, "image/jpeg")})
    await p.probe("no file field", "POST", path, data={"x": "y"})
    sid = await flows.required_session(client)
    await p.probe("truncated real JPEG", "POST", f"/sessions/{sid}/score/photo", files={"file": ("p.jpg", photo[:len(photo) // 3], "image/jpeg")})
    await p.probe("filename traversal (real photo)", "POST", f"/sessions/{await flows.required_session(client)}/score/photo",
                  files={"file": ("../../evil.jpg", photo, "image/jpeg")})


async def _session_and_json_cases(client: StressClient, p: Prober) -> None:
    for case, kwargs in (("bad JSON", {"content": b"{", "headers": JSON_HEADERS}), ("empty body", {}), ("instrument viola", {"json": {"instrument": "viola"}}),
                         ("instrument 5 MB", {"json": {"instrument": HUGE_TEXT}}), ("instrument number", {"json": {"instrument": 5}}),
                         ("form-encoded body", {"data": {"instrument": "violin"}}), ("extra fields", {"json": {"instrument": "violin", "x": [1] * 100000}}),
                         ("JSON NaN", {"content": b'{"instrument": NaN}', "headers": JSON_HEADERS}), ("deeply nested", {"content": b"[" * 100000, "headers": JSON_HEADERS})):
        await p.probe(f"POST /sessions {case}", "POST", "/sessions", **kwargs)
    sid = await flows.required_confirmed_session(client)
    for case, body in (("semitones string", {"semitones": "2"}), ("semitones float", {"semitones": 1.5}), ("semitones 99", {"semitones": 99}),
                       ("semitones bool", {"semitones": True}), ("no body", None), ("semitones 10**30", None)):
        kwargs = {"content": b'{"semitones": ' + b"9" * 30 + b"}", "headers": JSON_HEADERS} if case.endswith("10**30") else {"json": body}
        await p.probe(f"transposition {case}", "POST", f"/sessions/{sid}/transposition", **kwargs)
    for case, body in (("empty message", {"message": ""}), ("spaces only", {"message": "   "}), ("1001 chars", {"message": "a" * 1001}),
                       ("1 MB message", {"message": "a" * 1024 * 1024}), ("message number", {"message": 5}), ("unknown take_id", {"message": "hi", "take_id": "t99"}),
                       ("huge take_id", {"message": "hi", "take_id": "t" * 100000}), ("NUL + emoji", {"message": "hi\u0000🎻"}), ("message null", {"message": None})):
        await p.probe(f"chat {case}", "POST", f"/sessions/{sid}/chat", json=body)


async def _calibration_cases(client: StressClient, p: Prober) -> None:
    sid = await flows.required_session(client)
    path = f"/sessions/{sid}/calibration"
    files = await flows.calibration_files(client)
    await p.probe("no files", "POST", path, data={"click_at_s": "0.5"})
    for value in ("nan", "inf", "-1", "abc", "1e999", ""):
        await p.probe(f"click_at_s={value!r}", "POST", path, data={"click_at_s": value}, files=files)
    broken = {**files, "ref_0": ("r.wav", files["ref_0"][1][:1000], "audio/wav")}
    await p.probe("truncated ref_0 wav", "POST", path, data={"click_at_s": "0.5"}, files=broken)
    await p.probe("zero-byte ref_1", "POST", path, data={"click_at_s": "0.5"}, files={**files, "ref_1": ("r.wav", b"", "audio/wav")})
    await p.probe("ref_2 text/plain", "POST", path, data={"click_at_s": "0.5"}, files={**files, "ref_2": ("r.txt", b"hi", "text/plain")})
    await p.probe("ref_0 is 30 s long", "POST", path, data={"click_at_s": "0.5"}, files={**files, "ref_0": ("r.wav", fixtures.sine_wav(seconds=30), "audio/wav")})
    await p.probe("click is zero-byte", "POST", path, data={"click_at_s": "0.5"}, files={**files, "click": ("c.wav", b"", "audio/wav")})
    await p.probe("click_at_s beyond clip", "POST", path, data={"click_at_s": "9999"}, files=files)


async def _camera_cases(client: StressClient, p: Prober) -> None:
    path = f"/sessions/{await flows.required_session(client)}/camera-check"
    photo = fixtures.PHOTO_PATH.read_bytes()
    for case, content in (("zero bytes", b""), ("text", b"hello"), ("truncated JPEG", photo[:len(photo) // 3]), ("JPEG magic only", b"\xff\xd8\xff\xe0")):
        await p.probe(case, "POST", path, files={"file": ("f.jpg", content, "image/jpeg")})
    await p.probe("real photo (baseline)", "POST", path, files={"file": ("f.jpg", photo, "image/jpeg")})


async def run_malformed(client: StressClient) -> dict:
    results: list[dict] = []
    after_5xx = [0, 0]
    for group, cases in (("takes", _take_cases), ("score file", _score_cases), ("photo", _photo_cases), ("sessions/json/chat", _session_and_json_cases),
                         ("calibration", _calibration_cases), ("camera-check", _camera_cases)):
        prober = Prober(client, group)
        await cases(client, prober)
        results.extend(prober.as_dicts())
        after_5xx[0] += prober.after_5xx_checks
        after_5xx[1] += prober.after_5xx_dropped
    return {"probes": results, "after_5xx_connection_checks": {"sent": after_5xx[0], "dropped": after_5xx[1]}}

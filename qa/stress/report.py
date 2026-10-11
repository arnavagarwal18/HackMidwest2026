"""Turns out/results.json into RESULTS.md: the hand-written findings.md first, then every number as a table.

Usage: python report.py [results.json ...]  (several files are merged: later files add or replace phases/sections)
"""
import json
import logging
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
logger = logging.getLogger("stress.report")
ERROR_CODE = re.compile(r'"code":"([^"]+)"')


def table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def statuses_text(statuses: dict) -> str:
    return ", ".join(f"{code}×{count}" for code, count in statuses.items())


def phase_tables(phases: dict) -> str:
    out = []
    for name, phase in phases.items():
        if phase.get("crashed"):
            out.append(f"### {name}\n\nPHASE CRASHED (see run log)\n")
            continue
        rows = [[f"`{route}`", s["requests"], s["p50_ms"], s["p95_ms"], s["max_ms"], statuses_text(s["statuses"]), s["throughput_rps"]]
                for route, s in phase["routes"].items()]
        out.append(f"### {name} (wall {phase['wall_s']} s)\n\n" + table(["route", "n", "p50 ms", "p95 ms", "max ms", "status counts", "req/s (phase)"], rows) + "\n")
    return "\n".join(out)


def probe_table(probes: list[dict]) -> str:
    rows = []
    for probe in probes:
        match = ERROR_CODE.search(probe["body"])
        outcome = match.group(1) if match else (probe["body"][:40] if probe["status"] != 200 or "profile" not in probe["body"] else "ok")
        rows.append([probe["group"], probe["case"].replace("|", "\\|"), probe["status"], outcome.replace("|", "\\|")])
    return table(["group", "case", "status", "error code / body start"], rows)


def memory_tables(memory: dict, leak: dict | None) -> str:
    summary = table(["start MB", "peak MB", "end MB", "samples (every 2 s)", "peak child-process MB (ffmpeg/homr)", "process died"],
                    [[memory["start_mb"], memory["peak_mb"], memory["end_mb"], memory["samples"], memory["peak_children_mb"], memory["process_gone"]]])
    by_phase = table(["phase", "peak RSS MB"], [[phase, mb] for phase, mb in memory["peak_by_phase_mb"].items()])
    text = f"{summary}\n\n{by_phase}"
    if leak:
        readings = leak["rss_mb_before_then_after_each_round"]
        text += (f"\n\n### Leak check: {leak['sessions_per_round']} new sessions per round, 6 s idle, then RSS\n\n"
                 + table(["reading", "RSS MB"], [["before round 1", readings[0]]] + [[f"after round {i}", mb] for i, mb in enumerate(readings[1:], 1)]))
    return text


def merged(paths: list[Path]) -> dict:
    result: dict = {"phases": {}}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        result["phases"].update(data.pop("phases", {}))
        result.update(data)
    return result


def build(results: dict) -> str:
    findings = (HERE / "findings.md").read_text(encoding="utf-8")
    sections = [findings, "## Tables\n", "## Per-route load and large-input numbers\n", phase_tables(results["phases"])]
    sections += ["## Memory of the server process\n", memory_tables(results["memory"], results.get("leak_check"))]
    if "malformed" in results:
        sections += ["## Malformed and hostile inputs\n", f"Throwaway request right after a 5xx: {results['malformed']['after_5xx_connection_checks']}\n", probe_table(results["malformed"]["probes"])]
    if "sessions" in results:
        sessions = results["sessions"]
        writers = table(["same-session write (20 at once)", "result"], [[name, json.dumps(value)] for name, value in sessions["concurrent_writers"].items()])
        sections += ["## Session edge cases\n", f"Throwaway request right after a 5xx: {sessions['after_5xx_connection_checks']}\n", probe_table(sessions["probes"]), "\n### Concurrent writers on one session\n", writers]
    sections.append(f"\nDisk used by session folders: after load {results.get('disk_after_load_mb')} MB, after large uploads {results.get('disk_after_large_mb')} MB (deleted at the end of the run).")
    return "\n\n".join(sections) + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    paths = [Path(arg) for arg in sys.argv[1:]] or [HERE / "out" / "results.json"]
    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise SystemExit(f"Missing results file(s): {missing}. Run run_stress.py first.")
    (HERE / "RESULTS.md").write_text(build(merged(paths)), encoding="utf-8")
    logger.info("Wrote %s", HERE / "RESULTS.md")

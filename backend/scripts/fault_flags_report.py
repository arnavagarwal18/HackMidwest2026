"""The per-video match table for testdata/RESULTS_form_runs.md, from fault_flags.py's CSV and the answer keys.

Usage (from the repo root): backend/.venv/Scripts/python backend/scripts/fault_flags_report.py > table.md

Keys are testdata/youtube/fault_keys.csv: the faults named in the fault lines of fault_candidates_reviewed.csv (all treated as keys, per Xavier), one row per
fault (rule, start-end s, slack). A flag of the same rule that comes within slack_s of a key's times finds that key; a key with no such
flag is missed (or "not run" when its rule was skipped, needs the face reading, which this run does not make, or lies past the analysed part); a flag that finds no
key is extra. Prints one row per video, then found / missed / extra / not run per rule.
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

YOUTUBE_DIR = Path(__file__).parents[2] / "testdata" / "youtube"
FLAGS_CSV = YOUTUBE_DIR / "fault_flags.csv"
MANIFEST_CSV = YOUTUBE_DIR / "fault_manifest.csv"
KEYS_CSV = YOUTUBE_DIR / "fault_keys.csv"
NOT_VISIBLE = "not_visible"
FACE_RULES = {"trumpet_cheeks_puffed", "trumpet_smile_embouchure"}  # judged from the face reading, which this run does not make
OUTCOMES = ("found", "missed", "extra", "not run")


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"{path} is missing; run fault_flags.py (after fetch_youtube.py --list testdata/youtube/fault_candidates.csv)")
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def skipped_rules(cell: str) -> dict[str, str]:
    """{rule: reason} from a 'rule:reason; rule:reason' cell."""
    return dict(part.split(":") for part in cell.split("; ") if part)


def finds(flag: dict, key: dict) -> bool:
    slack = float(key["slack_s"])
    return (flag["rule"] == key["rule"] and float(flag["start_s"]) <= float(key["end_s"]) + slack
            and float(flag["end_s"]) >= float(key["start_s"]) - slack)


def compare(flags: list[dict], keys: list[dict], skipped: dict[str, str], analysed_s: float = float("inf")) -> list[tuple[str, dict]]:
    """[(outcome, flag or key row)] for one video: each key found / missed / not run, each flag that found no key extra.

    A key whose rule was skipped, needs the face reading, or starts after the analysed part of the video is "not run".
    """
    outcomes = []
    for key in keys:
        if key["rule"] in FACE_RULES or key["rule"] in skipped or float(key["start_s"]) > analysed_s:
            outcomes.append(("not run", key))
        else:
            outcomes.append(("found" if any(finds(f, key) for f in flags) else "missed", key))
    outcomes += [("extra", f) for f in flags if not any(finds(f, k) for k in keys)]
    return outcomes


def span(row: dict) -> str:
    return f"`{row['rule']}` {row['start_s']}-{row['end_s']} s"


def video_row(video: dict, rows: list[dict], outcomes: list[tuple[str, dict]]) -> str:
    first = rows[0]
    title = video["title"].replace("|", "/")
    if first["status"] != "ok":
        return f"| `{video['id']}` {title} | {video['duration_s']} | - | {first['status']} | - | - |"
    flags = "<br>".join(f"{span(r)} ({r['severity']})" for r in rows if r["rule"]) or "none"
    not_visible = ", ".join(f"`{r}`" for r, why in skipped_rules(first["rules_skipped"]).items() if why == NOT_VISIBLE) or "-"
    by_outcome = {name: "<br>".join(span(r) for o, r in outcomes if o == name) for name in OUTCOMES}
    result = "<br>".join(f"{name}: {text}" for name, text in by_outcome.items() if text) or "no key, no flag"
    return (f"| `{video['id']}` {title} | {video['duration_s']} (analysed {first['analysed_s']}) | {first['view']} | {flags} | "
            f"{not_visible} | {result} |")


def main() -> int:
    by_video, keys_by_video, totals = defaultdict(list), defaultdict(list), defaultdict(lambda: dict.fromkeys(OUTCOMES, 0))
    for row in read_csv(FLAGS_CSV):
        by_video[row["id"]].append(row)
    for key in read_csv(KEYS_CSV):
        keys_by_video[key["id"]].append(key)
    print("| Video | Length s | View | Flags (rule start-end, severity) | Rules skipped as not_visible | Against the answer keys |")
    print("|---|---|---|---|---|---|")
    for video in read_csv(MANIFEST_CSV):
        rows = by_video.get(video["id"])
        if not rows:
            continue
        flags = [r for r in rows if r["rule"]]
        outcomes = compare(flags, keys_by_video.get(video["id"], []), skipped_rules(rows[0]["rules_skipped"]),
                           float(rows[0]["analysed_s"] or 0))
        for outcome, row in outcomes:
            totals[row["rule"]][outcome] += 1
        print(video_row(video, rows, outcomes))
    print("\n| Rule | Found | Missed | Extra | Not run |\n|---|---|---|---|---|")
    for rule, counts in sorted(totals.items()):
        print(f"| `{rule}` | " + " | ".join(str(counts[name]) for name in OUTCOMES) + " |")
    print("| **All** | " + " | ".join(f"**{sum(c[name] for c in totals.values())}**" for name in OUTCOMES) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())

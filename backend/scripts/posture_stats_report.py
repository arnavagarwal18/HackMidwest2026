"""The "Good-posture statistics (YouTube set)" section of testdata/RESULTS_form_runs.md, built from posture_stats' per-video stats."""
import logging
import re
from collections import defaultdict
from pathlib import Path
from statistics import median

from posture_stats_measures import BELL_PROXY, PERCENTILES, percentiles

logger = logging.getLogger("posture_stats")

HEADING = "## Good-posture statistics (YouTube set)"
MEASURE_ORDER = ["head_pitch", "head_drop", "neck_ratio", "neck_side", "torso_lean", "side_torso_lean",
                 "elbow_gap_left", "elbow_gap_right", BELL_PROXY]
BELL_DEFINITION = (
    "`bell_proxy` (mouth = midpoint of pose landmarks 9 and 10, hands = midpoint of the wrists 15 and 16): "
    "**side view** = degrees above horizontal of the line from the mouth to the wrist midpoint (positive = wrists higher than the mouth), "
    "sign-corrected for the facing direction (nose vs the near ear); **front view** = (wrist-midpoint y - mouth y) / shoulder width "
    "(positive = wrists *below* the mouth, so the sign is opposite to the side view). Image-space proxies, not true bell angles.")


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _pooled_table(views_stats: list) -> list[str]:
    per_measure = defaultdict(list)  # measure -> per-video value lists
    for stats in views_stats:
        for name, values in stats.values.items():
            per_measure[name].append(values)
    header = ["| Measure | Videos | Frames | " + " | ".join(f"p{p}" for p in PERCENTILES) + " | median of per-video p1 | median of per-video p99 |",
              "|---|---|---|" + "---|" * (len(PERCENTILES) + 2)]
    rows = []
    for name in sorted(per_measure, key=lambda m: MEASURE_ORDER.index(m) if m in MEASURE_ORDER else len(MEASURE_ORDER)):
        lists = per_measure[name]
        pooled = percentiles([v for values in lists for v in values])
        per_video = [percentiles(values) for values in lists]
        cells = [name, str(len(lists)), str(sum(len(v) for v in lists)), *(_fmt(pooled[p]) for p in PERCENTILES),
                 _fmt(median(pv[1] for pv in per_video)), _fmt(median(pv[99] for pv in per_video))]
        rows.append("| " + " | ".join(cells) + " |")
    return header + rows


def build_section(all_stats: list, fps: float, cap_s: float) -> str:
    used = [s for s in all_stats if not s.skip_reason]
    skipped = [s for s in all_stats if s.skip_reason]
    by_view = {view: [s for s in used if s.view == view] for view in ("front", "side")}
    lines = [HEADING, "",
             f"Run: `backend/.venv/bin/python backend/scripts/posture_stats.py` (per-video percentiles in `testdata/youtube/posture_stats.csv`). "
             f"Each video's first {cap_s:g} s sampled at {fps:g} fps (app.form.track.track_video), pose tracked with the app's tracker, "
             "view detected per video with app.form.view (one view per video), absolute (not baseline-relative) measure values on every tracked frame.", "",
             f"Videos in the manifest: {len(all_stats)}; used: {len(used)} ({len(by_view['front'])} front, {len(by_view['side'])} side); "
             f"skipped: {len(skipped)}.", "", BELL_DEFINITION, "",
             "Front measures (head_drop, neck_ratio, torso_lean, elbow gaps) are also taken in side videos but are scaled by the tiny "
             "side-on shoulder width there, so for the side view use head_pitch, neck_side and side_torso_lean. "
             "Elbow gap = horizontal elbow-to-hip distance / shoulder width, as `trumpet_elbows_pinned` takes it.", ""]
    for view, view_stats in by_view.items():
        lines += [f"### {view.capitalize()} view: pooled over {len(view_stats)} videos", ""]
        lines += _pooled_table(view_stats) if view_stats else ["No videos used in this view."]
        lines.append("")
    lines += ["### Skipped videos", "", "| Video id | Reason |", "|---|---|"]
    lines += [f"| {s.video_id} | {s.skip_reason} |" for s in skipped] or ["| none | |"]
    return "\n".join(lines) + "\n"


def write_results_section(results_md: Path, all_stats: list, fps: float, cap_s: float) -> None:
    """Put the section into results_md, replacing an earlier one, else appending it."""
    section = build_section(all_stats, fps, cap_s)
    text = results_md.read_text(encoding="utf-8") if results_md.exists() else ""
    pattern = re.compile(rf"^{re.escape(HEADING)}\n.*?(?=^## |\Z)", re.S | re.M)
    new_text = pattern.sub(lambda _: section + "\n", text, count=1) if pattern.search(text) else text.rstrip("\n") + "\n\n" + section
    results_md.write_text(new_text, encoding="utf-8")
    logger.info("results section written to %s", results_md)

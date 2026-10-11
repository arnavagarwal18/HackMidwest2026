import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import fault_flags  # noqa: E402
import fault_flags_report as report  # noqa: E402


def flag(rule: str, start: float, end: float) -> dict:
    return {"rule": rule, "start_s": str(start), "end_s": str(end)}


def key(rule: str, start: float, end: float, slack: float = 2) -> dict:
    return {"rule": rule, "start_s": str(start), "end_s": str(end), "slack_s": str(slack)}


def outcome_names(outcomes) -> list[str]:
    return [name for name, _ in outcomes]


def test_a_flag_of_the_keys_rule_within_slack_finds_it():
    assert outcome_names(report.compare([flag("slouching", 64.5, 70)], [key("slouching", 53, 64)], {})) == ["found"]


def test_a_flag_outside_the_slack_leaves_the_key_missed_and_is_extra():
    outcomes = report.compare([flag("slouching", 70, 75)], [key("slouching", 53, 64)], {})
    assert outcome_names(outcomes) == ["missed", "extra"]


def test_a_flag_of_another_rule_does_not_find_the_key():
    outcomes = report.compare([flag("trumpet_head_down", 53, 64)], [key("slouching", 53, 64)], {})
    assert outcome_names(outcomes) == ["missed", "extra"]


def test_a_key_whose_rule_was_skipped_or_needs_the_face_is_not_run_rather_than_missed():
    keys = [key("trumpet_bell_angle", 1, 2), key("trumpet_cheeks_puffed", 1, 2)]
    assert outcome_names(report.compare([], keys, {"trumpet_bell_angle": "not_visible"})) == ["not run", "not run"]


def test_every_flag_on_a_video_without_keys_is_extra():
    assert outcome_names(report.compare([flag("slouching", 1, 2), flag("trumpet_head_down", 3, 4)], [], {})) == ["extra", "extra"]


def test_skipped_rules_cell_is_read_back():
    assert report.skipped_rules("a:not_visible; b:not_for_view") == {"a": "not_visible", "b": "not_for_view"}
    assert report.skipped_rules("") == {}


def test_a_failed_download_gets_one_row_with_its_reason_and_no_flag_columns():
    result = fault_flags.VideoFlags("abc", status="download failed: not available", video_s="")
    (row,) = fault_flags.csv_rows(result)
    assert row["status"] == "download failed: not available"
    assert row.get("rule") is None


def test_a_missing_input_file_is_an_actionable_error(tmp_path):
    with pytest.raises(SystemExit, match="fault_flags.py"):
        report.read_csv(tmp_path / "nope.csv")


def test_a_key_after_the_analysed_part_of_the_video_is_not_run():
    outcomes = report.compare([], [key("slouching", 400, 410)], {}, analysed_s=290)
    assert outcome_names(outcomes) == ["not run"]

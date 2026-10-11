import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import batch_run  # noqa: E402

FAKE_CHILD = """\
import os, sys, time
video, out_dir = sys.argv[1], sys.argv[2]
stem = os.path.splitext(os.path.basename(video))[0]
with open(os.path.join(out_dir, stem + ".pid"), "a") as f:
    f.write(str(os.getpid()) + "\\n")
print("child saw", video)
if "slow" in stem:
    time.sleep(30)
if "bad" in stem:
    sys.exit(3)
"""


@pytest.fixture
def batch(tmp_path):
    child = tmp_path / "child.py"
    child.write_text(FAKE_CHILD)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    state = tmp_path / "state.jsonl"

    class Batch:
        pass

    b = Batch()
    b.tmp_path, b.out_dir, b.state = tmp_path, out_dir, state
    b.template = [sys.executable, str(child), "{video}", str(out_dir)]

    def write_inputs(*names):
        listing = tmp_path / "videos.txt"
        listing.write_text("\n".join(str(tmp_path / n) for n in names) + "\n")
        return listing

    def run(inputs, *options, template=None):
        argv = ["--inputs", str(inputs), "--state", str(state), *options, "--", *(template or b.template)]
        return batch_run.main(argv)

    def records():
        return [json.loads(line) for line in state.read_text().splitlines()]

    def pids(stem):
        return (out_dir / f"{stem}.pid").read_text().split()

    b.write_inputs, b.run, b.records, b.pids = write_inputs, run, records, pids
    return b


def test_each_video_runs_in_its_own_process_one_after_another(batch, capsys):
    inputs = batch.write_inputs("a.mp4", "b.mp4", "c.mp4")

    assert batch.run(inputs) == 0

    pids = [batch.pids(stem)[0] for stem in ("a", "b", "c")]
    assert len(set(pids)) == 3
    assert str(os.getpid()) not in pids
    assert [r["status"] for r in batch.records()] == ["ok"] * 3
    assert {"video", "status", "returncode", "seconds", "ts"} <= set(batch.records()[0])
    assert capsys.readouterr().out.count("\n") == 3


def test_child_output_goes_to_a_log_file_not_the_console(batch, capsys):
    batch.run(batch.write_inputs("a.mp4"))

    assert "child saw" not in capsys.readouterr().out
    logs = list((batch.tmp_path / "state.jsonl.logs").glob("a-*.log"))
    assert len(logs) == 1
    assert "child saw" in logs[0].read_text()


def test_log_dir_option_is_used(batch):
    log_dir = batch.tmp_path / "my_logs"

    batch.run(batch.write_inputs("a.mp4"), "--log-dir", str(log_dir))

    assert len(list(log_dir.glob("a-*.log"))) == 1


def test_resume_skips_ok_items_and_runs_the_rest(batch):
    inputs = batch.write_inputs("a.mp4", "b.mp4")
    batch_run.append_state(batch.state, {"video": str(batch.tmp_path / "a.mp4"), "status": "ok", "returncode": 0, "seconds": 1, "ts": "t"})

    assert batch.run(inputs) == 0

    assert not (batch.out_dir / "a.pid").exists()
    assert len(batch.pids("b")) == 1
    assert [r["status"] for r in batch.records()] == ["ok", "ok"]


def test_failed_item_is_recorded_and_the_batch_continues(batch):
    inputs = batch.write_inputs("bad.mp4", "good.mp4")

    assert batch.run(inputs) == 1

    first, second = batch.records()
    assert (first["status"], first["returncode"]) == ("failed", 3)
    assert second["status"] == "ok"


def test_failed_items_are_retried_on_restart_unless_told_not_to(batch):
    inputs = batch.write_inputs("bad.mp4")
    batch.run(inputs)

    batch.run(inputs, "--no-retry-failed")
    assert len(batch.pids("bad")) == 1

    assert batch.run(inputs) == 1
    assert len(batch.pids("bad")) == 2


def test_no_retry_failed_still_reports_failure_in_exit_code(batch):
    inputs = batch.write_inputs("bad.mp4")
    batch.run(inputs)

    assert batch.run(inputs, "--no-retry-failed") == 1


def test_stop_on_fail_stops_the_batch(batch):
    inputs = batch.write_inputs("bad.mp4", "good.mp4")

    assert batch.run(inputs, "--stop-on-fail") == 1

    assert not (batch.out_dir / "good.pid").exists()
    assert len(batch.records()) == 1


def test_timeout_is_recorded_and_the_child_is_killed(batch):
    inputs = batch.write_inputs("slow.mp4", "good.mp4")

    started = time.monotonic()
    assert batch.run(inputs, "--timeout", "1") == 1

    assert time.monotonic() - started < 20
    slow, good = batch.records()
    assert slow["status"] == "timeout"
    assert "timeout" in slow["error"]
    assert good["status"] == "ok"
    with pytest.raises(ProcessLookupError):
        os.kill(int(batch.pids("slow")[0]), 0)


def test_command_that_cannot_start_is_recorded_as_failed(batch, capsys):
    code = batch.run(batch.write_inputs("a.mp4"), template=["/no/such/program", "{video}"])

    assert code == 1
    record = batch.records()[0]
    assert record["status"] == "failed"
    assert "could not start" in record["error"]


def test_placeholders_are_substituted_and_other_text_is_untouched():
    command = batch_run.build_command(["run", "{video}", "out/{stem}.csv", "--max-seconds", "290", "{other}"], "/data/clip one.mp4")

    assert command == ["run", "/data/clip one.mp4", "out/clip one.csv", "--max-seconds", "290", "{other}"]


def test_dry_run_lists_commands_and_runs_nothing(batch, capsys):
    inputs = batch.write_inputs("a.mp4", "b.mp4")
    batch_run.append_state(batch.state, {"video": str(batch.tmp_path / "a.mp4"), "status": "ok", "returncode": 0, "seconds": 1, "ts": "t"})
    state_before = batch.state.read_text()

    assert batch.run(inputs, "--dry-run") == 0

    out = capsys.readouterr().out
    assert "would skip (ok)" in out
    assert f"would run: {sys.executable}" in out and str(batch.tmp_path / "b.mp4") in out
    assert list(batch.out_dir.iterdir()) == []
    assert batch.state.read_text() == state_before
    assert not (batch.tmp_path / "state.jsonl.logs").exists()


def test_record_appended_after_a_torn_line_is_not_glued_onto_it(tmp_path):
    state = tmp_path / "state.jsonl"
    state.write_text('{"video": "a.mp4", "status": "ok"}\n{"video": "b.mp')

    batch_run.append_state(state, {"video": "c.mp4", "status": "ok"})

    assert set(batch_run.load_state(state)) == {"a.mp4", "c.mp4"}
    assert state.read_text().endswith('{"video": "c.mp4", "status": "ok"}\n')


def test_append_state_adds_no_blank_line_to_a_clean_file(tmp_path):
    state = tmp_path / "state.jsonl"

    batch_run.append_state(state, {"video": "a.mp4", "status": "ok"})
    batch_run.append_state(state, {"video": "b.mp4", "status": "ok"})

    assert len(state.read_text().splitlines()) == 2


def wait_for_file(path, seconds=15):
    deadline = time.monotonic() + seconds
    while not path.exists() or not path.read_text().strip():
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.05)


@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM], ids=["ctrl-c", "sigterm"])
def test_interrupting_the_runner_stops_the_running_child(batch, sig):
    runner = subprocess.Popen(
        [sys.executable, batch_run.__file__, "--inputs", str(batch.write_inputs("slow.mp4", "good.mp4")),
         "--state", str(batch.state), "--", *batch.template],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_file(batch.out_dir / "slow.pid")
        child_pid = int(batch.pids("slow")[0])

        runner.send_signal(sig)
        assert runner.wait(timeout=15) != 0

        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
        assert not (batch.out_dir / "good.pid").exists()
        assert not batch.state.exists()
    finally:
        if runner.poll() is None:
            runner.terminate()


def test_directory_input_with_glob(batch):
    videos = batch.tmp_path / "videos"
    videos.mkdir()
    for name in ("x.mp4", "y.mp4", "notes.txt"):
        (videos / name).write_text("")

    assert batch.run(videos, "--glob", "*.mp4") == 0

    assert sorted(p.name for p in batch.out_dir.iterdir()) == ["x.pid", "y.pid"]


def test_input_list_ignores_blank_lines_comments_and_duplicates(tmp_path):
    listing = tmp_path / "videos.txt"
    listing.write_text("a.mp4\n\n# skipped.mp4\n  b.mp4  \na.mp4\n")

    assert batch_run.read_videos(str(listing), "*") == ["a.mp4", "b.mp4"]


def test_torn_state_line_is_ignored_on_resume(tmp_path, capsys):
    state = tmp_path / "state.jsonl"
    state.write_text('{"video": "a.mp4", "status": "ok"}\n{"video": "b.mp')

    assert list(batch_run.load_state(state)) == ["a.mp4"]
    assert "unreadable line 2" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--inputs", "x", "--state", "s"], "Missing command template"),
        (["--inputs", "x", "--state", "s", "--"], "empty"),
    ],
)
def test_missing_template_is_a_usage_error(argv, message, capsys):
    assert batch_run.main(argv) == batch_run.EXIT_USAGE
    assert message in capsys.readouterr().err


def test_missing_or_empty_inputs_are_usage_errors(batch, capsys):
    assert batch.run(batch.tmp_path / "nope.txt") == batch_run.EXIT_USAGE
    assert "neither a file nor a directory" in capsys.readouterr().err

    empty = batch.tmp_path / "empty.txt"
    empty.write_text("\n")
    assert batch.run(empty) == batch_run.EXIT_USAGE
    assert "No videos found" in capsys.readouterr().err

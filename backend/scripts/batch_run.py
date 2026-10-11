"""Run one script once per video, one video at a time, each in its own process.

Every video gets a fresh subprocess, so the OS frees all of its memory when it
exits and a long batch never accumulates memory between videos. Finished items
are appended to a JSONL state file, so a re-run resumes where it stopped.

Example:
    python backend/scripts/batch_run.py --inputs videos.txt --state out/state.jsonl \\
        --timeout 600 -- python backend/scripts/dump_face_readings.py {video} out/{stem}.csv --max-seconds 290

``--inputs`` is a text file with one video path per line (blank lines and lines
starting with ``#`` are ignored), or a directory together with ``--glob``.
Everything after ``--`` is the command template, passed through verbatim except
that ``{video}`` and ``{stem}`` (the file name without extension) are replaced.
"""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_TIMEOUT = "timeout"
EXIT_USAGE = 2


class UsageError(Exception):
    """A problem with the command line the user can fix and retry."""


def split_template(argv):
    """Split argv at the first ``--`` into (our options, command template)."""
    if "--" not in argv:
        raise UsageError("Missing command template: put it after '--', e.g. -- python script.py {video}")
    index = argv.index("--")
    template = argv[index + 1 :]
    if not template:
        raise UsageError("The command template after '--' is empty.")
    return argv[:index], template


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run a command once per video, each in its own process. Put the command template after '--'.",
        usage="%(prog)s --inputs FILE_OR_DIR --state STATE.jsonl [options] -- COMMAND {video} ...",
    )
    parser.add_argument("--inputs", required=True, help="text file of video paths (one per line), or a directory (use with --glob)")
    parser.add_argument("--glob", default="*", help="pattern for files when --inputs is a directory (default: *)")
    parser.add_argument("--state", required=True, help="JSONL file recording finished items; enables resume")
    parser.add_argument("--log-dir", help="directory for per-item logs (default: <state file name>.logs next to the state file)")
    parser.add_argument("--timeout", type=float, help="seconds before an item is killed and recorded as timeout (default: none)")
    parser.add_argument("--no-retry-failed", action="store_true", help="on restart, skip items that failed or timed out too")
    parser.add_argument("--stop-on-fail", action="store_true", help="stop the batch at the first failed or timed-out item")
    parser.add_argument("--dry-run", action="store_true", help="list what would run, run nothing, write nothing")
    return parser


def read_videos(inputs, pattern):
    path = Path(inputs)
    if path.is_dir():
        videos = [str(p) for p in sorted(path.glob(pattern)) if p.is_file()]
    elif path.is_file():
        lines = (line.strip() for line in path.read_text().splitlines())
        videos = [line for line in lines if line and not line.startswith("#")]
    else:
        raise UsageError(f"--inputs {inputs!r} is neither a file nor a directory.")
    videos = list(dict.fromkeys(videos))
    if not videos:
        raise UsageError(f"No videos found in {inputs!r}" + (f" matching {pattern!r}." if path.is_dir() else "."))
    return videos


def load_state(state_path):
    """Return {video: latest record}; a torn final line from a crash is ignored."""
    latest = {}
    if not state_path.exists():
        return latest
    for number, line in enumerate(state_path.read_text().splitlines(), start=1):
        try:
            record = json.loads(line)
            latest[record["video"]] = record
        except (ValueError, KeyError, TypeError):
            print(f"warning: ignoring unreadable line {number} of {state_path}", file=sys.stderr)
    return latest


def append_state(state_path, record):
    with open(state_path, "a") as handle:
        handle.write(json.dumps(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def is_done(record, retry_failed):
    if record is None:
        return False
    return record["status"] == STATUS_OK or not retry_failed


def build_command(template, video):
    stem = Path(video).stem
    return [part.replace("{video}", video).replace("{stem}", stem) for part in template]


def log_path_for(log_dir, video):
    digest = hashlib.sha1(video.encode()).hexdigest()[:8]
    return log_dir / f"{Path(video).stem}-{digest}.log"


def kill_process_tree(process):
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
    process.wait()


def run_item(command, log_path, timeout):
    """Run one command in its own process; return (status, returncode, error)."""
    error = None
    with open(log_path, "a") as log:
        log.write(f"$ {' '.join(command)}\n")
        log.flush()
        try:
            process = subprocess.Popen(
                command, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                start_new_session=(os.name == "posix"),
            )
        except OSError as exc:
            error = f"could not start command: {exc}"
            log.write(error + "\n")
            return STATUS_FAILED, None, error
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_process_tree(process)
            error = f"killed after {timeout:g}s timeout"
            log.write(error + "\n")
            return STATUS_TIMEOUT, process.returncode, error
    return (STATUS_OK if returncode == 0 else STATUS_FAILED), returncode, error


def run_batch(videos, template, args):
    state_path = Path(args.state)
    log_dir = Path(args.log_dir) if args.log_dir else state_path.with_name(state_path.name + ".logs")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(state_path)
    total = len(videos)
    for number, video in enumerate(videos, start=1):
        if is_done(state.get(video), not args.no_retry_failed):
            print(f"[{number}/{total}] skip ({state[video]['status']}) {video}")
            continue
        log_path = log_path_for(log_dir, video)
        started = time.monotonic()
        status, returncode, error = run_item(build_command(template, video), log_path, args.timeout)
        record = {
            "video": video, "status": status, "returncode": returncode,
            "seconds": round(time.monotonic() - started, 2),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        if error:
            record["error"] = error
        append_state(state_path, record)
        state[video] = record
        print(f"[{number}/{total}] {status} {video} {record['seconds']}s (log: {log_path})")
        if status != STATUS_OK and args.stop_on_fail:
            print("stopping: --stop-on-fail", file=sys.stderr)
            break
    return state


def print_dry_run(videos, template, state, retry_failed):
    for number, video in enumerate(videos, start=1):
        if is_done(state.get(video), retry_failed):
            print(f"[{number}/{len(videos)}] would skip ({state[video]['status']}) {video}")
        else:
            print(f"[{number}/{len(videos)}] would run: {' '.join(build_command(template, video))}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        own_args, template = split_template(argv)
        args = build_parser().parse_args(own_args)
        videos = read_videos(args.inputs, args.glob)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except OSError as exc:
        print(f"error: cannot read inputs: {exc}", file=sys.stderr)
        return EXIT_USAGE

    if args.dry_run:
        print_dry_run(videos, template, load_state(Path(args.state)), not args.no_retry_failed)
        return 0

    try:
        state = run_batch(videos, template, args)
    except OSError as exc:
        print(f"error: cannot write state or logs: {exc}", file=sys.stderr)
        return EXIT_USAGE
    bad = [v for v in videos if v not in state or state[v]["status"] != STATUS_OK]
    if bad:
        print(f"{len(bad)} of {len(videos)} items not ok; see {args.state}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

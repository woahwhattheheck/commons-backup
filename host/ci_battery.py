#!/usr/bin/env python3
"""Run the Commons CI battery on a cloud worker without GitHub Actions.

The default discovery is shared with tests.yml: root test_*.py, recursive
infra/test_*.py, then root test_*.js. Every selected file runs after failures.
Use --output-dir for portable JSON evidence, or --results for the existing
Actions NUL stream. No provider API, Docker daemon, or new credentials needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

# Importing the local report helper must not manufacture an ignored __pycache__
# before the checkout preflight inventories ignored working-tree inputs.
sys.dont_write_bytecode = True

try:
    from . import battery_report
except ImportError:
    import battery_report


def discover(root: Path) -> list[tuple[str, str]]:
    python = [p for p in root.glob("test_*.py") if p.is_file() and not p.is_symlink()]
    infra = root / "infra"
    if infra.is_dir() and not infra.is_symlink():
        # os.walk does not descend through directory symlinks, like find.
        for directory, _, files in os.walk(infra, followlinks=False):
            python.extend(Path(directory) / name for name in files
                          if name.startswith("test_") and name.endswith(".py")
                          and (Path(directory) / name).is_file()
                          and not (Path(directory) / name).is_symlink())
    paths = sorted((p.relative_to(root).as_posix() for p in python), key=os.fsencode)
    node = sorted((p.name for p in root.glob("test_*.js") if p.is_file()), key=os.fsencode)
    return [("python3", p) for p in paths] + [("node", p) for p in node]


def record(handle, command: str, path: str, code: str | int) -> None:
    handle.write(b"".join(os.fsencode(str(value)) + b"\0" for value in (command, path, code)))
    handle.flush()


def execute(root: Path, command: str, path: str, timeout: float | None) -> int:
    argv = [sys.executable if command == "python3" else command, "./" + path]
    try:
        process = subprocess.Popen(argv, cwd=root, start_new_session=os.name == "posix")
    except OSError:
        print("could not start test: " + json.dumps(path), file=sys.stderr, flush=True)
        return 127
    try:
        rc = process.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait()
        if isinstance(exc, KeyboardInterrupt):
            raise
        print("test timed out: " + json.dumps(path), file=sys.stderr, flush=True)
        return 124
    return min(255, 128 - rc) if rc < 0 else min(255, rc)


def tracked_regular_files(root: Path, sha: str, paths: list[str]) -> set[str]:
    """Return selected paths that are tracked regular files at sha."""
    if not paths:
        return set()
    raw = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-z", "--full-tree", sha, "--", *paths],
        check=True, capture_output=True,
    ).stdout
    tracked = set()
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        mode, kind, _blob = metadata.split()
        if kind == b"blob" and mode in (b"100644", b"100755"):
            tracked.add(path.decode("utf-8", "surrogateescape"))
    return tracked


def ignored_worktree_paths(root: Path) -> list[str]:
    """Return ignored files that could supply uncommitted runtime bytes."""
    raw = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--others", "--ignored",
         "--exclude-standard", "-z"],
        check=True, capture_output=True,
    ).stdout
    return [path.decode("utf-8", "surrogateescape")
            for path in raw.split(b"\0") if path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, help="directory for results.nul and report.json")
    parser.add_argument("--results", type=Path, help="write the existing Actions-compatible raw stream")
    parser.add_argument("--report", type=Path, help="also write checkout-linked JSON")
    parser.add_argument("--test", action="append", default=[], help="select a discovered test path; repeatable")
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0, help="zero-based shard number")
    parser.add_argument("--timeout", type=float, default=0, help="per-file seconds; 0 preserves the unbounded battery")
    parser.add_argument("--fail-fast", action="store_true", help="stop after the first failed test while preserving default exhaustive execution")
    parser.add_argument("--list", action="store_true", help="list selected commands without executing")
    args = parser.parse_args(argv)
    if args.output_dir and args.results:
        parser.error("use --output-dir or --results, not both")
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        parser.error("shard index must be between zero and shard count minus one")
    if not math.isfinite(args.timeout) or args.timeout < 0:
        parser.error("timeout must be finite and nonnegative")
    root = args.root.resolve()
    discovered = discover(root)
    requested = list(dict.fromkeys(p[2:] if p.startswith("./") else p for p in args.test))
    missing = sorted(set(requested) - {path for _, path in discovered})
    if missing:
        parser.error("test paths were not discovered: " + json.dumps(missing))
    selected = [row for row in discovered if not requested or row[1] in requested]
    selected = selected[args.shard_index::args.shard_count]
    if args.list:
        print(json.dumps(selected, indent=2))
        return 0
    if args.results:
        results = args.results.resolve()
        report_path = args.report.resolve() if args.report else None
    else:
        output = (args.output_dir or Path(tempfile.mkdtemp(prefix="commons-ci-"))).resolve()
        results = output / "results.nul"
        report_path = args.report.resolve() if args.report else output / "report.json"
    if report_path == results:
        parser.error("report and results must be different files")
    # Never let an output path truncate a selected test before execution.
    inputs = {root / path for _, path in selected}
    if results in inputs or report_path in inputs:
        parser.error("output paths must differ from selected test paths")
    results.parent.mkdir(parents=True, exist_ok=True)
    outcome = "success"
    code = 0
    file_hashes = {}
    scope = {"kind": "selected" if requested else "full", "requested": requested,
             "shard_index": args.shard_index, "shard_count": args.shard_count,
             "discovered_files": len(discovered), "planned_files": len(selected),
             "fail_fast": args.fail_fast}
    if args.shard_count > 1:
        scope["kind"] = "selected-shard" if requested else "shard"
    dirty = None
    ignored_paths: list[str] = []
    preflight_error = None
    try:
        # Drop stale evidence before Git preflight so a missing checkout cannot
        # reuse a previous success. Measure dirt before creating new outputs.
        results.unlink(missing_ok=True)
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.unlink(missing_ok=True)
        sha = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"],
                             check=True, capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                                    check=True, capture_output=True).stdout)
        selected_paths = [path for _, path in selected]
        tracked = tracked_regular_files(root, sha, selected_paths)
        unbound = [path for path in selected_paths
                   if path not in tracked or (root / path).is_symlink() or not (root / path).is_file()]
        ignored_paths = ignored_worktree_paths(root)
        with results.open("wb") as handle:
            record(handle, "checkout_sha", sha, "")
            record(handle, "battery_scope", json.dumps(scope, sort_keys=True, separators=(",", ":")), "")
            if dirty:
                print("checkout is dirty; refusing source-linked passing evidence",
                      file=sys.stderr, flush=True)
                record(handle, "battery_complete", "", 0)
                outcome, code, preflight_error = "failure", 2, "dirty_worktree"
            elif unbound:
                print("selected tests are not tracked regular files at HEAD; "
                      "refusing source-linked passing evidence",
                      file=sys.stderr, flush=True)
                record(handle, "battery_complete", "", 0)
                outcome, code, preflight_error = "failure", 2, "selected_not_tracked_regular"
            elif ignored_paths:
                print("checkout contains ignored working-tree inputs; "
                      "refusing source-linked passing evidence",
                      file=sys.stderr, flush=True)
                record(handle, "battery_complete", "", 0)
                outcome, code, preflight_error = "failure", 2, "ignored_worktree_inputs"
            else:
                for command, path in selected:
                    try:
                        file_hashes[path] = hashlib.sha256((root / path).read_bytes()).hexdigest()
                    except OSError:
                        file_hashes[path] = None
                    started = time.monotonic()
                    rc = execute(root, command, path, args.timeout or None)
                    duration_ms = max(0, round((time.monotonic() - started) * 1000))
                    record(handle, command, "./" + path, rc)
                    record(handle, "timing_ms", "./" + path, duration_ms)
                    code = int(bool(code or rc))
                    print(("ok   " if rc == 0 else "FAIL ") + json.dumps(path), flush=True)
                    if rc and args.fail_fast:
                        print("fail-fast: stopping after first failed test", flush=True)
                        break
                record(handle, "battery_complete", "", code)
                outcome = "failure" if code else "success"
                if not selected:
                    print("no tests matched; no passing battery evidence", file=sys.stderr)
                    code = 1
    except KeyboardInterrupt:
        outcome, code = "cancelled", 130
    except (OSError, subprocess.CalledProcessError):
        print("battery could not read its checkout or write results", file=sys.stderr)
        outcome, code = "failure", 2
    if report_path:
        raw = results.read_bytes() if results.exists() else None
        report = battery_report.build_report(root, raw, outcome, os.environ)
        report["scope"] = scope
        report["execution"] = {"kind": "direct-process", "python_version": sys.version.split()[0],
                               "worktree_dirty_at_start": dirty,
                               "ignored_worktree_entries_at_start": len(ignored_paths),
                               "preflight_error": preflight_error,
                               "test_file_sha256": file_hashes}
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print(report["conclusion"] + ": " + str(report_path), flush=True)
        if report["conclusion"] != "PASSED" and code == 0:
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())

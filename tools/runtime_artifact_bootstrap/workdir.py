#!/usr/bin/env python3
"""Inspect explicit storage candidates or create an owned temporary workdir.

This optional operator aid does not reserve capacity, move existing files,
change environment variables, or intercept another program's execution.
"""
from __future__ import annotations

import argparse
import errno
import importlib.util
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def memory_observation():
    """Reuse the command center's visible-ancestor cgroup accounting."""
    result = {"host_available_bytes": None, "cgroup": None, "read_errors": []}
    if sys.platform != "linux":
        result["read_errors"].append("Linux memory observations unavailable on this platform")
        return result
    try:
        source = Path(__file__).resolve().parents[2] / "integrations/command_center/telemetry.py"
        spec = importlib.util.spec_from_file_location("commons_workdir_telemetry", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        limits = module._linux_process_limits()
        result["cgroup"] = {key: value for key, value in limits.items()
                            if key.startswith("memory_") or key in (
                                "scope", "cgroup_status", "cgroup_path", "cgroup_mount",
                                "controller_status", "unavailable_interfaces", "read_errors", "notes")}
    except (OSError, ImportError, AttributeError, ValueError) as exc:
        result["read_errors"].append("cgroup observation: " + str(exc))
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            name, separator, value = line.partition(":")
            if separator and name == "MemAvailable":
                amount, unit = value.split()
                if unit != "kB" or not amount.isascii() or not amount.isdecimal():
                    raise ValueError("invalid MemAvailable")
                result["host_available_bytes"] = int(amount) * 1024
                break
    except (OSError, ValueError) as exc:
        result["read_errors"].append("host memory observation: " + str(exc))
    return result


def mounts_observation():
    mounts, errors = [], []
    if sys.platform != "linux":
        return mounts, ["Linux filesystem types unavailable on this platform"]
    try:
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            before, separator, after = line.partition(" - ")
            fields, filesystem = before.split(), after.split()
            if separator and len(fields) >= 5 and filesystem:
                mount = re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), fields[4])
                mounts.append((Path(mount), fields[2], filesystem[0]))
    except OSError as exc:
        errors.append("mount observation: " + str(exc))
    return mounts, errors


def inspect_candidates(candidates, need_bytes=0, reserve_bytes=0):
    """Return observations and a preference; do not create or reserve files."""
    if need_bytes < 0 or reserve_bytes < 0:
        raise ValueError("need_bytes and reserve_bytes must be nonnegative")
    memory = memory_observation()
    mounts, mount_errors = mounts_observation()
    cgroup = memory.get("cgroup") or {}
    headroom = cgroup.get("memory_headroom_bytes")
    records, devices = [], {}
    for supplied in candidates:
        entry = {"supplied_path": str(supplied), "path": None, "device": None,
                 "filesystem": None, "memory_backed": None, "available_bytes": None,
                 "usable_bytes": None, "available_inodes": None, "fits": False,
                 "notes": [], "error": None}
        try:
            path = Path(supplied).expanduser().resolve(strict=True)
            entry["path"] = str(path)
            if not path.is_dir():
                raise ValueError("candidate is not a directory")
            stat = path.stat()
            space = os.statvfs(path)
            entry.update(device=stat.st_dev, total_bytes=space.f_blocks * space.f_frsize,
                         available_bytes=space.f_bavail * space.f_frsize,
                         available_inodes=space.f_favail)
            matches = [mount for mount in mounts if path.is_relative_to(mount[0])]
            if matches:
                mount, _, filesystem = max(matches, key=lambda item: len(item[0].parts))
                entry.update(mount=str(mount), filesystem=filesystem,
                             memory_backed=filesystem in {"tmpfs", "ramfs"})
            else:
                entry["notes"].append("Filesystem type unknown; memory-backed storage is unmeasured")
            available = entry["available_bytes"]
            if entry["memory_backed"]:
                budgets = [available]
                if memory["host_available_bytes"] is not None:
                    budgets.append(memory["host_available_bytes"])
                if headroom is not None:
                    budgets.append(headroom)
                else:
                    entry["notes"].append("No observed cgroup charge budget; visible coverage is in memory.cgroup")
                available = min(budgets)
                entry["notes"].append("Memory-backed bytes consume RAM; cgroup budget excludes possible reclaim")
            entry["usable_bytes"] = max(0, available - reserve_bytes)
            writable = os.access(path, os.W_OK | os.X_OK)
            readonly = bool(space.f_flag & getattr(os, "ST_RDONLY", 1))
            inode_fit = space.f_files == 0 or space.f_favail >= 2
            entry.update(writable=writable, readonly=readonly,
                         fits=writable and not readonly and inode_fit
                              and entry["usable_bytes"] >= need_bytes)
            if not writable or readonly:
                entry["notes"].append("Candidate is not currently writable")
            if not inode_fit:
                entry["notes"].append("Fewer than two available inodes for a directory and its first file")
            if entry["usable_bytes"] < need_bytes:
                entry["notes"].append("Observed bytes after reserve are below the requested allocation")
            aliases = devices.setdefault(str(stat.st_dev), [])
            if str(path) not in aliases:
                aliases.append(str(path))
        except (OSError, ValueError, AttributeError, RuntimeError) as exc:
            entry["error"] = str(exc)
        records.append(entry)
    eligible = sorted((entry for entry in records if entry["fits"]),
                      key=lambda entry: entry["usable_bytes"], reverse=True)
    return {
        "schema": "commons-workdir/v1",
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "need_bytes": need_bytes, "reserve_bytes": reserve_bytes,
        "selected_candidate": eligible[0]["path"] if eligible else None,
        "workdir": None, "created": False, "capacity_reserved": False,
        "distinct_filesystems": len(devices), "device_aliases": devices,
        "memory": memory, "mount_read_errors": mount_errors, "candidates": records,
        "notes": "Observations can change immediately. Filesystem aliases share capacity and are not added together. "
                 "The requested file budget excludes the workload's process memory. "
                 "This helper does not move existing outputs or change their retention.",
    }


def create_workdir(report):
    """Create one new directory; leave all pre-existing paths untouched."""
    eligible = sorted((entry for entry in report["candidates"] if entry["fits"]),
                      key=lambda entry: entry["usable_bytes"], reverse=True)
    exhausted_devices, attempted = set(), set()
    failures = []
    for entry in eligible:
        parent = entry["path"]
        if parent in attempted or entry["device"] in exhausted_devices:
            continue
        attempted.add(parent)
        directory = probe = None
        probe_created = False
        try:
            directory = Path(tempfile.mkdtemp(prefix="commons-work-", dir=parent))
            probe = directory / ".write-check"
            with probe.open("xb") as stream:
                probe_created = True
                stream.write(b"\0" * 4096)
                stream.flush()
                os.fsync(stream.fileno())
            # Read and remove only the file this call exclusively created.
            if probe.read_bytes() != b"\0" * 4096:
                raise OSError("The new work directory did not retain its initial write")
            probe.unlink()
            probe_created = False
            report.update(selected_candidate=parent, workdir=str(directory), created=True,
                          create_errors=failures)
            return report
        except OSError as exc:
            failure = {"path": parent, "error": str(exc)}
            if exc.errno == errno.ENOSPC:
                exhausted_devices.add(entry["device"])
            if directory is not None:
                try:
                    if probe_created:
                        probe.read_bytes()
                        probe.unlink()
                    directory.rmdir()  # Never recursively delete a directory.
                except OSError as cleanup_error:
                    failure.update(retained_directory=str(directory), cleanup_error=str(cleanup_error))
            failures.append(failure)
    report.update(error="No candidate could create a work directory for the requested budget. "
                        "Inspect candidates and supply another root or an updated allocation.",
                  create_errors=failures)
    return report


def nonnegative(value):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use a nonnegative whole number of bytes") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("use a nonnegative whole number of bytes")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "create"))
    parser.add_argument("--candidate", action="append", required=True,
                        help="existing candidate directory; repeat in preferred tie-break order")
    parser.add_argument("--need-bytes", type=nonnegative, default=0,
                        help="expected maximum temporary file bytes")
    parser.add_argument("--reserve-bytes", type=nonnegative, default=0,
                        help="leave this many observed bytes outside the requested budget")
    parser.add_argument("--format", choices=("json", "path"), default="json",
                        help="path prints only the created directory; JSON includes observations")
    args = parser.parse_args(argv)
    if args.format == "path" and args.action != "create":
        parser.error("--format path is for create; inspect returns JSON")
    try:
        report = inspect_candidates(args.candidate, args.need_bytes, args.reserve_bytes)
        if args.action == "create":
            create_workdir(report)
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif report["created"]:
            print(report["workdir"])
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        return 0 if args.action == "inspect" or report["created"] else 1
    except (OSError, ValueError) as exc:
        print("Workdir selection failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

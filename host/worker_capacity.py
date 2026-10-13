#!/usr/bin/env python3
"""Print a read-only snapshot of memory limits and selected filesystem capacity."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SCHEMA = "commons.worker_capacity/v1"
PROCESS_STATUS_BYTES = 65536


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _error(exc):
    return {"kind": type(exc).__name__, "errno": getattr(exc, "errno", None)}


def _nonnegative(raw):
    if not re.fullmatch(r"[0-9]+", raw):
        raise ValueError("expected a nonnegative kernel counter")
    return int(raw)


def _host_memory():
    result = {"source": "/proc/meminfo", "total_bytes": None, "available_bytes": None}
    try:
        wanted = {"MemTotal": "total_bytes", "MemAvailable": "available_bytes"}
        for line in Path(result["source"]).read_text(encoding="ascii").splitlines():
            key, _, raw = line.partition(":")
            if key in wanted:
                value, unit = raw.split()
                if unit != "kB":
                    raise ValueError("unexpected memory unit")
                result[wanted[key]] = _nonnegative(value) * 1024
        result["status"] = "ok" if all(result[key] is not None for key in wanted.values()) else "partial"
    except (OSError, UnicodeError, ValueError) as exc:
        result.update(status="unavailable", error=_error(exc))
    return result


def _unescape_mount(value):
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), value)


def _cgroup_location():
    membership = None
    for line in Path("/proc/self/cgroup").read_text(encoding="utf-8").splitlines():
        if line.startswith("0::"):
            membership = PurePosixPath(line[3:])
            break
    if membership is None:
        raise ValueError("no cgroup v2 membership")
    if not membership.is_absolute() or ".." in membership.parts:
        raise ValueError("unresolvable cgroup membership")
    candidates = []
    for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
        left, separator, right = line.partition(" - ")
        fields = left.split()
        if not separator or not right.startswith("cgroup2 ") or len(fields) < 5:
            continue
        root = PurePosixPath(_unescape_mount(fields[3]))
        mount = Path(_unescape_mount(fields[4]))
        if membership.is_relative_to(root):
            current = mount / str(membership.relative_to(root))
            candidates.append((len(root.parts), str(mount), mount, current))
    if not candidates:
        raise ValueError("no visible cgroup v2 mount matches membership")
    # A subtree mount is more specific than another view of the same hierarchy.
    _, _, mount, current = max(candidates, key=lambda item: item[:2])
    return mount, current, str(membership)


def _pairs(file):
    result = {}
    for line in file.read_text(encoding="ascii").splitlines():
        key, value = line.split()
        if key in result:
            raise ValueError("duplicate kernel counter")
        result[key] = _nonnegative(value)
    return result


def _memory_pressure(file):
    result = {"source": str(file), "status": "unavailable", "some": None, "full": None}
    try:
        rows = {}
        for line in file.read_text(encoding="ascii").splitlines():
            fields = line.split()
            if not fields or fields[0] not in ("some", "full"):
                continue
            kind, *tokens = fields
            if kind in rows:
                raise ValueError("duplicate pressure row")
            values = {}
            for token in tokens:
                key, separator, raw = token.partition("=")
                if not separator or key in values:
                    raise ValueError("invalid pressure field")
                values[key] = raw
            if not {"avg10", "avg60", "avg300", "total"}.issubset(values):
                raise ValueError("missing pressure field")
            row = {}
            for key in ("avg10", "avg60", "avg300"):
                raw = values[key]
                if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw):
                    raise ValueError("invalid pressure percentage")
                value = float(raw)
                if not 0 <= value <= 100:
                    raise ValueError("pressure percentage out of range")
                row[key + "_percent"] = value
            row["total_us"] = _nonnegative(values["total"])
            rows[kind] = row
        if set(rows) != {"some", "full"}:
            raise ValueError("missing pressure row")
        result.update(status="ok", **rows)
    except (OSError, UnicodeError, ValueError) as exc:
        result["error"] = _error(exc)
    return result


def _cgroup_memory():
    result = {"status": "unavailable", "scope": "visible_cgroup_v2_ancestors",
              "levels": [], "smallest_observed_headroom_bytes": None}
    try:
        mount, current, membership = _cgroup_location()
    except (OSError, UnicodeError, ValueError) as exc:
        result["error"] = _error(exc)
        return result
    result.update(mountpoint=str(mount), membership=membership)
    finite_headrooms = []
    directory = current
    while True:
        row = {"directory": str(directory), "current_bytes": None,
               "max_bytes": None, "max_status": "unavailable",
               "high_bytes": None, "high_status": "unavailable",
               "headroom_bytes": None, "errors": {}}
        for filename, key in (("memory.current", "current"),
                              ("memory.max", "max"), ("memory.high", "high")):
            try:
                raw = (directory / filename).read_text(encoding="ascii").strip()
                if key != "current" and raw == "max":
                    row[key + "_status"] = "unlimited"
                else:
                    row[key + "_bytes"] = _nonnegative(raw)
                    if key != "current":
                        row[key + "_status"] = "finite"
            except (OSError, UnicodeError, ValueError) as exc:
                row["errors"][filename] = _error(exc)
        if row["current_bytes"] is not None and row["max_status"] == "finite":
            row["headroom_bytes"] = max(0, row["max_bytes"] - row["current_bytes"])
            row["over_limit_bytes"] = max(0, row["current_bytes"] - row["max_bytes"])
            finite_headrooms.append(row["headroom_bytes"])
        result["levels"].append(row)
        if directory == mount:
            break
        directory = directory.parent
    result["smallest_observed_headroom_bytes"] = min(finite_headrooms) if finite_headrooms else None
    result["status"] = "ok" if all(not row["errors"] for row in result["levels"]) else "partial"
    for filename, key in (("memory.events", "events"), ("memory.stat", "stat_bytes")):
        try:
            values = _pairs(current / filename)
            if key == "stat_bytes":
                values = {name: values[name] for name in
                          ("anon", "file", "shmem", "kernel", "inactive_file", "active_file",
                           "file_mapped", "file_dirty", "file_writeback", "slab",
                           "slab_reclaimable", "slab_unreclaimable") if name in values}
            result[key] = values
        except (OSError, UnicodeError, ValueError) as exc:
            result[key] = None
            result.setdefault("errors", {})[filename] = _error(exc)
            result["status"] = "partial"
    result["pressure"] = _memory_pressure(current / "memory.pressure")
    if result["pressure"]["status"] != "ok":
        result.setdefault("errors", {})["memory.pressure"] = result["pressure"]["error"]
        result["status"] = "partial"
    return result


def _filesystem(value):
    result = {"requested_path": value, "available_bytes": None,
              "total_bytes": None, "inodes_available": None, "inodes_total": None}
    try:
        path = Path(value).expanduser().resolve(strict=True)
        usage = shutil.disk_usage(path)
        result.update(path=str(path), status="ok",
                      available_bytes=usage.free, total_bytes=usage.total)
        if hasattr(os, "statvfs"):
            stat = os.statvfs(path)
            result.update(inodes_available=stat.f_favail, inodes_total=stat.f_files)
            # Match statvfs's caller-available blocks, rather than reserved blocks.
            result["available_bytes"] = stat.f_bavail * stat.f_frsize
        else:
            result["inode_status"] = "unavailable"
    except (OSError, ValueError, RuntimeError) as exc:
        result.update(status="error", error=_error(exc))
    return result


def _process_row(raw, expected_pid):
    fields = {}
    for line in raw.splitlines():
        key, separator, value = line.partition(b":")
        if separator and key in (b"Name", b"Pid", b"PPid", b"VmRSS"):
            if key in fields:
                raise ValueError("duplicate process status field")
            fields[key] = value
    if not {b"Name", b"Pid", b"PPid"}.issubset(fields):
        raise ValueError("missing process status field")
    pid = _nonnegative(fields[b"Pid"].strip().decode("ascii"))
    parent_pid = _nonnegative(fields[b"PPid"].strip().decode("ascii"))
    if pid != expected_pid:
        raise ValueError("process status PID differs from directory")
    name = fields[b"Name"]
    name = name[1:] if name.startswith(b"\t") else name.lstrip(b" ")
    rss = None
    if b"VmRSS" in fields:
        value, unit = fields[b"VmRSS"].decode("ascii").split()
        if unit != "kB":
            raise ValueError("unexpected process RSS unit")
        rss = _nonnegative(value) * 1024
    return {"pid": pid, "parent_pid": parent_pid,
            "name": name.decode("utf-8", errors="backslashreplace"), "rss_bytes": rss}


def _process_rss(max_processes, max_status_bytes):
    coverage = {"max_processes": max_processes, "max_status_bytes": max_status_bytes,
                "max_bytes_per_status": PROCESS_STATUS_BYTES,
                "max_directory_entries": max_processes + 1024,
                "directory_entries_seen": 0, "pid_entries_seen": 0,
                "status_files_attempted": 0, "status_bytes_read": 0,
                "processes_returned": 0, "processes_with_rss": 0,
                "enumeration_complete": False, "stop_reason": None,
                "pending_pid": None, "unavailable_status_files": [],
                "truncated_status_files": [], "missing_rss_pids": []}
    result = {"source": "/proc/[pid]/status", "scope": "visible_procfs_processes",
              "status": "unavailable", "processes": [], "rss_sum_bytes": None,
              "coverage": coverage}
    try:
        with os.scandir("/proc") as entries:
            while coverage["directory_entries_seen"] < coverage["max_directory_entries"]:
                try:
                    entry = next(entries)
                except StopIteration:
                    coverage["enumeration_complete"] = True
                    break
                coverage["directory_entries_seen"] += 1
                if not entry.name.isascii() or not entry.name.isdecimal():
                    continue
                pid = int(entry.name)
                coverage["pid_entries_seen"] += 1
                if coverage["status_files_attempted"] >= max_processes:
                    coverage.update(stop_reason="process_limit", pending_pid=pid)
                    break
                remaining = max_status_bytes - coverage["status_bytes_read"]
                if remaining == 0:
                    coverage.update(stop_reason="total_byte_limit", pending_pid=pid)
                    break
                allowance = min(PROCESS_STATUS_BYTES, remaining)
                raw = bytearray()
                complete = False
                coverage["status_files_attempted"] += 1
                try:
                    with open(entry.path + "/status", "rb", buffering=0) as stream:
                        while len(raw) < allowance:
                            chunk = stream.read(min(8192, allowance - len(raw)))
                            if not chunk:
                                complete = True
                                break
                            raw.extend(chunk)
                            coverage["status_bytes_read"] += len(chunk)
                except OSError as exc:
                    coverage["unavailable_status_files"].append({"pid": pid, "error": _error(exc)})
                    continue
                if not complete:
                    reason = "total_byte_limit" if coverage["status_bytes_read"] == max_status_bytes else "per_status_byte_limit"
                    coverage["truncated_status_files"].append({"pid": pid, "reason": reason,
                                                              "bytes_read": len(raw)})
                    if reason == "total_byte_limit":
                        coverage["stop_reason"] = reason
                        break
                    continue
                try:
                    row = _process_row(bytes(raw), pid)
                except (UnicodeError, ValueError) as exc:
                    coverage["unavailable_status_files"].append({"pid": pid, "error": _error(exc)})
                    continue
                result["processes"].append(row)
                if row["rss_bytes"] is None:
                    coverage["missing_rss_pids"].append(pid)
            else:
                coverage["stop_reason"] = "directory_entry_limit"
    except OSError as exc:
        result["error"] = _error(exc)
        coverage["stop_reason"] = "directory_read_error"
    rows = result["processes"]
    rows.sort(key=lambda row: (row["rss_bytes"] is None, -(row["rss_bytes"] or 0), row["pid"]))
    coverage["processes_returned"] = len(rows)
    known = [row["rss_bytes"] for row in rows if row["rss_bytes"] is not None]
    coverage["processes_with_rss"] = len(known)
    result["rss_sum_bytes"] = sum(known) if known else None
    if "error" not in result or coverage["status_files_attempted"]:
        result["status"] = "ok" if (coverage["enumeration_complete"]
            and not coverage["unavailable_status_files"]
            and not coverage["truncated_status_files"]
            and not coverage["missing_rss_pids"]) else "partial"
    return result


def _positive_limit(maximum):
    def parse(raw):
        try:
            value = _nonnegative(raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("expected an integer from 1 to " + str(maximum)) from exc
        if not 1 <= value <= maximum:
            raise argparse.ArgumentTypeError("expected an integer from 1 to " + str(maximum))
        return value
    return parse


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", help="existing file/directory; repeat for each output filesystem (default: current directory)")
    parser.add_argument("--process-rss", action="store_true", help="include a bounded read of visible process PID, parent, short name and RSS")
    parser.add_argument("--max-processes", type=_positive_limit(4096), default=256,
                        help="status-file attempts with --process-rss (1..4096; default: 256)")
    parser.add_argument("--max-process-bytes", type=_positive_limit(8388608), default=1048576,
                        help="total status bytes with --process-rss (1..8388608; default: 1048576)")
    args = parser.parse_args(argv)
    started = _now()
    paths = args.path or ["."]
    report = {"schema": SCHEMA, "started_at": started, "host_memory": _host_memory(),
              "cgroup_memory": _cgroup_memory(),
              "filesystems": [_filesystem(value) for value in paths]}
    if args.process_rss:
        report["process_rss"] = _process_rss(args.max_processes, args.max_process_bytes)
    report["finished_at"] = _now()
    print(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))
    return 2 if any(row["status"] == "error" for row in report["filesystems"]) else 0


if __name__ == "__main__":
    sys.exit(main())

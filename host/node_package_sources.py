#!/usr/bin/env python3
"""Locate an exact installed Node package without changing its runtime."""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time

SCHEMA = "commons.node_package_sources/v1"
MANIFEST_LIMIT = 1024 * 1024
DEFAULT_EXCLUDES = {".git", ".hg", ".svn", "__pycache__"}


def positive_int(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def nonnegative_int(value):
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be at least 0")
    return parsed


def positive_seconds(value):
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return parsed


def package_name(value):
    parts = value.split("/")
    if (len(parts) == 1 and not value.startswith("@")) or (
        len(parts) == 2 and parts[0].startswith("@") and len(parts[0]) > 1
    ):
        if all(part not in ("", ".", "..") and "\\" not in part and "\x00" not in part
               for part in parts):
            return value
    raise argparse.ArgumentTypeError("use a package name or @scope/name")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=package_name)
    parser.add_argument("--version", required=True, help="exact manifest version; no semver ranges")
    parser.add_argument("--node-modules", action="append", default=[], metavar="DIRECTORY",
                        help="check this dependency directory directly; repeatable")
    parser.add_argument("--search-root", action="append", default=[], metavar="DIRECTORY",
                        help="discover node_modules below this directory; repeatable")
    parser.add_argument("--max-directories", type=positive_int, default=2000)
    parser.add_argument("--max-entries", type=positive_int, default=20000)
    parser.add_argument("--max-depth", type=nonnegative_int, default=8)
    parser.add_argument("--max-seconds", type=positive_seconds, default=10.0)
    parser.add_argument("--exclude-dir", action="append", default=[],
                        help="additional directory basename to skip during discovery")
    args = parser.parse_args(argv)
    if not args.node_modules and not args.search_root:
        parser.error("supply --node-modules or --search-root")
    if not args.version or args.version != args.version.strip():
        parser.error("--version must be a nonempty exact version without surrounding whitespace")

    started = time.monotonic()
    deadline = started + args.max_seconds
    excluded = DEFAULT_EXCLUDES | set(args.exclude_dir)
    matches, other_versions, manifest_mismatches, errors = [], [], [], []
    checked, observed_manifests, visited = set(), set(), set()
    reasons = set()
    counters = {"directories_visited": 0, "entries_examined": 0,
                "dependency_directories_checked": 0, "manifests_read": 0,
                "excluded_directories": 0, "directory_links_skipped": 0}
    queue = deque()
    unfinished_directory = None

    def expired():
        if time.monotonic() >= deadline:
            reasons.add("max_seconds")
            return True
        return False

    def error(path, operation, exc):
        errors.append({"path": str(path), "operation": operation,
                       "error": f"{type(exc).__name__}: {exc}"})
        reasons.add("read_errors")

    def directory(value, operation):
        try:
            path = Path(value).expanduser().resolve(strict=True)
            if not path.is_dir():
                raise NotADirectoryError(str(path))
            return path
        except (OSError, RuntimeError) as exc:
            error(value, operation, exc)
            return None

    def inspect_dependency_directory(path):
        if expired():
            return
        key = str(path)
        if key in checked:
            return
        checked.add(key)
        counters["dependency_directories_checked"] += 1
        requested = path.joinpath(*args.package.split("/"), "package.json")
        try:
            manifest = requested.resolve(strict=True)
            with os.fdopen(os.open(manifest, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)), "rb") as handle:
                before = os.fstat(handle.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ValueError("package manifest is not a regular file")
                if before.st_size > MANIFEST_LIMIT:
                    raise ValueError("package manifest exceeds the 1 MiB read limit")
                data = handle.read(MANIFEST_LIMIT + 1)
                after = os.fstat(handle.fileno())
            if len(data) > MANIFEST_LIMIT:
                raise ValueError("package manifest exceeds the 1 MiB read limit")
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns
            ):
                raise ValueError("package manifest changed while it was being read")
            identity = (after.st_dev, after.st_ino, hashlib.sha256(data).hexdigest())
            if identity in observed_manifests:
                return
            observed_manifests.add(identity)
            counters["manifests_read"] += 1
            metadata = json.loads(data)
            if not isinstance(metadata, dict):
                raise ValueError("package manifest is not a JSON object")
            record = {"name": metadata.get("name"), "version": metadata.get("version"),
                      "node_modules": str(path), "requested_manifest": str(requested),
                      "manifest": str(manifest), "package_directory": str(manifest.parent),
                      "manifest_sha256": identity[2], "manifest_bytes": len(data),
                      "node_engine": (metadata.get("engines") or {}).get("node")
                      if isinstance(metadata.get("engines"), dict) else None}
            if record["name"] != args.package:
                manifest_mismatches.append(record)
            elif record["version"] == args.version:
                matches.append(record)
            else:
                other_versions.append(record)
        except (FileNotFoundError, NotADirectoryError):
            return
        except (OSError, RuntimeError, ValueError, UnicodeError) as exc:
            error(requested, "read_manifest", exc)

    # Explicit donors are cheap and get priority over discovery.
    for value in args.node_modules:
        if expired():
            break
        path = directory(value, "read_explicit_directory")
        if path is not None:
            inspect_dependency_directory(path)

    for value in args.search_root:
        if expired():
            break
        path = directory(value, "read_search_root")
        if path is not None:
            queue.append((path, 0))

    while queue and not expired():
        if counters["directories_visited"] >= args.max_directories:
            reasons.add("max_directories")
            break
        path, depth = queue.popleft()
        try:
            info = path.stat()
            key = (info.st_dev, info.st_ino)
            if key in visited:
                continue
            visited.add(key)
            counters["directories_visited"] += 1
            if path.name == "node_modules":
                inspect_dependency_directory(path)
            if expired():
                unfinished_directory = str(path)
                break
            with os.scandir(path) as entries:
                for entry in entries:
                    if expired() or counters["entries_examined"] >= args.max_entries:
                        if counters["entries_examined"] >= args.max_entries:
                            reasons.add("max_entries")
                        unfinished_directory = str(path)
                        break
                    counters["entries_examined"] += 1
                    if entry.is_symlink():
                        if entry.is_dir():
                            counters["directory_links_skipped"] += 1
                        continue
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    if entry.name in excluded:
                        counters["excluded_directories"] += 1
                        continue
                    if depth >= args.max_depth:
                        reasons.add("max_depth")
                        continue
                    queue.append((Path(entry.path), depth + 1))
            if unfinished_directory is not None:
                break
        except OSError as exc:
            error(path, "scan_directory", exc)

    complete = not reasons
    outcome = "found" if matches else ("not_found_in_scope" if complete else "inconclusive")
    report = {
        "schema": SCHEMA,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "request": {"package": args.package, "version": args.version,
                    "node_modules": args.node_modules, "search_roots": args.search_root},
        "outcome": outcome,
        "matches": sorted(matches, key=lambda row: row["manifest"]),
        "other_versions": sorted(other_versions, key=lambda row: row["manifest"]),
        "manifest_name_mismatches": sorted(manifest_mismatches, key=lambda row: row["manifest"]),
        "coverage": {"complete": complete, "reasons": sorted(reasons),
                     "queued_directories": len(queue),
                     "unfinished_directory": unfinished_directory,
                     "excluded_directory_names": sorted(excluded),
                     "follow_directory_symlinks": False,
                     "limits": {"max_directories": args.max_directories,
                                "max_entries": args.max_entries, "max_depth": args.max_depth,
                                "max_seconds": args.max_seconds},
                     **counters},
        "errors": errors,
        "elapsed_seconds": round(time.monotonic() - started, 6),
    }
    print(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))
    return {"found": 0, "not_found_in_scope": 1, "inconclusive": 2}[outcome]


if __name__ == "__main__":
    raise SystemExit(main())

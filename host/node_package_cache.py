#!/usr/bin/env python3
"""Inspect or copy one exact package from an explicitly selected npm cache."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import zlib

SCHEMA = "commons.node_package_cache/v1"
MANIFEST_LIMIT = 1024 * 1024
DIGEST_BYTES = {"sha1": 20, "sha256": 32, "sha384": 48, "sha512": 64}


class SourceError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def positive_int(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def exact_text(value):
    if not value or value != value.strip() or "\x00" in value:
        raise argparse.ArgumentTypeError("must be nonempty without surrounding whitespace or NUL")
    return value


def integrity(value):
    algorithm, separator, encoded = value.partition("-")
    try:
        digest = base64.b64decode(encoded, validate=True)
    except ValueError:
        digest = b""
    if (not separator or algorithm not in DIGEST_BYTES
            or len(digest) != DIGEST_BYTES.get(algorithm)
            or base64.b64encode(digest).decode("ascii") != encoded):
        raise argparse.ArgumentTypeError(
            "use one canonical sha1-, sha256-, sha384- or sha512- base64 integrity value"
        )
    return value, algorithm, digest


def read_archive(path, limit):
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise SourceError("CACHE_READ", "cached content is not a regular file")
            if before.st_size > limit:
                raise SourceError("LIMIT_EXCEEDED", "cached archive exceeds --max-archive-bytes")
            data = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SourceError("CACHE_READ", str(exc)) from exc
    if len(data) > limit:
        raise SourceError("LIMIT_EXCEEDED", "cached archive exceeds --max-archive-bytes")
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_size, after.st_mtime_ns, after.st_ctime_ns
    ):
        raise SourceError("CACHE_READ", "cached content changed while it was being read")
    return data


def member_path(name):
    if not name or name.startswith("/") or "\\" in name or "\x00" in name:
        raise SourceError("INVALID_ARCHIVE", f"invalid archive path: {name!r}")
    parts = name.rstrip("/").split("/")
    while parts and parts[0] == ".":
        parts.pop(0)
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise SourceError("INVALID_ARCHIVE", f"invalid archive path: {name!r}")
    # Drive-qualified names must not become absolute paths on Windows.
    if any(":" in part for part in parts):
        raise SourceError("INVALID_ARCHIVE", f"drive-qualified archive path: {name!r}")
    return tuple(parts)


def inspect_archive(archive, args, report):
    entries, roots, seen, directories = [], set(), set(), set()
    count, file_bytes = 0, 0
    manifest_member = None
    for member in archive:
        count += 1
        if count > args.max_members:
            raise SourceError("LIMIT_EXCEEDED", "archive exceeds --max-members")
        if member.issparse() or not (member.isfile() or member.isdir()):
            raise SourceError("INVALID_ARCHIVE", f"unsupported archive member type: {member.name!r}")
        parts = member_path(member.name)
        roots.add(parts[0])
        if len(roots) != 1:
            raise SourceError("INVALID_ARCHIVE", "archive must have one package root directory")
        relative = parts[1:]
        if relative in seen:
            raise SourceError("INVALID_ARCHIVE", f"duplicate archive path: {member.name!r}")
        seen.add(relative)
        if not relative:
            if not member.isdir():
                raise SourceError("INVALID_ARCHIVE", "archive root is not a directory")
            continue
        directories.update(relative[:index] for index in range(1, len(relative)))
        if member.isdir():
            directories.add(relative)
        else:
            if member.size < 0:
                raise SourceError("INVALID_ARCHIVE", f"negative file size: {member.name!r}")
            file_bytes += member.size
            if file_bytes > args.max_tar_bytes:
                raise SourceError("LIMIT_EXCEEDED", "package contents exceed --max-tar-bytes")
            if relative == ("package.json",):
                manifest_member = member
        entries.append((member, relative))
    if any(member.isfile() and relative in directories for member, relative in entries):
        raise SourceError("INVALID_ARCHIVE", "a package file is also used as a directory")
    if manifest_member is None:
        raise SourceError("INVALID_ARCHIVE", "archive has no root package.json file")
    if manifest_member.size > MANIFEST_LIMIT:
        raise SourceError("LIMIT_EXCEEDED", "package.json exceeds the 1 MiB manifest limit")
    with archive.extractfile(manifest_member) as handle:
        manifest = handle.read(MANIFEST_LIMIT + 1)
    if len(manifest) != manifest_member.size:
        raise SourceError("INVALID_ARCHIVE", "package.json is truncated")
    try:
        metadata = json.loads(manifest)
    except (ValueError, UnicodeError) as exc:
        raise SourceError("INVALID_ARCHIVE", f"package.json is not valid JSON: {exc}") from exc
    if not isinstance(metadata, dict):
        raise SourceError("INVALID_ARCHIVE", "package.json is not a JSON object")
    if metadata.get("name") != args.package or metadata.get("version") != args.version:
        raise SourceError(
            "PACKAGE_MISMATCH",
            f"expected {args.package!r}@{args.version!r}; "
            f"archive contains {metadata.get('name')!r}@{metadata.get('version')!r}",
        )
    engines = metadata.get("engines")
    node_engine = engines.get("node") if isinstance(engines, dict) else None
    report["package"] = {
        "name": metadata["name"], "version": metadata["version"],
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "manifest_bytes": len(manifest),
        "node_engine": node_engine if isinstance(node_engine, str) else None,
    }
    report["archive"].update({
        "root": next(iter(roots)), "members": count,
        "files": sum(member.isfile() for member, _ in entries),
        "file_bytes": file_bytes,
    })
    return entries, directories


def materialize(archive, entries, directories, args, cache_root, report):
    requested = Path(args.destination).expanduser()
    try:
        parent = requested.parent.resolve(strict=True)
        if not parent.is_dir() or not requested.name:
            raise SourceError("DESTINATION_ERROR", "destination needs an existing parent directory")
        destination = parent / requested.name
        report["destination"]["path"] = str(destination)
        if destination == cache_root or cache_root in destination.parents:
            raise SourceError("DESTINATION_ERROR", "destination must be outside the source cache")
        if os.path.lexists(destination):
            raise SourceError("DESTINATION_EXISTS", "destination already exists; choose a new package directory")
        destination.mkdir(mode=0o755)
        report["destination"]["created"] = True
        for relative in sorted(directories, key=lambda parts: (len(parts), parts)):
            destination.joinpath(*relative).mkdir(mode=0o755)
        for member, relative in entries:
            if member.isdir():
                continue
            target = destination.joinpath(*relative)
            remaining = member.size
            with archive.extractfile(member) as source, target.open("xb") as output:
                while remaining:
                    block = source.read(min(1024 * 1024, remaining))
                    if not block:
                        raise SourceError("INVALID_ARCHIVE", f"truncated package file: {member.name!r}")
                    output.write(block)
                    remaining -= len(block)
                    report["destination"]["bytes_written"] += len(block)
            target.chmod(0o644 | (member.mode & 0o111))
            report["destination"]["files_written"] += 1
        report["destination"]["complete"] = True
    except (OSError, RuntimeError) as exc:
        raise SourceError("DESTINATION_ERROR", str(exc)) from exc


def run(args, report):
    try:
        cache_root = Path(args.cache_root).expanduser().resolve(strict=True)
        if not cache_root.is_dir():
            raise SourceError("CACHE_READ", "--cache-root is not a directory")
    except (OSError, RuntimeError) as exc:
        raise SourceError("CACHE_READ", str(exc)) from exc
    value, algorithm, digest = args.integrity
    key = digest.hex()
    path = cache_root / "content-v2" / algorithm / key[:2] / key[2:4] / key[4:]
    report["source"] = {"cache_root": str(cache_root), "path": str(path),
                        "integrity": value, "integrity_verified": False}
    compressed = read_archive(path, args.max_archive_bytes)
    if compressed is None:
        report["outcome"] = "not_found_in_scope"
        return 1
    if hashlib.new(algorithm, compressed).digest() != digest:
        raise SourceError("INTEGRITY_MISMATCH", "cached archive does not match the supplied integrity")
    report["source"]["integrity_verified"] = True
    report["archive"] = {"bytes": len(compressed),
                         "sha256": hashlib.sha256(compressed).hexdigest()}
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            expanded = stream.read(args.max_tar_bytes + 1)
        if len(expanded) > args.max_tar_bytes:
            raise SourceError("LIMIT_EXCEEDED", "expanded archive exceeds --max-tar-bytes")
        report["archive"]["tar_bytes"] = len(expanded)
        with tarfile.open(fileobj=io.BytesIO(expanded), mode="r:") as archive:
            entries, directories = inspect_archive(archive, args, report)
            if args.destination is not None:
                materialize(archive, entries, directories, args, cache_root, report)
    except (OSError, EOFError, ValueError, tarfile.TarError, zlib.error) as exc:
        raise SourceError("INVALID_ARCHIVE", str(exc)) from exc
    report["outcome"] = "materialized" if args.destination is not None else "verified"
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", required=True, type=exact_text,
                        help="explicit npm _cacache directory; no cache root is inferred")
    parser.add_argument("--package", required=True, type=exact_text)
    parser.add_argument("--version", required=True, type=exact_text,
                        help="exact package.json version, not a semver range")
    parser.add_argument("--integrity", required=True, type=integrity,
                        help="one exact integrity value, preferably from the consumer's lockfile")
    parser.add_argument("--destination", type=exact_text,
                        help="copy package contents into this new directory; parent must exist")
    parser.add_argument("--max-archive-bytes", type=positive_int, default=32 * 1024 * 1024)
    parser.add_argument("--max-tar-bytes", type=positive_int, default=128 * 1024 * 1024)
    parser.add_argument("--max-members", type=positive_int, default=20000)
    args = parser.parse_args(argv)
    report = {
        "schema": SCHEMA,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "request": {"cache_root": args.cache_root, "package": args.package,
                    "version": args.version, "integrity": args.integrity[0],
                    "destination": args.destination},
        "outcome": "error", "source": None, "archive": None, "package": None,
        "destination": {"path": args.destination, "created": False, "complete": False,
                        "files_written": 0, "bytes_written": 0}
        if args.destination is not None else None,
        "limits": {"max_archive_bytes": args.max_archive_bytes,
                   "max_tar_bytes": args.max_tar_bytes, "max_members": args.max_members,
                   "manifest_bytes": MANIFEST_LIMIT},
        "error": None,
    }
    try:
        code = run(args, report)
    except SourceError as exc:
        report["error"] = {"code": exc.code, "message": str(exc)}
        code = 2
    print(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

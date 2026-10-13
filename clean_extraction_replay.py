#!/usr/bin/env python3
"""Replay ZIP/TAR deliverables in a private fresh directory and verify a manifest."""
from __future__ import annotations

import argparse
import json
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

from clean_extraction_archive import extract_tar, extract_zip
from clean_extraction_io import hash_fresh, sha256, stable_read, write_new
from clean_extraction_manifest import ReplayError, validate_manifest

REPLAY_SCHEMA = "commons-clean-extraction-replay/v1"
MAX_FILES = 10_000
MAX_BYTES = 1 << 30
MAX_ARCHIVE = 512 << 20
MAX_MANIFEST = 8 << 20


def replay_archive(
    archive: Path,
    manifest_raw: bytes,
    *,
    max_files=MAX_FILES,
    max_uncompressed_bytes=MAX_BYTES,
    max_archive_bytes=MAX_ARCHIVE,
):
    if isinstance(max_files, bool) or not isinstance(max_files, int) or max_files <= 0:
        raise ReplayError("max_files must be positive")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in (max_uncompressed_bytes, max_archive_bytes)
    ):
        raise ReplayError("byte limits must be positive integers")
    manifest, expected = validate_manifest(manifest_raw)
    if len(expected) > max_files:
        raise ReplayError("manifest file count exceeds replay limit")
    if sum(row["bytes"] for row in expected) > max_uncompressed_bytes:
        raise ReplayError("manifest bytes exceed replay limit")

    with tempfile.TemporaryDirectory(prefix="clean-extraction-replay-") as temp:
        box = Path(temp)
        staged = box / "input.archive"
        archive_data = stable_read(archive, max_archive_bytes, "archive")
        staged.write_bytes(archive_data)
        archive_sha = sha256(archive_data)
        fresh = box / "fresh"
        fresh.mkdir()
        if zipfile.is_zipfile(staged):
            archive_format = "zip"
            count, byte_count = extract_zip(
                staged, fresh, max_files, max_uncompressed_bytes
            )
        elif tarfile.is_tarfile(staged):
            archive_format = "tar"
            count, byte_count = extract_tar(
                staged, fresh, max_files, max_uncompressed_bytes
            )
        else:
            raise ReplayError("unsupported archive format")

        actual = hash_fresh(fresh)
        if actual != expected:
            expected_by_path = {row["path"]: row for row in expected}
            actual_by_path = {row["path"]: row for row in actual}
            missing = sorted(set(expected_by_path) - set(actual_by_path))
            extra = sorted(set(actual_by_path) - set(expected_by_path))
            changed = sorted(
                path
                for path in set(expected_by_path) & set(actual_by_path)
                if expected_by_path[path] != actual_by_path[path]
            )
            raise ReplayError(
                f"fresh extraction mismatch: missing={missing}, "
                f"extra={extra}, changed={changed}"
            )
        if count != len(actual) or byte_count != sum(row["bytes"] for row in actual):
            raise ReplayError("extraction accounting mismatch")

    return {
        "schema": REPLAY_SCHEMA,
        "archive_sha256": archive_sha,
        "archive_format": archive_format,
        "manifest_sha256": manifest["manifest_sha256"],
        "files_verified": len(expected),
        "bytes_verified": sum(row["bytes"] for row in expected),
        "fresh_extraction": True,
        "verified": True,
    }


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-files", type=int, default=MAX_FILES)
    parser.add_argument("--max-uncompressed-bytes", type=int, default=MAX_BYTES)
    parser.add_argument("--max-archive-bytes", type=int, default=MAX_ARCHIVE)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    archive = args.archive.absolute()
    manifest = args.manifest.absolute()
    output = args.output.absolute()
    if output.resolve() in {archive.resolve(), manifest.resolve()}:
        raise ReplayError("receipt output must not alias archive or manifest input")
    receipt = replay_archive(
        archive,
        stable_read(manifest, MAX_MANIFEST, "manifest"),
        max_files=args.max_files,
        max_uncompressed_bytes=args.max_uncompressed_bytes,
        max_archive_bytes=args.max_archive_bytes,
    )
    write_new(
        output,
        (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode(),
    )
    print(receipt["archive_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

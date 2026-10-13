#!/usr/bin/env python3
"""Verify or extract the exact historical BASALT42 review; never apply its patch.

The five parts are transport segmentation, not separate archives. Verification
checks their hashes, the joined XZ, and every archived file. Extraction only
creates a new directory. No archived code is executed and no network is used.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import lzma
from pathlib import Path, PurePosixPath
import sys
import tarfile

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA256 = "115345ce0ba6b3ccb6c23455b53ddbf9ef7fb9b61e9a340dde6bcc738c1d9f3d"
ARCHIVE_BYTES = 30888
FILE_COUNT = 26
CONTENT_BYTES = 220838
MAX_TAR_BYTES = 1024 * 1024
ROOT_NAME = "zz-basalt42-workbench-review"
PARTS = (
    (7500, "6e7a7b5226fdbe262a804d905ffe92d68ac8e4efd67f6f5dcf515268e3f8eefc"),
    (7500, "92f2ce687a90a01d808c2e143b9c3429d3a4f0fddf382ca183500ea1829cfa8b"),
    (7500, "1dd53611627d319a3707d1164a74ffef6c08d64a804ec2262a83050fa2842451"),
    (7500, "8553bcaca92287dfbfb627e9bf08a5060a2603cd81829fa2d2810afab9f1573f"),
    (888, "93a46087d7776586681c426aaa5c1de34f80b8ccd4727922e11a4154ad4651c3"),
)


class ArchiveError(ValueError):
    """The retained package cannot be verified or safely reconstructed."""


def member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or "\\" in name or "\0" in name
            or ".." in path.parts or not path.parts or path.parts[0] != ROOT_NAME
            or path.as_posix() != name):
        raise ArchiveError(f"unexpected archive member path: {name!r}")
    return path


def verify(root: Path = HERE) -> dict[str, bytes]:
    chunks = []
    for index, (size, digest) in enumerate(PARTS, 1):
        name = f"retained.tar.xz.part-{index:02d}"
        part = root / name
        if part.is_symlink() or not part.is_file():
            raise ArchiveError(f"missing regular archive part: {name}")
        if part.stat().st_size != size:
            raise ArchiveError(f"incorrect archive part size: {name}")
        raw = part.read_bytes()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise ArchiveError(f"archive part digest mismatch: {name}")
        chunks.append(raw)
    raw = b"".join(chunks)
    if len(raw) != ARCHIVE_BYTES or hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise ArchiveError("joined archive digest or size mismatch")
    decoder = lzma.LZMADecompressor(memlimit=256 * 1024 * 1024)
    decoded = decoder.decompress(raw, max_length=MAX_TAR_BYTES + 1)
    if len(decoded) > MAX_TAR_BYTES or not decoder.eof or decoder.unused_data:
        raise ArchiveError("unexpected compressed archive boundary")
    files: dict[str, bytes] = {}
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(decoded), mode="r:") as archive:
        for member in archive.getmembers():
            member_path(member.name)
            if member.name in seen:
                raise ArchiveError(f"duplicate archive member: {member.name}")
            seen.add(member.name)
            if member.isdir():
                continue
            if not member.isfile() or member.size < 0:
                raise ArchiveError(f"not a regular file: {member.name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ArchiveError(f"unreadable archive member: {member.name}")
            with stream:
                contents = stream.read(member.size + 1)
            if len(contents) != member.size:
                raise ArchiveError(f"archive member length mismatch: {member.name}")
            files[member.name] = contents
    if len(files) != FILE_COUNT or sum(map(len, files.values())) != CONTENT_BYTES:
        raise ArchiveError("retained file inventory does not match the fixed archive")
    return files


def extract(root: Path, destination: Path) -> dict[str, bytes]:
    files = verify(root)  # Validate completely before creating the destination.
    if not destination.parent.is_dir():
        raise ArchiveError("extraction destination parent must already exist")
    destination.mkdir(exist_ok=False)
    for name, contents in files.items():
        target = destination.joinpath(*member_path(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(contents)
        if target.read_bytes() != contents:
            raise ArchiveError(f"written file does not match archive: {name}")
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", type=Path, metavar="NEW_DIRECTORY")
    args = parser.parse_args(argv)
    try:
        files = extract(HERE, args.extract) if args.extract else verify()
    except (ArchiveError, OSError, EOFError, lzma.LZMAError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "status": "VERIFIED_HISTORICAL_REFERENCE",
        "archive_sha256": ARCHIVE_SHA256,
        "files": len(files), "content_bytes": sum(map(len, files.values())),
        "extracted_to": str(args.extract) if args.extract else None,
        "production_patch_applied": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

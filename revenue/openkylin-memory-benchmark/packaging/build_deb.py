#!/usr/bin/env python3
"""Deterministic Debian package builder/verifier for KylinMemBench.

Uses only Python's standard library so the package can be reproduced in constrained
CI. The generated .deb is an ar archive containing debian-binary, control.tar.gz,
and data.tar.gz with normalized metadata and gzip timestamps.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import Iterable

PACKAGE = "kylin-memory-benchmark"
VERSION = "0.2.0"
ARCH = "all"
AR_MAGIC = b"!<arch>\n"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _tar_gz(entries: Iterable[tuple[str, bytes, int]]) -> bytes:
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0, compresslevel=9) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.USTAR_FORMAT) as tf:
            for name, data, mode in sorted(entries, key=lambda item: item[0]):
                posix = PurePosixPath(name)
                if posix.is_absolute() or ".." in posix.parts:
                    raise ValueError(f"unsafe tar path: {name}")
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                info.mode = mode
                info.mtime = 0
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                tf.addfile(info, io.BytesIO(data))
    return raw.getvalue()


def _ar_member(name: str, data: bytes, mode: int = 0o100644) -> bytes:
    encoded = (name + "/").encode("ascii")
    if len(encoded) > 16:
        raise ValueError(f"ar member name too long: {name}")
    header = b"".join(
        [
            encoded.ljust(16, b" "),
            b"0".ljust(12, b" "),
            b"0".ljust(6, b" "),
            b"0".ljust(6, b" "),
            format(mode, "o").encode("ascii").ljust(8, b" "),
            str(len(data)).encode("ascii").ljust(10, b" "),
            b"`\n",
        ]
    )
    if len(header) != 60:
        raise AssertionError("invalid ar header length")
    return header + data + (b"\n" if len(data) % 2 else b"")


def _read_required(root: Path, relative: str) -> bytes:
    path = root / relative
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError(f"missing package source {relative}: {exc}") from exc


def _wrapper(module_path: str) -> bytes:
    return ("#!/bin/sh\nexec python3 " + module_path + ' "$@"\n').encode("utf-8")


def build_package(root: Path, out_path: Path) -> dict[str, object]:
    baseline = _read_required(root, "kylin_memory_bench.py")
    dynamics = _read_required(root, "memory_dynamics.py")
    readme = _read_required(root, "README.md")
    submission = _read_required(root, "SUBMISSION.md")

    control = (
        f"Package: {PACKAGE}\n"
        f"Version: {VERSION}\n"
        "Section: utils\n"
        "Priority: optional\n"
        f"Architecture: {ARCH}\n"
        "Depends: python3 (>= 3.10)\n"
        "Maintainer: Token Junkie Labs <tokenjunkielabs@gmail.com>\n"
        "Description: deterministic long-term-memory benchmark for openKylin agents\n"
        " Includes the literal KylinMemBench scorer plus Memory Dynamics V2 adversarial\n"
        " scenario generation, repeated-trial stability analysis, and replay receipts.\n"
    ).encode("utf-8")

    manifest = {
        "package": PACKAGE,
        "version": VERSION,
        "architecture": ARCH,
        "files": {
            "kylin_memory_bench.py": sha256_bytes(baseline),
            "memory_dynamics.py": sha256_bytes(dynamics),
            "README.md": sha256_bytes(readme),
            "SUBMISSION.md": sha256_bytes(submission),
        },
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")

    control_tgz = _tar_gz([("./control", control, 0o644)])
    data_tgz = _tar_gz(
        [
            ("./usr/bin/kylin-memory-bench", _wrapper("/usr/lib/kylin-memory-benchmark/kylin_memory_bench.py"), 0o755),
            ("./usr/bin/kylin-memory-dynamics", _wrapper("/usr/lib/kylin-memory-benchmark/memory_dynamics.py"), 0o755),
            ("./usr/lib/kylin-memory-benchmark/kylin_memory_bench.py", baseline, 0o644),
            ("./usr/lib/kylin-memory-benchmark/memory_dynamics.py", dynamics, 0o644),
            ("./usr/share/doc/kylin-memory-benchmark/README.md", readme, 0o644),
            ("./usr/share/doc/kylin-memory-benchmark/SUBMISSION.md", submission, 0o644),
            ("./usr/share/doc/kylin-memory-benchmark/package-manifest.json", manifest_bytes, 0o644),
        ]
    )
    package = AR_MAGIC + _ar_member("debian-binary", b"2.0\n") + _ar_member("control.tar.gz", control_tgz) + _ar_member("data.tar.gz", data_tgz)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(package)
    return {"path": str(out_path), "sha256": sha256_bytes(package), "size": len(package)}


def _parse_ar(data: bytes) -> list[tuple[str, bytes]]:
    if not data.startswith(AR_MAGIC):
        raise ValueError("not a Debian ar archive")
    offset = len(AR_MAGIC)
    members: list[tuple[str, bytes]] = []
    while offset < len(data):
        if offset + 60 > len(data):
            raise ValueError("truncated ar header")
        header = data[offset : offset + 60]
        offset += 60
        if header[58:60] != b"`\n":
            raise ValueError("invalid ar member trailer")
        name = header[:16].decode("ascii").strip().rstrip("/")
        try:
            size = int(header[48:58].decode("ascii").strip())
        except ValueError as exc:
            raise ValueError("invalid ar member size") from exc
        if size < 0 or offset + size > len(data):
            raise ValueError("truncated ar member")
        payload = data[offset : offset + size]
        offset += size
        if size % 2:
            if offset >= len(data):
                raise ValueError("missing ar padding")
            offset += 1
        members.append((name, payload))
    return members


def _verify_tar(payload: bytes, *, expected: set[str], executable: set[str] = frozenset()) -> None:
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tf:
            members = tf.getmembers()
            names = {member.name for member in members}
            if names != expected:
                raise ValueError(f"tar member set mismatch: expected {sorted(expected)}, got {sorted(names)}")
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError(f"unsafe tar member path: {member.name}")
                if not member.isfile():
                    raise ValueError(f"non-regular tar member: {member.name}")
                wanted_exec = member.name in executable
                if wanted_exec and member.mode != 0o755:
                    raise ValueError(f"executable mode mismatch: {member.name}")
                if not wanted_exec and member.mode != 0o644:
                    raise ValueError(f"file mode mismatch: {member.name}")
                if member.mtime != 0 or member.uid != 0 or member.gid != 0:
                    raise ValueError(f"non-deterministic tar metadata: {member.name}")
    except (tarfile.TarError, OSError) as exc:
        raise ValueError(f"invalid tar.gz member: {exc}") from exc


def verify_package(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    members = _parse_ar(data)
    names = [name for name, _ in members]
    if names != ["debian-binary", "control.tar.gz", "data.tar.gz"]:
        raise ValueError(f"unexpected Debian members: {names}")
    member_map = dict(members)
    if member_map["debian-binary"] != b"2.0\n":
        raise ValueError("unsupported debian-binary version")
    _verify_tar(member_map["control.tar.gz"], expected={"./control"})
    data_expected = {
        "./usr/bin/kylin-memory-bench",
        "./usr/bin/kylin-memory-dynamics",
        "./usr/lib/kylin-memory-benchmark/kylin_memory_bench.py",
        "./usr/lib/kylin-memory-benchmark/memory_dynamics.py",
        "./usr/share/doc/kylin-memory-benchmark/README.md",
        "./usr/share/doc/kylin-memory-benchmark/SUBMISSION.md",
        "./usr/share/doc/kylin-memory-benchmark/package-manifest.json",
    }
    _verify_tar(
        member_map["data.tar.gz"],
        expected=data_expected,
        executable={"./usr/bin/kylin-memory-bench", "./usr/bin/kylin-memory-dynamics"},
    )
    return {"valid": True, "sha256": sha256_bytes(data), "size": len(data), "members": names}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="build-deb")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.verify:
            print(json.dumps(verify_package(args.verify), sort_keys=True))
            return 0
        out = args.out or Path("build") / f"{PACKAGE}_{VERSION}_{ARCH}.deb"
        built = build_package(args.root, out)
        verified = verify_package(out)
        print(json.dumps({"built": built, "verified": verified}, sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

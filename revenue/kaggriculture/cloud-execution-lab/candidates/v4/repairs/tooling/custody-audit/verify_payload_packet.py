#!/usr/bin/env python3
"""Verify a checksum-bound raw-byte handoff before Git custody.

This tool is intentionally boring: it does not fetch, decode, reconstruct, execute,
import, write, or publish payload members.  It only verifies an already-materialized
packet directory against a strict manifest and emits a deterministic JSON receipt.

Exit 0: the packet is complete and every declared byte identity matches.
Exit 1: the packet is well-formed but incomplete/mismatched/contains extras.
Exit 2: invalid manifest, unsafe filesystem shape, or I/O error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "titan-v4-payload-packet/v1"
RECEIPT_SCHEMA = "titan-v4-payload-verification/v1"
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
TOP_KEYS = {"schema", "packet", "members"}
MEMBER_KEYS = {"path", "size", "git_blob", "sha256"}


class ManifestError(ValueError):
    """The manifest or filesystem cannot be interpreted safely."""


class PacketMismatch(ValueError):
    """The packet is safe to inspect but does not match its declaration."""


def require(ok: bool, message: str) -> None:
    # Never use assert: verification semantics must survive python -O.
    if not ok:
        raise ManifestError(message)


def strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            require(type(key) is str and key not in out,
                    "duplicate or non-string JSON key: " + repr(key))
            out[key] = value
        return out

    def bad_constant(value: str) -> None:
        raise ManifestError("non-finite JSON value: " + value)

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=bad_constant)
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, ManifestError):
            raise
        raise ManifestError("invalid manifest JSON: " + str(exc)) from exc


def canonical_member_path(value: Any) -> str:
    require(type(value) is str and bool(value), "member path must be a non-empty string")
    require("\\" not in value, "member path must use POSIX separators")
    require(all(ord(ch) >= 32 and ord(ch) != 127 for ch in value),
            "member path contains a control character")
    require(unicodedata.normalize("NFC", value) == value,
            "member path must use NFC Unicode normalization")
    path = PurePosixPath(value)
    require(not path.is_absolute(), "member path must be relative")
    require(str(path) == value, "member path is not canonical")
    require(all(part not in {"", ".", ".."} for part in path.parts),
            "member path contains an unsafe segment")
    return value


def parse_manifest(raw: bytes) -> tuple[str, list[dict[str, Any]]]:
    doc = strict_json(raw)
    require(type(doc) is dict, "manifest root must be an object")
    require(set(doc) == TOP_KEYS, "manifest keys must be exactly schema, packet, members")
    require(doc["schema"] == SCHEMA, "unsupported manifest schema")
    require(type(doc["packet"]) is str and bool(doc["packet"].strip()),
            "packet must be a non-empty string")
    members = doc["members"]
    require(type(members) is list and bool(members), "members must be a non-empty list")

    seen: set[str] = set()
    seen_casefold: set[str] = set()
    parsed: list[dict[str, Any]] = []
    for index, item in enumerate(members):
        require(type(item) is dict, f"member {index} must be an object")
        require(set(item) == MEMBER_KEYS,
                f"member {index} keys must be exactly path, size, git_blob, sha256")
        path = canonical_member_path(item["path"])
        folded = path.casefold()
        require(path not in seen, "duplicate member path: " + path)
        require(folded not in seen_casefold, "case-folding member collision: " + path)
        seen.add(path)
        seen_casefold.add(folded)
        size = item["size"]
        require(type(size) is int and size >= 0, "member size must be a non-negative integer")
        git_blob = item["git_blob"]
        sha256 = item["sha256"]
        require(type(git_blob) is str and SHA1.fullmatch(git_blob) is not None,
                "git_blob must be a lowercase full SHA-1")
        require(type(sha256) is str and SHA256.fullmatch(sha256) is not None,
                "sha256 must be a lowercase full SHA-256")
        parsed.append({"path": path, "size": size, "git_blob": git_blob, "sha256": sha256})
    return doc["packet"], parsed


def git_blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def scan_packet(root: Path) -> dict[str, Path]:
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise ManifestError("cannot stat packet directory: " + str(exc)) from exc
    require(stat.S_ISDIR(root_stat.st_mode), "packet root must be a directory")
    require(not stat.S_ISLNK(root_stat.st_mode), "packet root must not be a symlink")

    files: dict[str, Path] = {}

    def walk(directory: Path, prefix: str = "") -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda e: os.fsencode(e.name))
        except OSError as exc:
            raise ManifestError("cannot scan packet directory: " + str(exc)) from exc
        for entry in entries:
            rel = entry.name if not prefix else prefix + "/" + entry.name
            canonical_member_path(rel)
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
            except OSError as exc:
                raise ManifestError("cannot stat packet member " + rel + ": " + str(exc)) from exc
            require(not stat.S_ISLNK(mode), "symlink packet entry rejected: " + rel)
            if stat.S_ISDIR(mode):
                walk(Path(entry.path), rel)
            else:
                require(stat.S_ISREG(mode), "non-regular packet entry rejected: " + rel)
                require(rel not in files, "duplicate filesystem member: " + rel)
                files[rel] = Path(entry.path)

    walk(root)
    return files


def verify(manifest_raw: bytes, packet_root: Path) -> dict[str, Any]:
    packet, declared = parse_manifest(manifest_raw)
    actual = scan_packet(packet_root)
    expected_paths = {member["path"] for member in declared}
    actual_paths = set(actual)
    missing = sorted(expected_paths - actual_paths)
    extras = sorted(actual_paths - expected_paths)
    if missing or extras:
        raise PacketMismatch(json.dumps({"missing": missing, "extras": extras}, sort_keys=True))

    receipt_members: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    for member in sorted(declared, key=lambda item: item["path"].encode("utf-8")):
        path = member["path"]
        try:
            data = actual[path].read_bytes()
        except OSError as exc:
            raise ManifestError("cannot read packet member " + path + ": " + str(exc)) from exc
        observed = {
            "path": path,
            "size": len(data),
            "git_blob": git_blob_id(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        fields = [field for field in ("size", "git_blob", "sha256")
                  if observed[field] != member[field]]
        if fields:
            mismatches.append({"path": path, "fields": fields,
                               "expected": {field: member[field] for field in fields},
                               "observed": {field: observed[field] for field in fields}})
        receipt_members.append(observed)
    if mismatches:
        raise PacketMismatch(json.dumps({"mismatches": mismatches}, sort_keys=True))

    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    return {
        "schema": RECEIPT_SCHEMA,
        "packet": packet,
        "manifest_sha256": manifest_sha256,
        "member_count": len(receipt_members),
        "packet_verified": True,
        "members": receipt_members,
        "interpretation": (
            "Exact byte custody only. This receipt does not prove source semantics, execution, "
            "composition safety, economics, approval, Git publication, or activation."
        ),
    }


def failure(kind: str, message: str) -> dict[str, Any]:
    return {"schema": RECEIPT_SCHEMA, "packet_verified": False,
            "error_kind": kind, "error": message}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="strict JSON packet manifest")
    parser.add_argument("packet_dir", type=Path, help="materialized packet directory")
    args = parser.parse_args(argv)
    try:
        raw = args.manifest.read_bytes()
        result = verify(raw, args.packet_dir)
        code = 0
    except PacketMismatch as exc:
        result = failure("packet_mismatch", str(exc))
        code = 1
    except (ManifestError, OSError) as exc:
        result = failure("invalid_evidence", str(exc))
        code = 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    sys.exit(main())

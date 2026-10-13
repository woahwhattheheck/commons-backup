#!/usr/bin/env python3
"""Verify the exact recovered DOCK temporal-routing V2 archives in place.

This verifier reads ZIP members without extracting them. It checks the outer
archive identity, ZIP integrity, the complete internal manifest, exact member
set, and the two critical V2 source files. It does not execute a solver or
change the selected ROADEF candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping
from zipfile import BadZipFile, ZipFile

PREFIX = "ROADEF-DOCK-temporal-routes/"
SOURCE_MANIFEST = PREFIX + "SOURCE-BUNDLE-CONTENTS.json"
SOURCE_NOTICE = PREFIX + "SOURCE-BUNDLE-NOTICE.md"
EVIDENCE_MANIFEST = PREFIX + "SHA256SUMS.json"

SOURCE_BYTES = 9_975_622
SOURCE_SHA256 = "e87f5d13946138d9742848dff7420bb47b9bb11fe0a34b96904d44fa57a117ba"
EVIDENCE_BYTES = 62_799_249
EVIDENCE_SHA256 = "d155648c11394b9fef635b8bb6d08fc3686094fdd56ca79427e2adde9af01c46"

CRITICAL_SOURCE = {
    "ranking-v2/joined/main.cpp": {
        "bytes": 39_290,
        "sha256": "4e0c328d28e053d335328ac520cb21825601d9cabd9d0bba8015634d5919393d",
    },
    "ranking-v2/temporal_dp.hpp": {
        "bytes": 8_995,
        "sha256": "a9db8fc26acc6f4127640f306dd12ff61a2726e5b5edc5b4c53d1fb6225fca8b",
    },
}


class VerificationError(ValueError):
    """The supplied archive differs from its recovered, manifested identity."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _records(document: Any, records_field: str | None) -> Mapping[str, Any]:
    records = document.get(records_field) if records_field else document
    if not isinstance(records, dict) or not records:
        raise VerificationError("manifest does not contain a nonempty record map")
    return records


def _meta(record: Any) -> tuple[int | None, str]:
    if isinstance(record, str):
        return None, record
    if not isinstance(record, dict):
        raise VerificationError("manifest record must be an object or SHA-256 string")
    size = record.get("bytes")
    digest = record.get("sha256")
    if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
        raise VerificationError("manifest bytes must be a nonnegative integer")
    if not isinstance(digest, str) or len(digest) != 64:
        raise VerificationError("manifest sha256 must be a 64-character string")
    return size, digest


def verify_archive(
    path: Path,
    *,
    expected_bytes: int,
    expected_outer_sha256: str,
    manifest_member: str,
    records_field: str | None,
    allowed_extra_members: tuple[str, ...] = (),
    critical: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise VerificationError(f"archive not found: {path}")
    size = path.stat().st_size
    outer = sha256_file(path)
    if size != expected_bytes:
        raise VerificationError(f"outer byte count {size} != {expected_bytes}")
    if outer != expected_outer_sha256:
        raise VerificationError(f"outer sha256 {outer} != {expected_outer_sha256}")

    try:
        with ZipFile(path) as archive:
            corrupt = archive.testzip()
            if corrupt is not None:
                raise VerificationError(f"ZIP CRC failure at {corrupt}")
            try:
                document = json.loads(archive.read(manifest_member))
            except KeyError as exc:
                raise VerificationError(f"missing manifest {manifest_member}") from exc
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise VerificationError(f"invalid manifest {manifest_member}: {exc}") from exc
            records = _records(document, records_field)
            expected_members: set[str] = set()
            failures: list[dict[str, Any]] = []
            for relative, record in records.items():
                if not isinstance(relative, str) or not relative or relative.startswith("/"):
                    raise VerificationError("manifest contains an invalid relative path")
                member = relative if relative.startswith(PREFIX) else PREFIX + relative
                expected_members.add(member)
                try:
                    payload = archive.read(member)
                except KeyError:
                    failures.append({"member": member, "problem": "missing"})
                    continue
                expected_size, expected_digest = _meta(record)
                actual_digest = sha256_bytes(payload)
                if expected_size is not None and len(payload) != expected_size:
                    failures.append(
                        {
                            "member": member,
                            "problem": "bytes",
                            "expected": expected_size,
                            "actual": len(payload),
                        }
                    )
                if actual_digest != expected_digest:
                    failures.append(
                        {
                            "member": member,
                            "problem": "sha256",
                            "expected": expected_digest,
                            "actual": actual_digest,
                        }
                    )
            expected_members.add(manifest_member)
            expected_members.update(allowed_extra_members)
            actual_members = {name for name in archive.namelist() if not name.endswith("/")}
            missing = sorted(expected_members - actual_members)
            extra = sorted(actual_members - expected_members)
            if missing:
                failures.extend(
                    {"member": name, "problem": "missing archive member"}
                    for name in missing
                )
            if extra:
                failures.extend(
                    {"member": name, "problem": "unexpected archive member"}
                    for name in extra
                )

            critical_results: dict[str, Any] = {}
            for relative, record in (critical or {}).items():
                member = relative if relative.startswith(PREFIX) else PREFIX + relative
                try:
                    payload = archive.read(member)
                except KeyError:
                    failures.append({"member": member, "problem": "missing critical source"})
                    continue
                expected_size, expected_digest = _meta(record)
                actual_digest = sha256_bytes(payload)
                critical_results[relative] = {
                    "bytes": len(payload),
                    "sha256": actual_digest,
                }
                if expected_size is not None and len(payload) != expected_size:
                    failures.append({"member": member, "problem": "critical bytes"})
                if actual_digest != expected_digest:
                    failures.append({"member": member, "problem": "critical sha256"})

            if failures:
                raise VerificationError(json.dumps(failures[:20], sort_keys=True))
            return {
                "path": str(path),
                "bytes": size,
                "sha256": outer,
                "zip_integrity": "PASS",
                "manifest": manifest_member,
                "manifest_payloads": len(records),
                "archive_files": len(actual_members),
                "member_set": "EXACT",
                "critical_source": critical_results,
            }
    except BadZipFile as exc:
        raise VerificationError(f"invalid ZIP: {exc}") from exc


def verify_source(path: Path) -> dict[str, Any]:
    return verify_archive(
        path,
        expected_bytes=SOURCE_BYTES,
        expected_outer_sha256=SOURCE_SHA256,
        manifest_member=SOURCE_MANIFEST,
        records_field="files",
        allowed_extra_members=(SOURCE_NOTICE,),
        critical=CRITICAL_SOURCE,
    )


def verify_evidence(path: Path) -> dict[str, Any]:
    return verify_archive(
        path,
        expected_bytes=EVIDENCE_BYTES,
        expected_outer_sha256=EVIDENCE_SHA256,
        manifest_member=EVIDENCE_MANIFEST,
        records_field="files",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = {
            "schema": "roadef.dock-v2-archive-verification.v1",
            "ok": True,
            "source": verify_source(args.source),
            "evidence": verify_evidence(args.evidence),
            "solver_executed": False,
            "benchmark_rerun": False,
            "submission_changed": False,
        }
    except (OSError, VerificationError) as exc:
        result = {
            "schema": "roadef.dock-v2-archive-verification.v1",
            "ok": False,
            "error": str(exc),
        }
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    stream = sys.stdout if result["ok"] else sys.stderr
    stream.write(encoded)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

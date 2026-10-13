#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize the town-procurement survivorship arm from exact V5 production recovery."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import tarfile

BASELINE_ARCHIVE_SHA256 = "0aded66a2c393cc60f4f45d10f11c384a7e788182bf5430863829a02b66daf02"
BASELINE_CONFIG_SHA256 = "ba18563683125fd89d5473ddb8a5c3e9431db1787a3046f618a9e03af2cb44af"
TREATMENT_CONFIG_SHA256 = "70e849ebc9275250f474aa463b8f90862a7c224b10f9b2e91f8b78e04ad94463"
CONFIG_PATH = "TITAN-CONFIG.json"
SCHEMA = "titan-v5-production-recovery-town-survivorship/v1"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parse_archive_bytes(raw: bytes, expected_sha256: str) -> dict[str, bytes]:
    if type(raw) is not bytes:
        raise TypeError("archive snapshot must be bytes")
    actual = digest(raw)
    if actual != expected_sha256:
        raise ValueError(f"Archive identity mismatch: expected {expected_sha256}, got {actual}")
    result: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            name = member.name
            rel = PurePosixPath(name)
            if (
                not member.isfile()
                or not name
                or name in result
                or rel.is_absolute()
                or ".." in rel.parts
                or "\\" in name
                or str(rel) != name
            ):
                raise ValueError("Noncanonical archive member: " + name)
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("Missing archive member bytes: " + name)
            result[name] = stream.read()
    if not result:
        raise ValueError("Archive is empty")
    return result


def archive_members(path: Path) -> dict[str, bytes]:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Baseline must be an ordinary file: {path}")
    return parse_archive_bytes(path.read_bytes(), BASELINE_ARCHIVE_SHA256)


def archive_bytes(files: dict[str, bytes]) -> bytes:
    if not files:
        raise ValueError("Cannot create an empty archive")
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        for name, body in sorted(files.items()):
            rel = PurePosixPath(name)
            if (
                type(body) is not bytes
                or not name
                or rel.is_absolute()
                or ".." in rel.parts
                or "\\" in name
                or str(rel) != name
            ):
                raise ValueError("Noncanonical output member: " + str(name))
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(body))
    packed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=packed, mtime=0) as zipped:
        zipped.write(raw.getvalue())
    return packed.getvalue()


def treatment_members(baseline: dict[str, bytes]) -> dict[str, bytes]:
    if CONFIG_PATH not in baseline:
        raise ValueError("Baseline archive is missing TITAN-CONFIG.json")
    original = baseline[CONFIG_PATH]
    if digest(original) != BASELINE_CONFIG_SHA256:
        raise ValueError("Baseline config is not the exact production-recovery config")
    config = json.loads(original)
    if not isinstance(config, dict):
        raise ValueError("TITAN-CONFIG.json must contain a JSON object")
    if type(config.get("town_procurement")) is not bool or config["town_procurement"] is not True:
        raise ValueError("Baseline must have town_procurement=true")

    config["town_procurement"] = False
    changed = json.dumps(config, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    if digest(changed) != TREATMENT_CONFIG_SHA256:
        raise AssertionError("Town-off config bytes drifted from the authenticated treatment")

    treatment = dict(baseline)
    treatment[CONFIG_PATH] = changed
    if set(treatment) != set(baseline):
        raise AssertionError("Treatment changed archive membership")
    diffs = sorted(name for name in baseline if baseline[name] != treatment[name])
    if diffs != [CONFIG_PATH]:
        raise AssertionError(f"Treatment changed unexpected members: {diffs}")
    for name in baseline:
        if name != CONFIG_PATH and baseline[name] is not treatment[name] and baseline[name] != treatment[name]:
            raise AssertionError(f"Treatment changed retained member: {name}")
    return treatment


def receipt_for(baseline: dict[str, bytes], treatment: dict[str, bytes], packed: bytes) -> dict:
    if set(baseline) != set(treatment):
        raise ValueError("Receipt inputs have different member sets")
    changed = sorted(name for name in baseline if baseline[name] != treatment[name])
    if changed != [CONFIG_PATH]:
        raise ValueError(f"Unexpected treatment member delta: {changed}")
    return {
        "schema": SCHEMA,
        "baseline_archive_sha256": BASELINE_ARCHIVE_SHA256,
        "baseline_config_sha256": BASELINE_CONFIG_SHA256,
        "treatment": {
            "key": "town_procurement",
            "before": True,
            "after": False,
            "config_sha256": TREATMENT_CONFIG_SHA256,
            "archive_sha256": digest(packed),
        },
        "member_count": len(treatment),
        "changed_members": changed,
        "baseline_members": {name: digest(body) for name, body in sorted(baseline.items())},
        "treatment_members": {name: digest(body) for name, body in sorted(treatment.items())},
        "native_economics_status": "PENDING_BASE_PRODUCTION_PANEL",
        "kaggle_submission_hold": True,
    }


def _unlink_if_owned(path: Path, identity: tuple[int, int] | None) -> None:
    if identity is None:
        return
    try:
        stat = os.lstat(path)
    except FileNotFoundError:
        return
    if (stat.st_dev, stat.st_ino) == identity:
        os.unlink(path)


def _publish_pair(out_path: Path, packed: bytes, receipt_path: Path, receipt: dict) -> None:
    """Reserve both create-only destinations before publishing either payload."""
    out_path = Path(out_path)
    receipt_path = Path(receipt_path)
    if out_path == receipt_path:
        raise ValueError("Treatment and receipt paths must be different")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    out_fd = receipt_fd = None
    out_identity = receipt_identity = None
    try:
        out_fd = os.open(out_path, flags, 0o666)
        out_stat = os.fstat(out_fd)
        out_identity = (out_stat.st_dev, out_stat.st_ino)

        receipt_fd = os.open(receipt_path, flags, 0o666)
        receipt_stat = os.fstat(receipt_fd)
        receipt_identity = (receipt_stat.st_dev, receipt_stat.st_ino)

        with os.fdopen(out_fd, "wb") as stream:
            out_fd = None
            stream.write(packed)
            stream.flush()
            os.fsync(stream.fileno())

        with os.fdopen(receipt_fd, "w", encoding="utf-8") as stream:
            receipt_fd = None
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if out_fd is not None:
            os.close(out_fd)
        if receipt_fd is not None:
            os.close(receipt_fd)
        _unlink_if_owned(out_path, out_identity)
        _unlink_if_owned(receipt_path, receipt_identity)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    if args.out == args.receipt:
        parser.error("--out and --receipt must be different paths")
    if args.out.exists() or args.out.is_symlink() or args.receipt.exists() or args.receipt.is_symlink():
        parser.error("Use fresh --out and --receipt paths")

    baseline = archive_members(args.baseline)
    treatment = treatment_members(baseline)
    packed = archive_bytes(treatment)
    receipt = receipt_for(baseline, treatment, packed)

    try:
        _publish_pair(args.out, packed, args.receipt, receipt)
    except FileExistsError:
        parser.error("Use fresh --out and --receipt paths")

    print(json.dumps({
        "baseline_archive_sha256": BASELINE_ARCHIVE_SHA256,
        "treatment_archive_sha256": receipt["treatment"]["archive_sha256"],
        "treatment_config_sha256": TREATMENT_CONFIG_SHA256,
        "members": len(treatment),
        "changed_members": [CONFIG_PATH],
    }, sort_keys=True))


if __name__ == "__main__":
    main()

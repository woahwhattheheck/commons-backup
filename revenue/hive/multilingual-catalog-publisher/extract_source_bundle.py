#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify and extract the exact multilingual-catalog source bundle."""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_manifest(path: Path) -> dict:
    """Read the bundle schema without leaking JSON-shape errors as tracebacks."""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid bundle manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise SystemExit("invalid bundle manifest: expected an object")
    if manifest.get("schema") != "hive.multilingual-catalog-source-bundle.v1":
        raise SystemExit("unsupported bundle manifest schema")

    def byte_count(value: object, label: str) -> None:
        if type(value) is not int or value < 0:
            raise SystemExit(f"invalid bundle manifest: {label} must be a nonnegative integer")

    def sha256(value: object, label: str) -> None:
        if (not isinstance(value, str) or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)):
            raise SystemExit(f"invalid bundle manifest: {label} must be a lowercase SHA-256 hex digest")

    byte_count(manifest.get("archive_bytes"), "archive_bytes")
    sha256(manifest.get("archive_sha256"), "archive_sha256")
    for collection in ("parts", "members"):
        records = manifest.get(collection)
        if not isinstance(records, list):
            raise SystemExit(f"invalid bundle manifest: {collection} must be an array")
        for index, record in enumerate(records):
            label = f"{collection}[{index}]"
            if not isinstance(record, dict):
                raise SystemExit(f"invalid bundle manifest: {label} must be an object")
            if not isinstance(record.get("path"), str) or not record["path"]:
                raise SystemExit(f"invalid bundle manifest: {label}.path must be a nonempty string")
            byte_count(record.get("bytes"), f"{label}.bytes")
            sha256(record.get("sha256"), f"{label}.sha256")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--destination", type=Path, default=Path.cwd())
    args = parser.parse_args()

    root = args.bundle_dir.resolve()
    destination = args.destination.resolve()
    manifest = read_manifest(root / "BUNDLE.json")

    encoded = bytearray()
    for record in manifest["parts"]:
        path = root / record["path"]
        payload = path.read_bytes()
        if len(payload) != record["bytes"] or digest(payload) != record["sha256"]:
            raise SystemExit(f"bundle part mismatch: {record['path']}")
        encoded.extend(payload)
    try:
        archive = base64.b64decode(bytes(encoded), validate=True)
    except ValueError as exc:
        raise SystemExit(f"invalid base64 bundle: {exc}") from exc
    if len(archive) != manifest["archive_bytes"] or digest(archive) != manifest["archive_sha256"]:
        raise SystemExit("reconstructed archive does not match BUNDLE.json")

    expected = {record["path"]: record for record in manifest["members"]}
    prefix = PurePosixPath("revenue/hive/multilingual-catalog-publisher")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:xz") as package:
        files = []
        for member in package.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or member.issym() or member.islnk():
                raise SystemExit(f"unsafe archive member: {member.name}")
            try:
                relative = name.relative_to(prefix)
            except ValueError as exc:
                raise SystemExit(f"member is outside expected product root: {member.name}") from exc
            if member.isfile():
                files.append((member, relative.as_posix()))
        if {name for _, name in files} != set(expected):
            raise SystemExit("archive member set does not match BUNDLE.json")
        for member, relative in files:
            payload = package.extractfile(member)
            if payload is None:
                raise SystemExit(f"cannot read archive member: {member.name}")
            data = payload.read()
            record = expected[relative]
            if len(data) != record["bytes"] or digest(data) != record["sha256"]:
                raise SystemExit(f"archive member mismatch: {relative}")
            target = destination / prefix / relative
            if target.exists() or target.is_symlink():
                raise SystemExit(f"refusing to replace existing path: {target}")
        for member, relative in files:
            data = package.extractfile(member).read()
            target = destination / prefix / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                # Preflight is advisory: another extractor may create this path.
                with target.open("xb") as output:
                    output.write(data)
            except FileExistsError as exc:
                raise SystemExit(f"refusing to replace existing path: {target}") from exc
            target.chmod(member.mode & 0o777)

    print(json.dumps({
        "status": "extracted",
        "archive_sha256": manifest["archive_sha256"],
        "member_count": len(files),
        "destination": str(destination / prefix),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

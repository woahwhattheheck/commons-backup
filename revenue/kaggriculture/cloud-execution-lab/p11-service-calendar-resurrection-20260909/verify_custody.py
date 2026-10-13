#!/usr/bin/env python3
"""Fail-closed custody verifier for the P11 strict-field repair."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
MANIFEST = HERE / "MANIFEST.json"
RECEIPT = HERE / "CUSTODY-RECEIPT.json"


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def require_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path.name}: expected JSON object")
    return value


def main() -> int:
    manifest = require_object(MANIFEST)
    receipt = require_object(RECEIPT)
    if manifest.get("schema") != "titan-p11-service-calendar-manifest/v2":
        raise SystemExit("manifest schema mismatch")
    if manifest.get("repair_parent_head") != "23ceddf19ede39d1c7c872f80d71a1734d4b64a3":
        raise SystemExit("manifest parent-head mismatch")
    files = manifest.get("custody_files")
    if not isinstance(files, list) or not files:
        raise SystemExit("manifest custody_files missing")

    root = ROOT.resolve()
    seen: set[str] = set()
    for row in files:
        if not isinstance(row, dict) or set(row) not in ({"path", "git_blob_sha1"}, {"path", "sha256"}):
            raise SystemExit("invalid custody row")
        rel = row["path"]
        if not isinstance(rel, str) or not rel or rel in seen:
            raise SystemExit("invalid or duplicate custody path")
        seen.add(rel)
        raw_path = ROOT / rel
        if raw_path.is_symlink():
            raise SystemExit(f"custody path must not be a symlink: {rel}")
        try:
            path = raw_path.resolve(strict=True)
            path.relative_to(root)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"custody path is missing or escapes repository: {rel}") from exc
        if not path.is_file():
            raise SystemExit(f"custody path is not one regular file: {rel}")
        data = path.read_bytes()
        if "git_blob_sha1" in row:
            actual = git_blob_sha1(data)
            if actual != row["git_blob_sha1"]:
                raise SystemExit(f"git blob mismatch: {rel}: {actual}")
        else:
            actual = hashlib.sha256(data).hexdigest()
            if actual != row["sha256"]:
                raise SystemExit(f"sha256 mismatch: {rel}: {actual}")

    required_value = manifest.get("required_paths")
    if not isinstance(required_value, list) or any(not isinstance(item, str) for item in required_value):
        raise SystemExit("manifest required_paths must be a list of strings")
    required = set(required_value)
    if len(required) != len(required_value) or seen != required:
        raise SystemExit(f"custody path set mismatch: seen={sorted(seen)!r} required={sorted(required)!r}")

    manifest_blob = git_blob_sha1(MANIFEST.read_bytes())
    if receipt.get("schema") != "titan-p11-service-calendar-custody-receipt/v1":
        raise SystemExit("receipt schema mismatch")
    if receipt.get("manifest_git_blob_sha1") != manifest_blob:
        raise SystemExit("receipt does not bind this manifest")
    if receipt.get("repair_parent_head") != manifest["repair_parent_head"]:
        raise SystemExit("receipt parent-head mismatch")
    print(json.dumps({"custody": "PASS", "files": len(seen), "manifest_git_blob_sha1": manifest_blob}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

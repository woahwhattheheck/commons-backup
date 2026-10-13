"""Strict validation for commons-deliverable-manifest/v1 receipts."""
from __future__ import annotations

import hashlib
import json
import ntpath
from pathlib import PurePosixPath
from typing import Any

MANIFEST_SCHEMA = "commons-deliverable-manifest/v1"
HEX = frozenset("0123456789abcdef")


class ReplayError(ValueError):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canon(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise ReplayError(f"non-canonical JSON: {exc}") from exc


def _strict_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ReplayError(f"duplicate JSON key {key!r}")
        out[key] = value
    return out


def _load(raw: bytes):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReplayError("manifest is not UTF-8") from exc

    def reject_constant(value):
        raise ReplayError(f"non-finite JSON constant: {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=reject_constant,
        )
    except ReplayError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise ReplayError(f"invalid manifest JSON: {exc}") from exc


def normalize_path(raw: str, *, directory: bool = False) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        raise ReplayError(f"invalid archive path: {raw!r}")
    candidate = raw[:-1] if directory and raw.endswith("/") else raw
    drive, _ = ntpath.splitdrive(candidate)
    if drive or ntpath.isabs(candidate):
        raise ReplayError(f"Windows drive/rooted archive path: {raw!r}")
    path = PurePosixPath(candidate)
    if (
        not candidate
        or path.is_absolute()
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise ReplayError(f"non-canonical archive path: {raw!r}")
    rendered = path.as_posix() + ("/" if directory else "")
    if rendered != raw or "//" in raw:
        raise ReplayError(f"non-canonical archive path: {raw!r}")
    return path.as_posix()


def _valid_hash(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in HEX for ch in value)
    )


def validate_manifest(raw: bytes):
    doc = _load(raw)
    if not isinstance(doc, dict) or set(doc) != {
        "schema",
        "files",
        "acceptance",
        "manifest_sha256",
    }:
        raise ReplayError("invalid manifest top-level schema")
    if doc["schema"] != MANIFEST_SCHEMA or not _valid_hash(doc["manifest_sha256"]):
        raise ReplayError("invalid manifest schema or digest")

    payload = {key: doc[key] for key in ("schema", "files", "acceptance")}
    if _sha(_canon(payload)) != doc["manifest_sha256"]:
        raise ReplayError("manifest payload digest mismatch")

    rows = doc["files"]
    if not isinstance(rows, list) or not rows:
        raise ReplayError("manifest files must be non-empty")
    seen = set()
    folded = {}
    normalized_rows = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "bytes", "sha256"}:
            raise ReplayError("invalid manifest file row")
        rel = normalize_path(row["path"])
        fold = rel.casefold()
        if rel in seen:
            raise ReplayError(f"duplicate manifest file path: {rel}")
        if fold in folded and folded[fold] != rel:
            raise ReplayError("case-fold ambiguous manifest paths")
        size = row["bytes"]
        digest = row["sha256"]
        if (
            isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
            or not _valid_hash(digest)
        ):
            raise ReplayError(f"invalid manifest file metadata: {rel}")
        seen.add(rel)
        folded[fold] = rel
        normalized_rows.append({"path": rel, "bytes": size, "sha256": digest})
    if normalized_rows != sorted(normalized_rows, key=lambda row: row["path"]):
        raise ReplayError("manifest file rows are not canonical")

    acceptance = doc["acceptance"]
    if not isinstance(acceptance, list) or not acceptance:
        raise ReplayError("manifest acceptance must be non-empty")
    ids = set()
    normalized_acceptance = []
    for item in acceptance:
        if not isinstance(item, dict) or set(item) != {"id", "description", "paths"}:
            raise ReplayError("invalid manifest acceptance row")
        criterion_id = item["id"]
        description = item["description"]
        paths = item["paths"]
        if (
            not isinstance(criterion_id, str)
            or not criterion_id.strip()
            or criterion_id != criterion_id.strip()
            or criterion_id in ids
        ):
            raise ReplayError("invalid or duplicate manifest acceptance id")
        if (
            not isinstance(description, str)
            or not description.strip()
            or description != description.strip()
        ):
            raise ReplayError("invalid manifest acceptance description")
        if not isinstance(paths, list) or not paths:
            raise ReplayError("manifest acceptance paths must be non-empty")
        ids.add(criterion_id)
        local = set()
        clean_paths = []
        for raw_path in paths:
            rel = normalize_path(raw_path)
            if rel in local:
                raise ReplayError("manifest acceptance repeats path")
            if rel not in seen:
                raise ReplayError("manifest acceptance references absent file")
            local.add(rel)
            clean_paths.append(rel)
        if clean_paths != sorted(clean_paths):
            raise ReplayError("manifest acceptance paths are not canonical")
        normalized_acceptance.append(
            {"id": criterion_id, "description": description, "paths": clean_paths}
        )
    if normalized_acceptance != sorted(
        normalized_acceptance, key=lambda item: item["id"]
    ):
        raise ReplayError("manifest acceptance rows are not canonical")
    return doc, normalized_rows

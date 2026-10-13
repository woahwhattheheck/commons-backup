# SPDX-License-Identifier: Apache-2.0
"""Deterministic closure for a TITAN package's embedded SOURCE.json.

The root SOURCE.json is metadata, not a runtime member.  Its ``runtime`` map
must describe every other regular package file exactly once by byte length and
SHA-256.  The manifest itself is deliberately excluded to avoid a self-hash
cycle.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any

SOURCE_NAME = "SOURCE.json"
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class SourceManifestError(ValueError):
    """Raised when package/source closure is malformed or false."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise SourceManifestError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_nonfinite_constant(value: str) -> None:
    raise SourceManifestError(f"non-finite JSON constant: {value}")


def _canonical_name(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise SourceManifestError(f"invalid package member name: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith("./") or path.as_posix() != value:
        raise SourceManifestError(f"non-canonical package member name: {value!r}")
    if any(part in ("", ".", "..") for part in path.parts):
        raise SourceManifestError(f"unsafe package member name: {value!r}")
    return value


def _bytes_map(files: Mapping[str, bytes | bytearray | memoryview]) -> dict[str, bytes]:
    if not isinstance(files, Mapping):
        raise SourceManifestError("files must be a mapping")
    out: dict[str, bytes] = {}
    for raw_name, raw_blob in files.items():
        name = _canonical_name(raw_name)
        if not isinstance(raw_blob, (bytes, bytearray, memoryview)):
            raise SourceManifestError(f"package member is not bytes: {name}")
        out[name] = bytes(raw_blob)
    if SOURCE_NAME not in out:
        raise SourceManifestError(f"missing root {SOURCE_NAME}")
    return out


def parse_source_manifest(blob: bytes) -> dict[str, Any]:
    if not isinstance(blob, bytes):
        raise SourceManifestError("SOURCE.json must be bytes")
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceManifestError("SOURCE.json is not UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
    except SourceManifestError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise SourceManifestError("SOURCE.json is not valid JSON") from exc
    if not isinstance(value, dict):
        raise SourceManifestError("SOURCE.json root must be an object")
    runtime = value.get("runtime")
    if not isinstance(runtime, dict):
        raise SourceManifestError("SOURCE.json.runtime must be an object")
    if SOURCE_NAME in runtime:
        raise SourceManifestError("SOURCE.json.runtime must exclude SOURCE.json")
    for raw_name, raw_entry in runtime.items():
        name = _canonical_name(raw_name)
        if name != raw_name or not isinstance(raw_entry, dict):
            raise SourceManifestError(f"invalid runtime entry: {raw_name!r}")
        size = raw_entry.get("bytes")
        digest = raw_entry.get("sha256")
        source_path = raw_entry.get("source_path")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise SourceManifestError(f"invalid runtime byte count: {name}")
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise SourceManifestError(f"invalid runtime SHA-256: {name}")
        if not isinstance(source_path, str) or not source_path:
            raise SourceManifestError(f"invalid runtime source_path: {name}")
    return value


def refresh_source_manifest(
    files: Mapping[str, bytes | bytearray | memoryview],
    *,
    source_paths: Mapping[str, str] | None = None,
) -> bytes:
    """Return deterministic SOURCE.json bytes closed over final package bytes.

    Non-runtime metadata is preserved exactly as parsed.  Existing source labels
    survive; a new member defaults to its package-relative path unless an
    explicit source label is supplied.
    """
    package = _bytes_map(files)
    manifest = parse_source_manifest(package[SOURCE_NAME])
    old_runtime = manifest["runtime"]
    if source_paths is not None and not isinstance(source_paths, Mapping):
        raise SourceManifestError("source_paths must be a mapping")
    labels: dict[str, str] = {}
    for raw_name, raw_label in (source_paths or {}).items():
        name = _canonical_name(raw_name)
        if not isinstance(raw_label, str) or not raw_label:
            raise SourceManifestError(f"invalid source label: {name}")
        labels[name] = raw_label
    unknown_labels = sorted(set(labels) - (set(package) - {SOURCE_NAME}))
    if unknown_labels:
        raise SourceManifestError(f"source labels name absent package members: {unknown_labels}")

    runtime: dict[str, dict[str, Any]] = {}
    for name in sorted(set(package) - {SOURCE_NAME}):
        blob = package[name]
        old = old_runtime.get(name)
        source_path = labels.get(name)
        if source_path is None and isinstance(old, dict):
            source_path = old.get("source_path")
        if source_path is None:
            source_path = name
        if not isinstance(source_path, str) or not source_path:
            raise SourceManifestError(f"invalid source label: {name}")
        runtime[name] = {
            "bytes": len(blob),
            "sha256": sha256_bytes(blob),
            "source_path": source_path,
        }
    manifest["runtime"] = runtime
    try:
        encoded = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise SourceManifestError("SOURCE.json contains non-JSON metadata") from exc
    return encoded.encode("utf-8")


def verify_source_manifest(
    files: Mapping[str, bytes | bytearray | memoryview],
) -> dict[str, Any]:
    """Fail closed unless SOURCE.json exactly describes every other member."""
    package = _bytes_map(files)
    manifest = parse_source_manifest(package[SOURCE_NAME])
    runtime = manifest["runtime"]
    expected_names = set(package) - {SOURCE_NAME}
    actual_names = set(runtime)
    missing = sorted(expected_names - actual_names)
    extra = sorted(actual_names - expected_names)
    mismatches: list[dict[str, Any]] = []
    for name in sorted(expected_names & actual_names):
        blob = package[name]
        entry = runtime[name]
        expected_size = len(blob)
        expected_digest = sha256_bytes(blob)
        if entry["bytes"] != expected_size or entry["sha256"] != expected_digest:
            mismatches.append(
                {
                    "path": name,
                    "manifest_bytes": entry["bytes"],
                    "actual_bytes": expected_size,
                    "manifest_sha256": entry["sha256"],
                    "actual_sha256": expected_digest,
                }
            )
    if missing or extra or mismatches:
        raise SourceManifestError(
            "SOURCE.json runtime closure mismatch: "
            f"missing={missing}, extra={extra}, mismatches={mismatches}"
        )
    return {
        "source_sha256": sha256_bytes(package[SOURCE_NAME]),
        "runtime_files": len(runtime),
        "regular_files": len(package),
        "runtime_names_sha256": sha256_bytes(
            ("\n".join(sorted(runtime)) + "\n").encode("utf-8")
        ),
    }

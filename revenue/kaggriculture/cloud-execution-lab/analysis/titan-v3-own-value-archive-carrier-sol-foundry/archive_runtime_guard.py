# SPDX-License-Identifier: Apache-2.0
"""Runtime-side verification for materialized TITAN archive carriers.

This module is copied beside a generated control or candidate entrypoint.  It
validates the complete canonical runtime closure before any policy module is
imported.  The evaluator fingerprints the generated entrypoint separately;
this guard binds every archive member and every declared carrier support file.
"""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


class ArchiveRuntimeGuardError(RuntimeError):
    """The materialized runtime no longer matches its bound source manifest."""


def _strict_json_bytes(data: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ArchiveRuntimeGuardError(f"{label} has duplicate key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> Any:
        raise ArchiveRuntimeGuardError(f"{label} contains non-finite JSON constant {value}")

    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchiveRuntimeGuardError(f"{label} is not strict UTF-8 JSON: {exc}") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ArchiveRuntimeGuardError(f"{label} is not a canonical archive path")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or any(part in ("", ".", "..") for part in path.parts):
        raise ArchiveRuntimeGuardError(f"{label} is not a canonical archive path")
    return value


def _true_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ArchiveRuntimeGuardError(f"{label} must be an integer >= {minimum}")
    return value


def _hex_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ArchiveRuntimeGuardError(f"{label} must be a SHA-256 hex digest")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ArchiveRuntimeGuardError(f"{label} must be a SHA-256 hex digest") from exc
    return value.lower()


def _runtime_rows(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    runtime = source.get("runtime")
    if not isinstance(runtime, dict) or not runtime:
        raise ArchiveRuntimeGuardError("SOURCE.json runtime map is missing or empty")
    rows: list[dict[str, Any]] = []
    for raw_name in sorted(runtime):
        name = _canonical_name(raw_name, "SOURCE.json runtime member")
        record = runtime[raw_name]
        if not isinstance(record, dict):
            raise ArchiveRuntimeGuardError(f"runtime record for {name!r} must be an object")
        rows.append(
            {
                "name": name,
                "bytes": _true_int(record.get("bytes"), f"runtime[{name!r}].bytes"),
                "sha256": _hex_digest(record.get("sha256"), f"runtime[{name!r}].sha256"),
            }
        )
    return rows


def runtime_tree_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    """Hash the canonical name/size/digest ledger for the runtime file set."""
    normalized = [
        {
            "name": _canonical_name(row.get("name"), "runtime row name"),
            "bytes": _true_int(row.get("bytes"), "runtime row bytes"),
            "sha256": _hex_digest(row.get("sha256"), "runtime row sha256"),
        }
        for row in rows
    ]
    if [row["name"] for row in normalized] != sorted(row["name"] for row in normalized):
        normalized.sort(key=lambda row: row["name"])
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return _sha256(payload)


def _inventory(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ArchiveRuntimeGuardError(f"materialized carrier contains symlink: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ArchiveRuntimeGuardError(f"materialized carrier contains non-file: {path}")
        name = path.relative_to(root).as_posix()
        _canonical_name(name, "materialized carrier path")
        if name in files:
            raise ArchiveRuntimeGuardError(f"materialized carrier duplicates path: {name}")
        files[name] = path
    return files


def guard_runtime(
    root: Path,
    *,
    expected_source_sha256: str,
    expected_runtime_tree_sha256: str,
    extra_sha256: Mapping[str, str],
    entry_name: str,
) -> dict[str, Any]:
    """Verify the complete canonical closure and declared carrier extras.

    ``entry_name`` is permitted in the root but is fingerprinted by the parent
    evaluator and later reconciled against the materializer receipt.  Every
    other non-canonical file must have an exact SHA-256 supplied here.
    """
    root = Path(root).resolve(strict=True)
    expected_source_sha256 = _hex_digest(expected_source_sha256, "expected source SHA-256")
    expected_runtime_tree_sha256 = _hex_digest(
        expected_runtime_tree_sha256, "expected runtime tree SHA-256"
    )
    entry_name = _canonical_name(entry_name, "entrypoint name")
    normalized_extras = {
        _canonical_name(name, "carrier extra name"): _hex_digest(digest, f"extra {name!r} SHA-256")
        for name, digest in extra_sha256.items()
    }
    if entry_name in normalized_extras:
        raise ArchiveRuntimeGuardError("entrypoint must not be duplicated in extra_sha256")

    source_path = root / "SOURCE.json"
    try:
        source_bytes = source_path.read_bytes()
    except OSError as exc:
        raise ArchiveRuntimeGuardError(f"cannot read SOURCE.json: {exc}") from exc
    actual_source_sha256 = _sha256(source_bytes)
    if actual_source_sha256 != expected_source_sha256:
        raise ArchiveRuntimeGuardError(
            f"SOURCE.json drift: expected {expected_source_sha256}, got {actual_source_sha256}"
        )
    source = _strict_json_bytes(source_bytes, "SOURCE.json")
    if not isinstance(source, dict):
        raise ArchiveRuntimeGuardError("SOURCE.json root must be an object")
    rows = _runtime_rows(source)
    actual_tree_sha256 = runtime_tree_sha256(rows)
    if actual_tree_sha256 != expected_runtime_tree_sha256:
        raise ArchiveRuntimeGuardError(
            "runtime ledger drift: "
            f"expected {expected_runtime_tree_sha256}, got {actual_tree_sha256}"
        )

    inventory = _inventory(root)
    runtime_names = {row["name"] for row in rows}
    expected_names = runtime_names | {"SOURCE.json", entry_name} | set(normalized_extras)
    actual_names = set(inventory)
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        raise ArchiveRuntimeGuardError(
            f"materialized file-set drift: missing={missing!r}, unexpected={unexpected!r}"
        )

    verified_rows: list[dict[str, Any]] = []
    for row in rows:
        path = inventory[row["name"]]
        data = path.read_bytes()
        actual_size = len(data)
        actual_digest = _sha256(data)
        if actual_size != row["bytes"] or actual_digest != row["sha256"]:
            raise ArchiveRuntimeGuardError(
                f"runtime member drift: {row['name']}; "
                f"expected bytes/sha256 {row['bytes']}/{row['sha256']}, "
                f"got {actual_size}/{actual_digest}"
            )
        verified_rows.append(row)

    for name, expected_digest in normalized_extras.items():
        actual_digest = _sha256(inventory[name].read_bytes())
        if actual_digest != expected_digest:
            raise ArchiveRuntimeGuardError(
                f"carrier support file drift: {name}; expected {expected_digest}, got {actual_digest}"
            )

    return {
        "schema_version": 1,
        "source_sha256": actual_source_sha256,
        "runtime_tree_sha256": actual_tree_sha256,
        "runtime_files": len(verified_rows),
        "entry_name": entry_name,
        "extra_sha256": dict(sorted(normalized_extras.items())),
        "file_set_complete": True,
    }


def reject_foreign_modules(root: Path, names: Sequence[str]) -> None:
    """Reject same-named modules already loaded from outside this private root."""
    import sys

    root = Path(root).resolve(strict=True)
    for name in names:
        module = sys.modules.get(name)
        if module is None:
            continue
        raw = getattr(module, "__file__", None)
        if not isinstance(raw, str):
            raise ArchiveRuntimeGuardError(f"preloaded module {name!r} has no file origin")
        origin = Path(raw).resolve(strict=True)
        if not origin.is_relative_to(root):
            raise ArchiveRuntimeGuardError(
                f"preloaded module {name!r} escaped carrier root: {origin}"
            )


def module_origins(root: Path, names: Sequence[str]) -> dict[str, str]:
    """Import required root modules and prove every origin remains in the arena."""
    root = Path(root).resolve(strict=True)
    origins: dict[str, str] = {}
    for name in names:
        if not isinstance(name, str) or not name or "." in name:
            raise ArchiveRuntimeGuardError(f"invalid required root module name: {name!r}")
        module = importlib.import_module(name)
        raw = getattr(module, "__file__", None)
        if not isinstance(raw, str):
            raise ArchiveRuntimeGuardError(f"required module {name!r} has no file origin")
        origin = Path(raw).resolve(strict=True)
        if not origin.is_relative_to(root):
            raise ArchiveRuntimeGuardError(
                f"required module {name!r} escaped carrier root: {origin}"
            )
        origins[name] = origin.relative_to(root).as_posix()
    return origins

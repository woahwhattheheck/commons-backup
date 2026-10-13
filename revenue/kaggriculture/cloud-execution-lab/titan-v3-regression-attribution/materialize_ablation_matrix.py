#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize the canonical seven-arm TITAN V3 current-source ablation matrix.

This tool turns one fully enabled TITAN config and one immutable source closure
into seven deterministic config artifacts:

* every suspect feature disabled (neutral anchor),
* each suspect feature enabled alone, and
* every suspect feature enabled (full current behavior).

The output directory is published atomically and includes exact SHA-256 receipts
plus the neutral-anchored comparison graph consumed by regression_attribution.py.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any, Mapping, Sequence


MAX_CONFIG_BYTES = 4 * 1024 * 1024
MAX_CLOSURE_BYTES = 1024 * 1024 * 1024
_HEX = frozenset("0123456789abcdef")
_MATRIX_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

SUSPECT_FLAGS: tuple[str, ...] = (
    "market_pressure",
    "operating_stock",
    "idle_fertilizer",
    "crop_release",
    "early_capital",
)

ARM_SPECS: tuple[tuple[str, frozenset[str]], ...] = (
    ("neutral-current-source", frozenset()),
    ("market-pressure-only", frozenset({"market_pressure"})),
    ("operating-stock-only", frozenset({"operating_stock"})),
    ("idle-fertilizer-only", frozenset({"idle_fertilizer"})),
    ("crop-release-only", frozenset({"crop_release"})),
    ("early-capital-only", frozenset({"early_capital"})),
    ("full-current", frozenset(SUSPECT_FLAGS)),
)


class MatrixError(ValueError):
    """Raised when the requested matrix cannot be materialized safely."""


def _reject_constant(value: str) -> None:
    raise MatrixError(f"non-finite JSON constant is forbidden: {value}")


def _pairs_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MatrixError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _loads_json(data: bytes, label: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MatrixError(f"{label}: input is not UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise MatrixError(f"{label}: invalid JSON: {exc}") from exc


def _canonical_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MatrixError(f"value is not canonical JSON: {exc}") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hex(value: str, length: int, label: str) -> str:
    text = value.strip().lower()
    if len(text) != length or any(character not in _HEX for character in text):
        raise MatrixError(f"{label}: expected {length} hexadecimal characters")
    return text


def _commit(value: str) -> str:
    text = value.strip().lower()
    if len(text) not in (40, 64) or any(character not in _HEX for character in text):
        raise MatrixError("source_commit: expected a 40- or 64-character hexadecimal commit")
    return text


def _read_regular_file(path: Path, label: str, max_bytes: int) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise MatrixError(f"{label}: cannot open regular non-symlink file {path}: {exc}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise MatrixError(f"{label}: input is not a regular file: {path}")
        if info.st_size > max_bytes:
            raise MatrixError(f"{label}: input exceeds {max_bytes} bytes")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_bytes:
            raise MatrixError(f"{label}: input exceeds {max_bytes} bytes")
        return data
    finally:
        os.close(fd)



def _hash_regular_file(path: Path, label: str, max_bytes: int) -> tuple[str, int]:
    """Hash a regular non-symlink file without loading the closure into memory."""
    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise MatrixError(f"{label}: cannot open regular non-symlink file {path}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise MatrixError(f"{label}: input is not a regular file: {path}")
        if before.st_size > max_bytes:
            raise MatrixError(f"{label}: input exceeds {max_bytes} bytes")
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise MatrixError(f"{label}: input exceeds {max_bytes} bytes")
            digest.update(chunk)
        after = os.fstat(fd)
        stable_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            getattr(before, "st_mtime_ns", None),
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_size,
            getattr(after, "st_mtime_ns", None),
        )
        if not stable_identity or total != before.st_size:
            raise MatrixError(f"{label}: input changed while it was being hashed")
        return digest.hexdigest(), total
    finally:
        os.close(fd)

def _validate_json_tree(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MatrixError(f"{path}: non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_tree(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise MatrixError(f"{path}: object key is not a string")
            _validate_json_tree(item, f"{path}.{key}")
        return
    raise MatrixError(f"{path}: unsupported JSON value type {type(value).__name__}")


def _validate_base_config(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MatrixError("base_config: expected a JSON object")
    config = dict(value)
    _validate_json_tree(config)
    for flag in SUSPECT_FLAGS:
        if flag not in config:
            raise MatrixError(f"base_config: missing suspect flag {flag!r}")
        if not isinstance(config[flag], bool):
            raise MatrixError(f"base_config.{flag}: expected a boolean")
        if config[flag] is not True:
            raise MatrixError(
                f"base_config.{flag}: expected true; this experiment starts from the fully enabled current config"
            )
    return config


def _diff_paths(before: Any, after: Any, prefix: str = "$") -> list[str]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        paths: list[str] = []
        for key in sorted(set(before) | set(after)):
            child = f"{prefix}.{key}"
            if key not in before or key not in after:
                paths.append(child)
            else:
                paths.extend(_diff_paths(before[key], after[key], child))
        return paths
    if isinstance(before, list) and isinstance(after, list):
        paths = []
        for index in range(max(len(before), len(after))):
            child = f"{prefix}[{index}]"
            if index >= len(before) or index >= len(after):
                paths.append(child)
            else:
                paths.extend(_diff_paths(before[index], after[index], child))
        return paths
    return [] if before == after and type(before) is type(after) else [prefix]


def _arm_config(base: Mapping[str, Any], enabled: frozenset[str]) -> dict[str, Any]:
    config = deepcopy(dict(base))
    for flag in SUSPECT_FLAGS:
        config[flag] = flag in enabled
    return config


def _assert_arm_contract(
    base: Mapping[str, Any],
    neutral: Mapping[str, Any],
    arm: Mapping[str, Any],
    enabled: frozenset[str],
    arm_name: str,
) -> None:
    expected_from_base = sorted(
        f"$.{flag}" for flag in SUSPECT_FLAGS if (flag in enabled) is not True
    )
    actual_from_base = _diff_paths(base, arm)
    if actual_from_base != expected_from_base:
        raise MatrixError(
            f"{arm_name}: source diff contract failed; expected={expected_from_base}, actual={actual_from_base}"
        )

    expected_from_neutral = sorted(f"$.{flag}" for flag in enabled)
    actual_from_neutral = _diff_paths(neutral, arm)
    if actual_from_neutral != expected_from_neutral:
        raise MatrixError(
            f"{arm_name}: neutral diff contract failed; expected={expected_from_neutral}, actual={actual_from_neutral}"
        )


def _safe_parent(path: Path) -> Path:
    parent = path.parent if path.parent != Path("") else Path(".")
    try:
        info = parent.lstat()
    except OSError as exc:
        raise MatrixError(f"output_dir parent cannot be inspected: {parent}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise MatrixError(f"output_dir parent must be a real directory, not a symlink: {parent}")
    return parent


def _exclusive_write(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o644)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(fd, data[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)


def materialize_matrix(
    *,
    base_config_path: Path,
    source_closure_path: Path,
    source_commit: str,
    output_dir: Path,
    matrix_id: str | None = None,
    expected_source_closure_sha256: str | None = None,
) -> dict[str, Any]:
    """Build and atomically publish a deterministic seven-arm matrix."""
    commit = _commit(source_commit)
    config_data = _read_regular_file(base_config_path, "base_config", MAX_CONFIG_BYTES)
    closure_sha, closure_bytes = _hash_regular_file(
        source_closure_path, "source_closure", MAX_CLOSURE_BYTES
    )
    if expected_source_closure_sha256 is not None:
        expected = _hex(expected_source_closure_sha256, 64, "expected_source_closure_sha256")
        if closure_sha != expected:
            raise MatrixError(
                f"source_closure: SHA-256 mismatch; expected={expected}, actual={closure_sha}"
            )

    base = _validate_base_config(_loads_json(config_data, "base_config"))
    base_sha = _sha256(config_data)
    resolved_id = matrix_id or f"titan-v3-current-source-ablation-{closure_sha[:12]}"
    if not _MATRIX_ID.fullmatch(resolved_id):
        raise MatrixError("matrix_id: use 1-128 ASCII letters, digits, dot, underscore, or hyphen")

    neutral = _arm_config(base, frozenset())
    arm_payloads: list[tuple[str, frozenset[str], str, bytes, dict[str, Any]]] = []
    for index, (arm_name, enabled) in enumerate(ARM_SPECS):
        arm = _arm_config(base, enabled)
        _assert_arm_contract(base, neutral, arm, enabled, arm_name)
        filename = f"{index:02d}-{arm_name}.json"
        data = _canonical_bytes(arm)
        arm_payloads.append((arm_name, enabled, filename, data, arm))

    hashes = [_sha256(item[3]) for item in arm_payloads]
    if len(set(hashes)) != len(hashes):
        raise MatrixError("arm configs are not byte-distinct")

    comparisons = [
        {
            "id": f"neutral-vs-{arm_name}",
            "before": "neutral-current-source",
            "after": arm_name,
        }
        for arm_name, _enabled, _filename, _data, _arm in arm_payloads[1:]
    ]

    arms: list[dict[str, Any]] = []
    for arm_name, enabled, filename, data, arm in arm_payloads:
        arms.append(
            {
                "name": arm_name,
                "config_path": filename,
                "config_sha256": _sha256(data),
                "config_bytes": len(data),
                "enabled_suspect_flags": sorted(enabled),
                "disabled_suspect_flags": sorted(set(SUSPECT_FLAGS) - set(enabled)),
                "changed_paths_from_source": _diff_paths(base, arm),
                "changed_paths_from_neutral": _diff_paths(neutral, arm),
            }
        )

    non_suspect = {key: value for key, value in base.items() if key not in SUSPECT_FLAGS}
    manifest = {
        "schema_version": 1,
        "matrix_id": resolved_id,
        "source_identity": {
            "source_commit": commit,
            "source_closure_sha256": closure_sha,
            "source_closure_bytes": closure_bytes,
            "input_config_sha256": base_sha,
            "input_config_bytes": len(config_data),
            "non_suspect_config_sha256": _sha256(_canonical_bytes(non_suspect)),
        },
        "suspect_flags": list(SUSPECT_FLAGS),
        "arms": arms,
        "comparisons": comparisons,
        "execution_contract": {
            "same_source_commit_for_every_arm": True,
            "same_source_closure_sha256_for_every_arm": True,
            "compare_each_non_neutral_arm_directly_to_neutral": True,
            "build_complete_executable_closure_per_arm": True,
            "require_byte_distinct_executable_closures": True,
            "promotion_authority": "titan-v3-paired-game-gate/dual_predecessor_gate.py",
        },
    }
    manifest_data = _canonical_bytes(manifest)

    if os.path.lexists(output_dir):
        raise MatrixError(f"output_dir already exists: {output_dir}")
    parent = _safe_parent(output_dir)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=parent))
    published = False
    try:
        for _arm_name, _enabled, filename, data, _arm in arm_payloads:
            _exclusive_write(temporary / filename, data)
        _exclusive_write(temporary / "ABLATION-MATRIX.json", manifest_data)
        directory_fd = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        os.replace(temporary, output_dir)
        published = True
        parent_fd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except OSError as exc:
        raise MatrixError(f"cannot publish output_dir atomically: {exc}") from exc
    finally:
        if not published:
            shutil.rmtree(temporary, ignore_errors=True)

    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", required=True, type=Path)
    parser.add_argument("--source-closure", required=True, type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--matrix-id")
    parser.add_argument("--expected-source-closure-sha256")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = materialize_matrix(
            base_config_path=args.base_config,
            source_closure_path=args.source_closure,
            source_commit=args.source_commit,
            output_dir=args.output_dir,
            matrix_id=args.matrix_id,
            expected_source_closure_sha256=args.expected_source_closure_sha256,
        )
    except MatrixError as exc:
        print(f"INVALID: {exc}", file=os.sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "MATERIALIZED",
                "matrix_id": manifest["matrix_id"],
                "arms": len(manifest["arms"]),
                "comparisons": len(manifest["comparisons"]),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

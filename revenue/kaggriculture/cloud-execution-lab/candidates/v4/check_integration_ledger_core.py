#!/usr/bin/env python3
"""Fail closed on stale or contradictory TITAN V4 integration custody.

This is coordination/tooling only.  It does not import candidate gameplay, execute
legacy materializers, promote defaults, or decide economic gates.  It verifies
that CANONICAL.json, INTEGRATION.json, and raw-payload blocker manifests describe
one coherent main-line workspace.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
EXPECTED_SCHEMA = "titan-v4-integration-ledger/v1"
EXPECTED_WORKSPACE = "revenue/kaggriculture/cloud-execution-lab/candidates/v4"
BLOB_ID = re.compile(r"[0-9a-f]{40}\Z")


class LedgerError(RuntimeError):
    pass


class DuplicateJsonKey(ValueError):
    pass


class NonFiniteJson(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateJsonKey(f"duplicate JSON object key {key!r}")
        out[key] = value
    return out


def _reject_nonfinite(value: str) -> Any:
    raise NonFiniteJson(f"non-finite JSON constant {value!r}")


def _claims_activation(status: Any) -> bool:
    """Return True only for an unnegated activation/promote/enable status token."""
    if not isinstance(status, str):
        return False
    words = re.sub(r"[^a-z0-9]+", "_", status.casefold()).strip("_")
    words = re.sub(
        r"(?:^|_)not_(?:(?:runtime|production)_)?"
        r"(?:promoted|active|enabled|activated)(?=_|$)",
        "_",
        words,
    )
    return bool(
        re.search(r"(?:^|_)(?:promoted|active|enabled|activated)(?:_|$)", words)
    )


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_nonfinite,
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        DuplicateJsonKey,
        NonFiniteJson,
    ) as exc:
        raise LedgerError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LedgerError(f"{path} must contain a JSON object")
    return value


def _rows(ledger: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = ledger.get(key)
    if not isinstance(value, list):
        raise LedgerError(f"INTEGRATION.json {key!r} must be a list")
    out: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise LedgerError(f"INTEGRATION.json {key}[{index}] must be an object")
        lane = row.get("lane")
        if not isinstance(lane, str) or not lane.strip():
            raise LedgerError(f"INTEGRATION.json {key}[{index}] has invalid lane")
        if lane != lane.strip():
            raise LedgerError(
                f"INTEGRATION.json {key}[{index}] lane must not have leading/trailing whitespace"
            )
        if lane in seen:
            raise LedgerError(
                f"INTEGRATION.json {key!r} duplicates lane {lane!r} "
                f"at indexes {seen[lane]} and {index}"
            )
        seen[lane] = index
        row = dict(row)
        out.append(row)
    return out


def _lane_set(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row["lane"]) for row in rows}


def _require_nonempty_text(
    row: dict[str, Any],
    lane: str,
    field: str,
    errors: list[str],
    *,
    label: str,
) -> None:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} lane {lane!r} lacks {field}")


_FILE_STABLE_FIELDS = (
    "st_dev",
    "st_ino",
    "st_mode",
    "st_nlink",
    "st_size",
    "st_mtime_ns",
    "st_ctime_ns",
)
_DIR_STABLE_FIELDS = (
    "st_dev",
    "st_ino",
    "st_mode",
    "st_nlink",
    "st_mtime_ns",
    "st_ctime_ns",
)


def _same_stat_generation(
    before: os.stat_result,
    after: os.stat_result,
    fields: tuple[str, ...],
) -> bool:
    return all(getattr(before, field) == getattr(after, field) for field in fields)


def _require_descriptor_relative_custody() -> None:
    """Fail closed unless this host supports safe descriptor-relative traversal."""

    supports_dir_fd = getattr(os, "supports_dir_fd", set())
    supports_fd = getattr(os, "supports_fd", set())
    supports_follow_symlinks = getattr(os, "supports_follow_symlinks", set())
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or os.open not in supports_dir_fd
        or os.stat not in supports_dir_fd
        or os.stat not in supports_follow_symlinks
        or os.listdir not in supports_fd
    ):
        raise LedgerError(
            "descriptor-relative custody traversal is unavailable on this platform"
        )


def _regular_git_blob_id_at(
    parent_fd: int,
    name: str,
    display_path: Path,
) -> str | None:
    """Hash one regular file without ever reopening its pathname ancestors."""

    try:
        pathname_before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise LedgerError(f"cannot inspect custody file {display_path}: {exc}") from exc
    if not stat.S_ISREG(pathname_before.st_mode):
        return None

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_NOFOLLOW
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise LedgerError(f"cannot open custody file {display_path}: {exc}") from exc

    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            return None
        if (opened.st_dev, opened.st_ino) != (
            pathname_before.st_dev,
            pathname_before.st_ino,
        ):
            raise LedgerError(f"custody file changed before read: {display_path}")

        # SHA-1 is required here only to reproduce Git's content-addressed blob ID.
        digest = hashlib.sha1()
        digest.update(f"blob {opened.st_size}\0".encode("ascii"))
        consumed = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            consumed += len(chunk)
        descriptor_after = os.fstat(descriptor)
        pathname_after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise LedgerError(f"cannot read custody file {display_path}: {exc}") from exc
    finally:
        os.close(descriptor)

    if (
        consumed != opened.st_size
        or not _same_stat_generation(opened, descriptor_after, _FILE_STABLE_FIELDS)
        or not _same_stat_generation(opened, pathname_after, _FILE_STABLE_FIELDS)
    ):
        raise LedgerError(f"custody file changed while hashing: {display_path}")
    return digest.hexdigest()


def _walk_custody_dir(
    directory_fd: int,
    display_path: Path,
    wanted: set[str],
    found: set[str],
) -> None:
    """Walk one retained directory descriptor without following namespace swaps."""

    try:
        names = sorted(os.listdir(directory_fd))
    except OSError as exc:
        raise LedgerError(f"cannot list custody directory {display_path}: {exc}") from exc

    for name in names:
        if found == wanted:
            return
        try:
            before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise LedgerError(
                f"cannot inspect custody entry {display_path / name}: {exc}"
            ) from exc

        entry_path = display_path / name
        if stat.S_ISREG(before.st_mode):
            blob_id = _regular_git_blob_id_at(directory_fd, name, entry_path)
            if blob_id in wanted:
                found.add(blob_id)
            continue
        if not stat.S_ISDIR(before.st_mode):
            continue

        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
        )
        try:
            child_fd = os.open(name, flags, dir_fd=directory_fd)
        except OSError as exc:
            raise LedgerError(
                f"cannot open custody directory {entry_path}: {exc}"
            ) from exc
        try:
            opened = os.fstat(child_fd)
            if not stat.S_ISDIR(opened.st_mode):
                raise LedgerError(f"custody entry is no longer a directory: {entry_path}")
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise LedgerError(f"custody directory changed before traversal: {entry_path}")

            _walk_custody_dir(child_fd, entry_path, wanted, found)

            descriptor_after = os.fstat(child_fd)
            pathname_after = os.stat(
                name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            if (
                not _same_stat_generation(opened, descriptor_after, _DIR_STABLE_FIELDS)
                or not _same_stat_generation(opened, pathname_after, _DIR_STABLE_FIELDS)
            ):
                raise LedgerError(
                    f"custody directory changed while traversing: {entry_path}"
                )
        except OSError as exc:
            raise LedgerError(
                f"cannot re-inspect custody directory {entry_path}: {exc}"
            ) from exc
        finally:
            os.close(child_fd)


def _custody_blob_ids(custody_dir: Path, wanted: set[str]) -> set[str]:
    """Resolve wanted Git blobs only through retained descriptor-relative custody."""

    _require_descriptor_relative_custody()
    try:
        pathname_before = custody_dir.stat(follow_symlinks=False)
    except OSError as exc:
        raise LedgerError(
            f"cannot inspect custody directory {custody_dir}: {exc}"
        ) from exc
    if not stat.S_ISDIR(pathname_before.st_mode):
        raise LedgerError(f"custody path is not a directory: {custody_dir}")

    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
    )
    try:
        root_fd = os.open(custody_dir, flags)
    except OSError as exc:
        raise LedgerError(f"cannot open custody directory {custody_dir}: {exc}") from exc

    found: set[str] = set()
    try:
        opened = os.fstat(root_fd)
        if not stat.S_ISDIR(opened.st_mode):
            raise LedgerError(f"custody path is no longer a directory: {custody_dir}")
        if (opened.st_dev, opened.st_ino) != (
            pathname_before.st_dev,
            pathname_before.st_ino,
        ):
            raise LedgerError(f"custody directory changed before traversal: {custody_dir}")

        _walk_custody_dir(root_fd, custody_dir, wanted, found)

        descriptor_after = os.fstat(root_fd)
        pathname_after = custody_dir.stat(follow_symlinks=False)
        if (
            not _same_stat_generation(opened, descriptor_after, _DIR_STABLE_FIELDS)
            or not _same_stat_generation(opened, pathname_after, _DIR_STABLE_FIELDS)
        ):
            raise LedgerError(
                f"custody directory changed while traversing: {custody_dir}"
            )
    except OSError as exc:
        raise LedgerError(
            f"cannot re-inspect custody directory {custody_dir}: {exc}"
        ) from exc
    finally:
        os.close(root_fd)
    return found


def _historical_gap_errors(
    row: dict[str, Any],
    landed: list[dict[str, Any]],
    custody_dir: Path,
) -> list[str]:
    """Bind a non-blocking historical gap to one current landed source package."""

    lane = str(row["lane"])
    custody_path = row.get("custody_path")
    matches = [item for item in landed if item.get("repair_path") == custody_path]
    if len(matches) != 1:
        return [
            f"historical evidence gap lane {lane!r} requires exactly one landed "
            "component in its custody_path"
        ]

    component = matches[0]
    errors: list[str] = []
    source_blob = component.get("source_blob")
    source_valid = isinstance(source_blob, str) and bool(BLOB_ID.fullmatch(source_blob))
    if not source_valid:
        errors.append(
            f"historical evidence gap lane {lane!r} landed component lacks a valid source_blob"
        )

    test_blobs = component.get("test_blobs")
    if test_blobs is None:
        test_blobs = [component.get("test_blob")]
    tests_valid = (
        isinstance(test_blobs, list)
        and bool(test_blobs)
        and all(
            isinstance(blob, str) and bool(BLOB_ID.fullmatch(blob))
            for blob in test_blobs
        )
    )
    if not tests_valid:
        errors.append(
            f"historical evidence gap lane {lane!r} landed component lacks valid test blob references"
        )

    wanted: set[str] = set()
    if source_valid:
        wanted.add(source_blob)
    if isinstance(test_blobs, list):
        wanted.update(
            blob
            for blob in test_blobs
            if isinstance(blob, str) and BLOB_ID.fullmatch(blob)
        )
    if not wanted:
        return errors

    try:
        present = _custody_blob_ids(custody_dir, wanted)
    except LedgerError as exc:
        errors.append(
            f"historical evidence gap lane {lane!r} cannot verify current custody bytes: {exc}"
        )
        return errors

    if source_valid and source_blob not in present:
        errors.append(
            f"historical evidence gap lane {lane!r} source_blob {source_blob!r} "
            "does not identify a regular file beneath custody_path"
        )
    if tests_valid:
        missing_tests = [blob for blob in test_blobs if blob not in present]
        for blob in missing_tests:
            errors.append(
                f"historical evidence gap lane {lane!r} test blob {blob!r} "
                "does not identify a regular file beneath custody_path"
            )
    return errors


def _resolve_within_root(root: Path, relative: str | Path, *, label: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise LedgerError(
            f"{label} must be relative to the integration root, got {str(candidate)!r}"
        )
    root_resolved = root.resolve()
    resolved = (root_resolved / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise LedgerError(f"{label} escapes integration root: {str(candidate)!r}") from exc
    return resolved


def validate(root: Path = HERE) -> list[str]:
    errors: list[str] = []
    try:
        canonical = _load(root / "CANONICAL.json")
        ledger = _load(root / "INTEGRATION.json")
    except LedgerError as exc:
        return [str(exc)]

    schema = ledger.get("schema")
    branch = ledger.get("canonical_branch")
    workspace = ledger.get("workspace")
    if schema != EXPECTED_SCHEMA:
        errors.append(f"schema must be {EXPECTED_SCHEMA!r}, got {schema!r}")
    if branch != "main":
        errors.append(f"canonical_branch must be 'main', got {branch!r}")
    if workspace != EXPECTED_WORKSPACE:
        errors.append(f"workspace must be {EXPECTED_WORKSPACE!r}, got {workspace!r}")
    if canonical.get("canonical_branch") != branch:
        errors.append("CANONICAL canonical_branch disagrees with INTEGRATION canonical_branch")
    if canonical.get("workspace") != workspace:
        errors.append("CANONICAL workspace disagrees with INTEGRATION workspace")

    try:
        landed = _rows(ledger, "landed")
        recovered = _rows(ledger, "recovered_not_yet_composed")
        blocked = _rows(ledger, "custody_blocked")
        negative = _rows(ledger, "negative_or_parked")
    except LedgerError as exc:
        errors.append(str(exc))
        return errors

    landed_lanes = _lane_set(landed)
    recovered_lanes = _lane_set(recovered)
    blocked_lanes = _lane_set(blocked)
    negative_lanes = _lane_set(negative)

    for label, overlap in (
        ("landed/recovered", landed_lanes & recovered_lanes),
        ("landed/blocked", landed_lanes & blocked_lanes),
        ("recovered/blocked", recovered_lanes & blocked_lanes),
        ("recovered/negative", recovered_lanes & negative_lanes),
        ("blocked/negative", blocked_lanes & negative_lanes),
    ):
        if overlap:
            errors.append(f"contradictory {label} lanes: {sorted(overlap)!r}")

    # A negative/parked lane may have historical custody elsewhere, but it must
    # never be represented as a newly recovered or raw-custody work item above.
    for row in negative:
        disposition = row.get("disposition")
        if not isinstance(disposition, str) or not disposition.strip():
            errors.append(f"negative/parked lane {row['lane']!r} lacks disposition")

    # Custody rows have two deliberately distinct contracts:
    #
    # * awaiting_raw_payload is a live source blocker.  The blocker directory and
    #   MANIFEST must exist and independently say that exact raw bytes are owed.
    # * historical_evidence_gap_not_source_blocker records missing archival
    #   receipts for a component whose exact current source/test custody already
    #   exists.  It must name what is available, what is missing, and what may be
    #   done if the history resurfaces, but it must NOT require an "awaiting"
    #   manifest or masquerade as a live source blocker.
    #
    # Custody paths and manifests are also trust inputs: both must resolve within
    # this exact V4 root.  A ../ path, absolute path, or symlink escape cannot make
    # external bytes satisfy source custody.
    for row in blocked:
        lane = str(row["lane"])
        custody_path = row.get("custody_path")
        status = row.get("status")

        if not isinstance(custody_path, str) or not custody_path.strip():
            errors.append(f"custody lane {lane!r} lacks custody_path")
            continue
        if custody_path != custody_path.strip():
            errors.append(
                f"custody lane {lane!r} custody_path must not have leading/trailing whitespace"
            )
            continue
        try:
            path = _resolve_within_root(
                root,
                custody_path,
                label=f"custody lane {lane!r} custody_path",
            )
        except LedgerError as exc:
            errors.append(str(exc))
            continue
        if not path.is_dir():
            errors.append(
                f"custody lane {lane!r} missing custody directory {custody_path!r}"
            )
            continue

        if status == "historical_evidence_gap_not_source_blocker":
            for field in ("available", "missing", "required"):
                _require_nonempty_text(
                    row,
                    lane,
                    field,
                    errors,
                    label="historical evidence gap",
                )
            errors.extend(_historical_gap_errors(row, landed, path))
            continue

        if status != "awaiting_raw_payload":
            errors.append(f"custody lane {lane!r} has unsupported status {status!r}")
            continue

        try:
            manifest_path = _resolve_within_root(
                root,
                Path(custody_path) / "MANIFEST.json",
                label=f"blocked lane {lane!r} MANIFEST.json",
            )
            manifest = _load(manifest_path)
        except LedgerError as exc:
            errors.append(str(exc))
            continue
        if manifest.get("lane") != lane:
            errors.append(
                f"blocked lane {lane!r} disagrees with {custody_path}/MANIFEST.json lane "
                f"{manifest.get('lane')!r}"
            )
        if manifest.get("status") != "awaiting_raw_payload":
            errors.append(
                f"blocked lane {lane!r} manifest status is {manifest.get('status')!r}, "
                "expected 'awaiting_raw_payload'"
            )
        required = manifest.get("required_next_step")
        if not isinstance(required, str) or not required.strip():
            errors.append(f"blocked lane {lane!r} manifest lacks required_next_step")

    # Prevent the most dangerous stale-ledger regression: a lane explicitly
    # retired/NO_BUILD must not simultaneously masquerade as active landed work.
    active_landed = {
        str(row["lane"])
        for row in landed
        if _claims_activation(row.get("status"))
    }
    for lane in sorted(active_landed & negative_lanes):
        disposition = next(
            str(row.get("disposition", ""))
            for row in negative
            if row["lane"] == lane
        ).lower()
        if (
            "no_build" in disposition
            or "rejected" in disposition
            or "do_not_promote" in disposition
            or ("do_not_" in disposition and "activate" in disposition)
        ):
            errors.append(
                f"retired/NO_BUILD lane {lane!r} is also represented as active landed work"
            )

    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"TITAN V4 integration ledger INVALID ({len(errors)} error(s))",
            file=sys.stderr,
        )
        return 1
    print("TITAN V4 integration ledger OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

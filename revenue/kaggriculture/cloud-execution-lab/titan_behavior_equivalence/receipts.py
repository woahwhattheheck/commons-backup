# SPDX-License-Identifier: Apache-2.0
"""Deterministic report rendering and tamper-evident receipt chaining."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterator, Mapping

from .core import (
    BehaviorGateError,
    LEDGER_ENTRY_SCHEMA,
    PREFLIGHT_SCHEMA,
    ZERO_SHA256,
    _mapping,
    _nonempty_string,
    _nonnegative_int,
    _sha256,
    canonical_bytes,
    loads_strict,
    sha256_json,
)


def _safe_open_flags(base: int) -> int:
    flags = base
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


@contextmanager
def _exclusive_ledger_lock(path: Path) -> Iterator[None]:
    """Serialize readers and writers on a persistent sibling lock inode."""
    lock_path = path.with_name(path.name + ".lock")
    descriptor = os.open(
        lock_path,
        _safe_open_flags(os.O_CREAT | os.O_RDWR),
        0o600,
    )
    windows = os.name == "nt"
    locked = False
    try:
        if windows:
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        yield
    finally:
        try:
            if locked:
                if windows:
                    import msvcrt

                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _read_descriptor(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _read_ledger_unlocked(path: Path) -> bytes:
    if not path.exists():
        return b""
    descriptor = os.open(path, _safe_open_flags(os.O_RDONLY))
    try:
        return _read_descriptor(descriptor)
    finally:
        os.close(descriptor)


def _verify_ledger_bytes(path: Path, data: bytes) -> list[dict[str, Any]]:
    if not data:
        return []
    if not data.endswith(b"\n"):
        raise BehaviorGateError(f"{path}: nonempty ledger must end with one final newline")
    raw_lines = data[:-1].split(b"\n")
    entries: list[dict[str, Any]] = []
    previous = ZERO_SHA256
    for line_number, raw_line in enumerate(raw_lines, 1):
        if not raw_line:
            raise BehaviorGateError(f"{path}:{line_number}: blank ledger lines are forbidden")
        try:
            line = raw_line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BehaviorGateError(f"{path}:{line_number}: ledger is not UTF-8") from exc
        entry = _mapping(loads_strict(line, f"{path}:{line_number}"), f"{path}:{line_number}")
        if canonical_bytes(entry) != raw_line:
            raise BehaviorGateError(f"{path}:{line_number}: ledger entry is not canonical JSON")
        if entry.get("schema") != LEDGER_ENTRY_SCHEMA:
            raise BehaviorGateError(f"{path}:{line_number}: wrong ledger schema")
        sequence = _nonnegative_int(entry.get("sequence"), f"{path}:{line_number}.sequence")
        if sequence != len(entries):
            raise BehaviorGateError(
                f"{path}:{line_number}: sequence {sequence} does not equal {len(entries)}"
            )
        if _sha256(entry.get("previous_entry_sha256"), f"{path}:{line_number}.previous_entry_sha256") != previous:
            raise BehaviorGateError(f"{path}:{line_number}: broken previous-entry chain")
        _sha256(entry.get("family_sha256"), f"{path}:{line_number}.family_sha256")
        _sha256(
            entry.get("report_receipt_sha256"),
            f"{path}:{line_number}.report_receipt_sha256",
        )
        _nonempty_string(entry.get("kind"), f"{path}:{line_number}.kind")
        declared = _sha256(entry.get("entry_sha256"), f"{path}:{line_number}.entry_sha256")
        unsealed = dict(entry)
        unsealed.pop("entry_sha256", None)
        actual = sha256_json(unsealed)
        if declared != actual:
            raise BehaviorGateError(
                f"{path}:{line_number}: entry_sha256 mismatch: declared={declared} actual={actual}"
            )
        previous = declared
        entries.append(dict(entry))
    return entries


def verify_ledger(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with _exclusive_ledger_lock(path):
        return _verify_ledger_bytes(path, _read_ledger_unlocked(path))


def append_ledger(path: str | Path, report: Mapping[str, Any], kind: str) -> dict[str, Any]:
    path = Path(path)
    kind = _nonempty_string(kind, "kind")
    report = _mapping(report, "report")
    receipt = _sha256(report.get("receipt_sha256"), "report.receipt_sha256")
    unsealed_report = dict(report)
    unsealed_report.pop("receipt_sha256", None)
    if sha256_json(unsealed_report) != receipt:
        raise BehaviorGateError("report receipt is invalid; refusing ledger append")
    family_sha = _sha256(report.get("family_sha256"), "report.family_sha256")

    path.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_ledger_lock(path):
        entries = _verify_ledger_bytes(path, _read_ledger_unlocked(path))
        previous = entries[-1]["entry_sha256"] if entries else ZERO_SHA256
        entry: dict[str, Any] = {
            "schema": LEDGER_ENTRY_SCHEMA,
            "sequence": len(entries),
            "previous_entry_sha256": previous,
            "family_sha256": family_sha,
            "report_receipt_sha256": receipt,
            "kind": kind,
        }
        entry["entry_sha256"] = sha256_json(entry)
        payload = canonical_bytes(entry) + b"\n"
        descriptor = os.open(
            path,
            _safe_open_flags(os.O_APPEND | os.O_CREAT | os.O_RDWR),
            0o644,
        )
        original_size = os.fstat(descriptor).st_size
        try:
            view = memoryview(payload)
            written = 0
            while written < len(payload):
                count = os.write(descriptor, view[written:])
                if count <= 0:
                    raise BehaviorGateError(
                        f"ledger append made no progress after {written} of {len(payload)} bytes"
                    )
                written += count
            os.fsync(descriptor)
            updated = _read_descriptor(descriptor)
            verified = _verify_ledger_bytes(path, updated)
            if verified[-1] != entry:
                raise BehaviorGateError("ledger readback does not match appended entry")
        except BaseException:
            try:
                os.ftruncate(descriptor, original_size)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            raise
        else:
            os.close(descriptor)
        return entry


def render_markdown(report: Mapping[str, Any]) -> str:
    report = _mapping(report, "report")
    lines = [
        "# TITAN behavior-equivalence receipt",
        "",
        f"- Verdict: `{report.get('verdict', '<missing>')}`",
        f"- Family: `{report.get('family_id', '<missing>')}`",
        f"- Family SHA-256: `{report.get('family_sha256', '<missing>')}`",
        f"- Receipt SHA-256: `{report.get('receipt_sha256', '<missing>')}`",
        "",
    ]
    if report.get("schema") == PREFLIGHT_SCHEMA:
        lines.extend(
            [
                f"- Declared candidates: {report.get('declared_candidates')}",
                f"- Unique executable identities: {report.get('unique_executable_identities')}",
                "",
                "## Duplicate exact executable registrations",
                "",
            ]
        )
        groups = report.get("duplicate_executable_groups", [])
        if groups:
            for group in groups:
                lines.append(
                    "- `{} → {}` (representative `{}`)".format(
                        group.get("executable_closure_sha256"),
                        ", ".join(group.get("all_candidate_ids", [])),
                        group.get("representative_candidate_id"),
                    )
                )
        else:
            lines.append("- None.")
    else:
        lines.extend(
            [
                f"- Declared candidates: {report.get('declared_candidates')}",
                f"- Observed behavior classes: {report.get('behavior_class_count')}",
                "",
                "## Observational behavior aliases",
                "",
            ]
        )
        aliases = report.get("observational_behavior_aliases", [])
        if aliases:
            for group in aliases:
                lines.append(
                    "- `{}`: {}".format(
                        group.get("behavior_signature_sha256"),
                        ", ".join(group.get("candidate_ids", [])),
                    )
                )
        else:
            lines.append("- None.")
        lines.extend(["", "## Action/effect contradictions", ""])
        conflicts = report.get("action_only_conflicts", [])
        if conflicts:
            for conflict in conflicts:
                lines.append(
                    "- `{}`: {}".format(
                        conflict.get("action_signature_sha256"),
                        ", ".join(conflict.get("candidate_ids", [])),
                    )
                )
        else:
            lines.append("- None.")
    lines.extend(
        [
            "",
            "## Statistical boundary",
            "",
            "Observational equality is reporting only. It does not authorize retroactive alpha reduction, validation-seed reuse, selection, promotion, package mutation, or Kaggle submission.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_json(report: Mapping[str, Any], target: str | None) -> None:
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if target:
        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)


def _write_markdown(report: Mapping[str, Any], target: str | None) -> None:
    if not target:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")

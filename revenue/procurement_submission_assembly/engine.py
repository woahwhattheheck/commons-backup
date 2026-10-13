"""Deterministic, evidence-bound procurement submission assembly.

This module is deliberately an owner-review assembly compiler, not a submission
bot.  It reads a strict source/requirement packet plus candidate artifact bytes,
recomputes their evidence, and emits a deterministic bundle whose only positive
state is ``ASSEMBLY_READY_FOR_OWNER_REVIEW``.

External provider mutation, signature/certification authority, buyer acceptance,
and commercial/payment state are always outside this module's authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Callable, Iterable, Mapping, Sequence

CONTRACT_VERSION = "procurement-submission-assembly/v1"
RECEIPT_VERSION = "procurement-submission-assembly/receipt-v1"
WORKLIST_VERSION = "procurement-submission-assembly/worklist-v1"

ASSEMBLY_READY_FOR_OWNER_REVIEW = "ASSEMBLY_READY_FOR_OWNER_REVIEW"
HOLD_MISSING_REQUIRED_ARTIFACT = "HOLD_MISSING_REQUIRED_ARTIFACT"
HOLD_SOURCE_CONFLICT = "HOLD_SOURCE_CONFLICT"
HOLD_DEADLINE_PASSED = "HOLD_DEADLINE_PASSED"

MAX_PACKET_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_SOURCES = 512
MAX_REQUIREMENTS = 4096
MAX_ARTIFACTS = 4096
MAX_TEXT = 32768

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class AssemblyError(ValueError):
    """Raised when a packet, filesystem boundary, or bundle is invalid."""


def _fail(message: str) -> "None":
    raise AssemblyError(message)


def _strict_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            _fail(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> "None":
    _fail(f"non-finite JSON constant is forbidden: {value}")


def strict_json_loads(data: bytes) -> Any:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise AssemblyError("input is not strict UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except AssemblyError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AssemblyError(f"invalid JSON: {exc}") from exc


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AssemblyError(f"cannot canonicalize value: {exc}") from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _expect_dict(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(f"{where} must be an object")
    return value


def _expect_list(value: Any, where: str, *, maximum: int) -> list[Any]:
    if type(value) is not list:
        _fail(f"{where} must be an array")
    if len(value) > maximum:
        _fail(f"{where} exceeds maximum length {maximum}")
    return value


def _expect_keys(
    obj: Mapping[str, Any],
    where: str,
    required: Iterable[str],
    optional: Iterable[str] = (),
) -> None:
    required_set = set(required)
    allowed = required_set | set(optional)
    missing = required_set - set(obj)
    unknown = set(obj) - allowed
    if missing:
        _fail(f"{where} missing keys: {sorted(missing)}")
    if unknown:
        _fail(f"{where} has unknown keys: {sorted(unknown)}")


def _string(value: Any, where: str, *, nonempty: bool = True, maximum: int = MAX_TEXT) -> str:
    if type(value) is not str:
        _fail(f"{where} must be a string")
    if "\x00" in value:
        _fail(f"{where} contains NUL")
    if nonempty and not value:
        _fail(f"{where} must not be empty")
    if len(value) > maximum:
        _fail(f"{where} exceeds maximum length {maximum}")
    return value


def _integer(value: Any, where: str, *, minimum: int = 0) -> int:
    if type(value) is not int:
        _fail(f"{where} must be an integer (bool is forbidden)")
    if value < minimum:
        _fail(f"{where} must be >= {minimum}")
    return value


def _nullable_integer(value: Any, where: str, *, minimum: int = 0) -> int | None:
    if value is None:
        return None
    return _integer(value, where, minimum=minimum)


def _nullable_string(value: Any, where: str) -> str | None:
    if value is None:
        return None
    return _string(value, where)


def _enum(value: Any, where: str, allowed: set[str]) -> str:
    text = _string(value, where)
    if text not in allowed:
        _fail(f"{where} must be one of {sorted(allowed)}")
    return text


def _digest(value: Any, where: str) -> str:
    text = _string(value, where, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        _fail(f"{where} must be a lowercase SHA-256 hex digest")
    return text


def _parse_time(value: Any, where: str) -> datetime:
    text = _string(value, where, maximum=64)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise AssemblyError(f"{where} must be ISO-8601/RFC3339-like") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        _fail(f"{where} must include a timezone offset")
    return dt.astimezone(timezone.utc)


def _time_text(dt: datetime) -> str:
    value = dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    return value.replace("+00:00", "Z")


def _relative_path(value: Any, where: str) -> str:
    text = _string(value, where, maximum=4096)
    if "\\" in text:
        _fail(f"{where} must use '/' separators")
    path = PurePosixPath(text)
    if path.is_absolute() or not path.parts:
        _fail(f"{where} must be a non-empty relative path")
    if any(part in {"", ".", ".."} for part in path.parts):
        _fail(f"{where} contains unsafe path components")
    return str(path)


def _open_dir_nofollow(path: str) -> int:
    """Open every directory component without following symlinks."""
    absolute = os.path.abspath(path)
    parts = [part for part in absolute.split(os.sep) if part]
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    root_fd = os.open(os.sep, flags)
    current = root_fd
    try:
        for part in parts:
            next_fd = os.open(
                part,
                flags | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current,
            )
            if current != root_fd:
                os.close(current)
            current = next_fd
        if current == root_fd:
            return os.dup(root_fd)
        return current
    except Exception:
        if current != root_fd:
            os.close(current)
        raise
    finally:
        os.close(root_fd)


def _fingerprint(st: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        st.st_dev,
        st.st_ino,
        st.st_size,
        st.st_mtime_ns,
        st.st_ctime_ns,
        st.st_mode,
    )


def _read_from_fd(fd: int, *, max_bytes: int, where: str) -> bytes:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        _fail(f"{where} is not a regular file")
    if before.st_size < 0 or before.st_size > max_bytes:
        _fail(f"{where} exceeds byte limit {max_bytes}")
    chunks: list[bytes] = []
    remaining = before.st_size
    while remaining:
        chunk = os.read(fd, min(1024 * 1024, remaining))
        if not chunk:
            _fail(f"{where} changed or truncated during read")
        chunks.append(chunk)
        remaining -= len(chunk)
    if os.read(fd, 1):
        _fail(f"{where} grew during read")
    after = os.fstat(fd)
    if _fingerprint(before) != _fingerprint(after):
        _fail(f"{where} generation changed during read")
    return b"".join(chunks)


def _read_regular_path(path: str, *, max_bytes: int, where: str) -> bytes:
    absolute = os.path.abspath(path)
    parent, name = os.path.split(absolute)
    if not name:
        _fail(f"{where} must name a file")
    parent_fd = _open_dir_nofollow(parent or os.sep)
    try:
        fd = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        try:
            return _read_from_fd(fd, max_bytes=max_bytes, where=where)
        finally:
            os.close(fd)
    except OSError as exc:
        raise AssemblyError(f"{where} cannot be opened safely: {exc.strerror or exc}") from exc
    finally:
        os.close(parent_fd)


def _read_regular_under(root_fd: int, relative: str, *, max_bytes: int, where: str) -> bytes:
    parts = PurePosixPath(relative).parts
    current = os.dup(root_fd)
    flags_dir = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, flags_dir, dir_fd=current)
            os.close(current)
            current = next_fd
        fd = os.open(
            parts[-1],
            os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=current,
        )
        try:
            return _read_from_fd(fd, max_bytes=max_bytes, where=where)
        finally:
            os.close(fd)
    except OSError as exc:
        raise AssemblyError(f"{where} cannot be opened safely: {exc.strerror or exc}") from exc
    finally:
        os.close(current)


def load_packet(path: str) -> dict[str, Any]:
    data = _read_regular_path(path, max_bytes=MAX_PACKET_BYTES, where="packet")
    value = strict_json_loads(data)
    return _expect_dict(value, "packet")


def _validate_source(value: Any, index: int) -> dict[str, Any]:
    where = f"sources[{index}]"
    obj = _expect_dict(value, where)
    _expect_keys(
        obj,
        where,
        ["source_id", "generation", "sha256", "source_class", "section", "observed_at_utc"],
    )
    return {
        "source_id": _string(obj["source_id"], f"{where}.source_id", maximum=256),
        "generation": _integer(obj["generation"], f"{where}.generation", minimum=1),
        "sha256": _digest(obj["sha256"], f"{where}.sha256"),
        "source_class": _enum(obj["source_class"], f"{where}.source_class", {"OFFICIAL", "SECONDARY"}),
        "section": _string(obj["section"], f"{where}.section", maximum=1024),
        "observed_at_utc": _time_text(_parse_time(obj["observed_at_utc"], f"{where}.observed_at_utc")),
    }


def _validate_deadline(value: Any, index: int) -> dict[str, Any]:
    where = f"deadlines[{index}]"
    obj = _expect_dict(value, where)
    _expect_keys(obj, where, ["deadline_id", "at", "source_id", "source_section", "generation"])
    return {
        "deadline_id": _string(obj["deadline_id"], f"{where}.deadline_id", maximum=256),
        "at": _time_text(_parse_time(obj["at"], f"{where}.at")),
        "source_id": _string(obj["source_id"], f"{where}.source_id", maximum=256),
        "source_section": _string(obj["source_section"], f"{where}.source_section", maximum=1024),
        "generation": _integer(obj["generation"], f"{where}.generation", minimum=1),
    }


def _validate_requirement(value: Any, index: int) -> dict[str, Any]:
    where = f"requirements[{index}]"
    obj = _expect_dict(value, where)
    _expect_keys(
        obj,
        where,
        [
            "requirement_id",
            "slot_id",
            "generation",
            "source_id",
            "source_section",
            "requirement_class",
            "delivery_kind",
            "order",
            "filename_rule",
            "format",
            "page_limit",
            "size_limit_bytes",
            "signature_requirement",
            "attachment_class",
            "portal_field",
        ],
    )
    return {
        "requirement_id": _string(obj["requirement_id"], f"{where}.requirement_id", maximum=256),
        "slot_id": _string(obj["slot_id"], f"{where}.slot_id", maximum=256),
        "generation": _integer(obj["generation"], f"{where}.generation", minimum=1),
        "source_id": _string(obj["source_id"], f"{where}.source_id", maximum=256),
        "source_section": _string(obj["source_section"], f"{where}.source_section", maximum=1024),
        "requirement_class": _enum(
            obj["requirement_class"], f"{where}.requirement_class", {"REQUIRED", "OPTIONAL"}
        ),
        "delivery_kind": _enum(obj["delivery_kind"], f"{where}.delivery_kind", {"FILE", "FORM_VALUE"}),
        "order": _nullable_integer(obj["order"], f"{where}.order", minimum=0),
        "filename_rule": _nullable_string(obj["filename_rule"], f"{where}.filename_rule"),
        "format": _nullable_string(obj["format"], f"{where}.format"),
        "page_limit": _nullable_integer(obj["page_limit"], f"{where}.page_limit", minimum=1),
        "size_limit_bytes": _nullable_integer(
            obj["size_limit_bytes"], f"{where}.size_limit_bytes", minimum=1
        ),
        "signature_requirement": _enum(
            obj["signature_requirement"],
            f"{where}.signature_requirement",
            {"NONE", "SIGNATURE", "NOTARIZATION", "CERTIFICATION", "SIGNATORY_AUTHORITY"},
        ),
        "attachment_class": _nullable_string(obj["attachment_class"], f"{where}.attachment_class"),
        "portal_field": _nullable_string(obj["portal_field"], f"{where}.portal_field"),
    }


def _validate_artifact(value: Any, index: int) -> dict[str, Any]:
    where = f"artifacts[{index}]"
    obj = _expect_dict(value, where)
    if "kind" not in obj:
        _fail(f"{where} missing keys: ['kind']")
    kind = _enum(obj["kind"], f"{where}.kind", {"FILE", "FORM_VALUE"})
    if kind == "FILE":
        _expect_keys(obj, where, ["slot_id", "kind", "path", "built_for_generation"])
        return {
            "slot_id": _string(obj["slot_id"], f"{where}.slot_id", maximum=256),
            "kind": kind,
            "path": _relative_path(obj["path"], f"{where}.path"),
            "built_for_generation": _integer(
                obj["built_for_generation"], f"{where}.built_for_generation", minimum=1
            ),
        }
    _expect_keys(obj, where, ["slot_id", "kind", "value", "built_for_generation"])
    value_text = _string(obj["value"], f"{where}.value", maximum=MAX_TEXT)
    return {
        "slot_id": _string(obj["slot_id"], f"{where}.slot_id", maximum=256),
        "kind": kind,
        "value": value_text,
        "built_for_generation": _integer(
            obj["built_for_generation"], f"{where}.built_for_generation", minimum=1
        ),
    }


def _normalize_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    _expect_keys(
        packet,
        "packet",
        ["contract_version", "opportunity", "sources", "deadlines", "requirements", "artifacts"],
    )
    if _string(packet["contract_version"], "contract_version", maximum=128) != CONTRACT_VERSION:
        _fail(f"contract_version must equal {CONTRACT_VERSION}")

    opportunity = _expect_dict(packet["opportunity"], "opportunity")
    _expect_keys(opportunity, "opportunity", ["opportunity_id", "buyer", "solicitation_id", "source_generation"])
    normalized_opportunity = {
        "opportunity_id": _string(opportunity["opportunity_id"], "opportunity.opportunity_id", maximum=256),
        "buyer": _string(opportunity["buyer"], "opportunity.buyer", maximum=512),
        "solicitation_id": _string(opportunity["solicitation_id"], "opportunity.solicitation_id", maximum=256),
        "source_generation": _integer(opportunity["source_generation"], "opportunity.source_generation", minimum=1),
    }

    source_values = _expect_list(packet["sources"], "sources", maximum=MAX_SOURCES)
    if not source_values:
        _fail("sources must not be empty")
    sources = [_validate_source(value, index) for index, value in enumerate(source_values)]
    source_ids = [row["source_id"] for row in sources]
    if len(source_ids) != len(set(source_ids)):
        _fail("source_id values must be unique")
    official = [row for row in sources if row["source_class"] == "OFFICIAL"]
    if not official:
        _fail("at least one OFFICIAL source is required")
    max_generation = max(row["generation"] for row in official)
    if normalized_opportunity["source_generation"] != max_generation:
        _fail("opportunity.source_generation must equal the maximum OFFICIAL source generation")

    deadline_values = _expect_list(packet["deadlines"], "deadlines", maximum=MAX_SOURCES)
    if not deadline_values:
        _fail("deadlines must not be empty")
    deadlines = [_validate_deadline(value, index) for index, value in enumerate(deadline_values)]
    deadline_ids = [row["deadline_id"] for row in deadlines]
    if len(deadline_ids) != len(set(deadline_ids)):
        _fail("deadline_id values must be unique")

    requirement_values = _expect_list(packet["requirements"], "requirements", maximum=MAX_REQUIREMENTS)
    requirements = [_validate_requirement(value, index) for index, value in enumerate(requirement_values)]
    requirement_ids = [row["requirement_id"] for row in requirements]
    if len(requirement_ids) != len(set(requirement_ids)):
        _fail("requirement_id values must be unique")

    artifact_values = _expect_list(packet["artifacts"], "artifacts", maximum=MAX_ARTIFACTS)
    artifacts = [_validate_artifact(value, index) for index, value in enumerate(artifact_values)]
    slots = [row["slot_id"] for row in artifacts]
    if len(slots) != len(set(slots)):
        _fail("at most one candidate artifact is permitted per slot_id")

    source_by_id = {row["source_id"]: row for row in sources}
    for index, deadline in enumerate(deadlines):
        source = source_by_id.get(deadline["source_id"])
        if source is None:
            _fail(f"deadlines[{index}] references unknown source_id")
        if source["source_class"] != "OFFICIAL":
            _fail(f"deadlines[{index}] must reference an OFFICIAL source")
        if deadline["generation"] != source["generation"]:
            _fail(f"deadlines[{index}] generation must match its source generation")
        if deadline["generation"] > max_generation:
            _fail(f"deadlines[{index}] generation exceeds current source generation")

    for index, requirement in enumerate(requirements):
        source = source_by_id.get(requirement["source_id"])
        if source is None:
            _fail(f"requirements[{index}] references unknown source_id")
        if source["source_class"] != "OFFICIAL":
            _fail(f"requirements[{index}] must reference an OFFICIAL source")
        if requirement["generation"] != source["generation"]:
            _fail(f"requirements[{index}] generation must match its source generation")
        if requirement["generation"] > max_generation:
            _fail(f"requirements[{index}] generation exceeds current source generation")

    return {
        "contract_version": CONTRACT_VERSION,
        "opportunity": normalized_opportunity,
        "sources": sources,
        "deadlines": deadlines,
        "requirements": requirements,
        "artifacts": artifacts,
    }


def _latest_rows(rows: Sequence[dict[str, Any]], key: Callable[[dict[str, Any]], str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    active: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for group_key in sorted(groups):
        group = groups[group_key]
        highest = max(row["generation"] for row in group)
        latest = [row for row in group if row["generation"] == highest]
        if len(latest) != 1:
            conflicts.append(
                {
                    "key": group_key,
                    "generation": highest,
                    "record_ids": sorted(
                        row.get("requirement_id", row.get("deadline_id", "")) for row in latest
                    ),
                }
            )
        else:
            active.append(latest[0])
    return active, conflicts


def _human_checks(requirement: Mapping[str, Any]) -> list[str]:
    checks: list[str] = []
    if requirement["filename_rule"] is not None:
        checks.append("FILENAME_RULE_OWNER_REVIEW")
    if requirement["format"] is not None:
        checks.append("FORMAT_OWNER_REVIEW")
    if requirement["page_limit"] is not None:
        checks.append("PAGE_LIMIT_OWNER_REVIEW")
    if requirement["signature_requirement"] != "NONE":
        checks.append("SIGNATURE_AUTHORITY_OWNER_REVIEW")
    if requirement["portal_field"] is not None:
        checks.append("PORTAL_FIELD_OWNER_REVIEW")
    return checks


def _sort_requirement(row: Mapping[str, Any]) -> tuple[int, int, str]:
    order = row["order"]
    return (1 if order is None else 0, 0 if order is None else order, row["slot_id"])


def compile_packet(
    packet: Mapping[str, Any],
    artifact_root: str,
    *,
    _now: datetime | None = None,
) -> dict[str, Any]:
    """Compile current owner-review assembly state.

    ``_now`` is a private test seam.  Production callers should omit it; the
    current process clock is sampled internally.
    """
    normalized = _normalize_packet(packet)
    now = _now if _now is not None else datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        _fail("internal verification clock must be timezone-aware")
    now = now.astimezone(timezone.utc)

    active_deadlines, deadline_conflicts = _latest_rows(
        normalized["deadlines"], lambda row: "proposal_deadline"
    )
    active_requirements, requirement_conflicts = _latest_rows(
        normalized["requirements"], lambda row: row["slot_id"]
    )

    conflicts = []
    for row in deadline_conflicts:
        conflicts.append({"kind": "DUPLICATE_DEADLINE_GENERATION", **row})
    for row in requirement_conflicts:
        conflicts.append({"kind": "DUPLICATE_REQUIRED_SLOT_GENERATION", **row})

    deadline: dict[str, Any] | None = active_deadlines[0] if active_deadlines else None
    if deadline is None:
        conflicts.append(
            {
                "kind": "NO_UNAMBIGUOUS_ACTIVE_DEADLINE",
                "key": "proposal_deadline",
                "generation": normalized["opportunity"]["source_generation"],
                "record_ids": [],
            }
        )

    declared_slot_ids = {row["slot_id"] for row in normalized["requirements"]}
    candidate_by_slot = {row["slot_id"]: row for row in normalized["artifacts"]}
    # A candidate may legitimately name a declared slot whose current source row is
    # itself conflicted.  That ambiguity must survive to HOLD_SOURCE_CONFLICT rather
    # than being mislabeled as an invented slot.  Only never-declared slots are bad.
    unknown_candidates = sorted(set(candidate_by_slot) - declared_slot_ids)
    if unknown_candidates:
        _fail(f"candidate artifacts reference unknown slot_ids: {unknown_candidates}")

    artifact_rows: list[dict[str, Any]] = []
    missing_required: list[dict[str, Any]] = []
    root_fd = _open_dir_nofollow(artifact_root)
    try:
        for requirement in sorted(active_requirements, key=_sort_requirement):
            slot_id = requirement["slot_id"]
            candidate = candidate_by_slot.get(slot_id)
            evidence: dict[str, Any] = {
                "slot_id": slot_id,
                "requirement_id": requirement["requirement_id"],
                "requirement_class": requirement["requirement_class"],
                "delivery_kind": requirement["delivery_kind"],
                "source_id": requirement["source_id"],
                "source_section": requirement["source_section"],
                "source_generation": requirement["generation"],
                "candidate_state": "MISSING",
                "candidate_sha256": None,
                "candidate_byte_count": None,
                "candidate_path": None,
                "human_checks": _human_checks(requirement),
            }
            reason = "NO_CANDIDATE"
            if candidate is not None:
                if candidate["built_for_generation"] != normalized["opportunity"]["source_generation"]:
                    evidence["candidate_state"] = "STALE_GENERATION"
                    reason = "STALE_GENERATION"
                    if candidate["kind"] == "FILE":
                        evidence["candidate_path"] = candidate["path"]
                elif candidate["kind"] != requirement["delivery_kind"]:
                    evidence["candidate_state"] = "DELIVERY_KIND_MISMATCH"
                    reason = "DELIVERY_KIND_MISMATCH"
                    if candidate["kind"] == "FILE":
                        evidence["candidate_path"] = candidate["path"]
                elif candidate["kind"] == "FORM_VALUE":
                    raw = candidate["value"].encode("utf-8")
                    evidence["candidate_state"] = "PRESENT"
                    evidence["candidate_sha256"] = _sha256(raw)
                    evidence["candidate_byte_count"] = len(raw)
                    reason = "PRESENT"
                else:
                    evidence["candidate_path"] = candidate["path"]
                    try:
                        raw = _read_regular_under(
                            root_fd,
                            candidate["path"],
                            max_bytes=MAX_ARTIFACT_BYTES,
                            where=f"artifact[{slot_id}]",
                        )
                    except AssemblyError:
                        evidence["candidate_state"] = "UNREADABLE"
                        reason = "UNREADABLE"
                    else:
                        limit = requirement["size_limit_bytes"]
                        evidence["candidate_sha256"] = _sha256(raw)
                        evidence["candidate_byte_count"] = len(raw)
                        if limit is not None and len(raw) > limit:
                            evidence["candidate_state"] = "SIZE_LIMIT_EXCEEDED"
                            reason = "SIZE_LIMIT_EXCEEDED"
                        else:
                            evidence["candidate_state"] = "PRESENT"
                            reason = "PRESENT"
            artifact_rows.append(evidence)
            if requirement["requirement_class"] == "REQUIRED" and evidence["candidate_state"] != "PRESENT":
                missing_required.append(
                    {
                        "slot_id": slot_id,
                        "requirement_id": requirement["requirement_id"],
                        "reason": reason,
                        "source_id": requirement["source_id"],
                        "source_section": requirement["source_section"],
                    }
                )
    finally:
        os.close(root_fd)

    if conflicts:
        status = HOLD_SOURCE_CONFLICT
    elif deadline is not None and now >= _parse_time(deadline["at"], "active deadline"):
        status = HOLD_DEADLINE_PASSED
    elif missing_required:
        status = HOLD_MISSING_REQUIRED_ARTIFACT
    else:
        status = ASSEMBLY_READY_FOR_OWNER_REVIEW

    requirement_projection = []
    for row in sorted(active_requirements, key=_sort_requirement):
        requirement_projection.append(dict(row))

    deadline_projection = None if deadline is None else dict(deadline)
    source_manifest = sorted(
        (dict(row) for row in normalized["sources"]),
        key=lambda row: (row["generation"], row["source_id"]),
    )

    receipt: dict[str, Any] = {
        "receipt_version": RECEIPT_VERSION,
        "opportunity": dict(normalized["opportunity"]),
        "status": status,
        "active_deadline": deadline_projection,
        "source_manifest": source_manifest,
        "active_requirements": requirement_projection,
        "artifact_evidence": artifact_rows,
        "missing_required_slots": missing_required,
        "source_conflicts": conflicts,
        "authority": {
            "external_submission_authorized": False,
            "portal_mutation_authorized": False,
            "buyer_contact_authorized": False,
            "signature_or_certification_authorized": False,
            "price_commitment_authorized": False,
            "award_contract_payment_or_revenue_authorized": False,
        },
    }
    receipt["receipt_sha256"] = _sha256(_canonical_json_bytes(receipt))
    return receipt


def _render_checklist(receipt: Mapping[str, Any]) -> bytes:
    opp = receipt["opportunity"]
    lines = [
        "# Procurement Submission Assembly Checklist",
        "",
        f"- Opportunity: `{opp['opportunity_id']}`",
        f"- Buyer: {opp['buyer']}",
        f"- Solicitation: `{opp['solicitation_id']}`",
        f"- Source generation: `{opp['source_generation']}`",
        f"- Assembly state: **{receipt['status']}**",
    ]
    deadline = receipt["active_deadline"]
    if deadline is not None:
        lines.append(f"- Active deadline: `{deadline['at']}` ({deadline['source_id']} · {deadline['source_section']})")
    else:
        lines.append("- Active deadline: **UNRESOLVED SOURCE CONFLICT**")
    lines.extend(["", "## Required and optional slots", ""])
    evidence_by_slot = {row["slot_id"]: row for row in receipt["artifact_evidence"]}
    for req in receipt["active_requirements"]:
        evidence = evidence_by_slot[req["slot_id"]]
        order = "?" if req["order"] is None else str(req["order"])
        lines.append(
            f"- `{req['slot_id']}` [{req['requirement_class']}] order={order} "
            f"kind={req['delivery_kind']} → **{evidence['candidate_state']}**"
        )
        lines.append(f"  - Source: `{req['source_id']}` · {req['source_section']}")
        if evidence["candidate_path"] is not None:
            lines.append(f"  - Candidate path: `{evidence['candidate_path']}`")
        if evidence["candidate_sha256"] is not None:
            lines.append(f"  - Candidate SHA-256: `{evidence['candidate_sha256']}`")
        if req["filename_rule"] is not None:
            lines.append(f"  - Buyer filename rule (owner verify): {req['filename_rule']}")
        if req["format"] is not None:
            lines.append(f"  - Buyer format (owner verify): {req['format']}")
        if req["page_limit"] is not None:
            lines.append(f"  - Buyer page limit (owner verify): {req['page_limit']}")
        if req["size_limit_bytes"] is not None:
            lines.append(f"  - Byte limit (machine checked): {req['size_limit_bytes']}")
        if req["signature_requirement"] != "NONE":
            lines.append(
                f"  - Signature/certification requirement: {req['signature_requirement']} — OWNER AUTHORITY REVIEW REQUIRED"
            )
        if req["attachment_class"] is not None:
            lines.append(f"  - Attachment class: {req['attachment_class']}")
        if req["portal_field"] is not None:
            lines.append(f"  - Portal/form field (owner verify): {req['portal_field']}")
    lines.extend(["", "## Missing required work", ""])
    if receipt["missing_required_slots"]:
        for row in receipt["missing_required_slots"]:
            lines.append(f"- `{row['slot_id']}` — {row['reason']} ({row['source_id']} · {row['source_section']})")
    else:
        lines.append("- None at the structural assembly layer.")
    lines.extend(["", "## Source conflicts", ""])
    if receipt["source_conflicts"]:
        for row in receipt["source_conflicts"]:
            lines.append(f"- {row['kind']} · key `{row['key']}` · generation `{row['generation']}`")
    else:
        lines.append("- None detected in the supplied authoritative generation.")
    lines.extend(
        [
            "",
            "## Authority ceiling",
            "",
            "This bundle is owner-review assembly evidence only. It does not authorize buyer contact, portal upload/submission, signatures/certifications, price commitments, contract acceptance, payment, cash, or revenue recognition.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _render_worklist(receipt: Mapping[str, Any]) -> bytes:
    worklist = {
        "worklist_version": WORKLIST_VERSION,
        "opportunity_id": receipt["opportunity"]["opportunity_id"],
        "status": receipt["status"],
        "missing_required_slots": receipt["missing_required_slots"],
        "source_conflicts": receipt["source_conflicts"],
        "external_submission_authorized": False,
    }
    worklist["worklist_sha256"] = _sha256(_canonical_json_bytes(worklist))
    return _canonical_json_bytes(worklist)


def render_bundle(receipt: Mapping[str, Any]) -> dict[str, bytes]:
    return {
        "assembly.json": _canonical_json_bytes(receipt),
        "checklist.md": _render_checklist(receipt),
        "missing.json": _render_worklist(receipt),
    }


def _validated_stem(stem: str) -> str:
    if not _STEM_RE.fullmatch(stem):
        _fail("stem must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    return stem


def _publish_exclusive(output_dir: str, files: Mapping[str, bytes]) -> dict[str, str]:
    dir_fd = _open_dir_nofollow(output_dir)
    opened: dict[str, tuple[int, tuple[int, int]]] = {}
    try:
        for name in files:
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=dir_fd,
            )
            st = os.fstat(fd)
            opened[name] = (fd, (st.st_dev, st.st_ino))
        for name, data in files.items():
            fd = opened[name][0]
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    _fail(f"short write while publishing {name}")
                view = view[written:]
            os.fsync(fd)
        os.fsync(dir_fd)
        result = {name: _sha256(data) for name, data in files.items()}
        for fd, _identity in opened.values():
            os.close(fd)
        opened.clear()
        return result
    except Exception:
        for name, (fd, identity) in list(opened.items()):
            try:
                current = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == identity:
                    os.unlink(name, dir_fd=dir_fd)
            except OSError:
                pass
            try:
                os.close(fd)
            except OSError:
                pass
        raise
    finally:
        os.close(dir_fd)


def publish_bundle(receipt: Mapping[str, Any], output_dir: str, *, stem: str = "submission") -> dict[str, str]:
    stem = _validated_stem(stem)
    rendered = render_bundle(receipt)
    named = {
        f"{stem}.assembly.json": rendered["assembly.json"],
        f"{stem}.checklist.md": rendered["checklist.md"],
        f"{stem}.missing.json": rendered["missing.json"],
    }
    return _publish_exclusive(output_dir, named)


def verify_bundle(
    packet_path: str,
    artifact_root: str,
    output_dir: str,
    *,
    stem: str = "submission",
) -> dict[str, Any]:
    stem = _validated_stem(stem)
    packet = load_packet(packet_path)
    receipt = compile_packet(packet, artifact_root)
    expected = render_bundle(receipt)
    root_fd = _open_dir_nofollow(output_dir)
    try:
        comparisons = [
            (f"{stem}.assembly.json", expected["assembly.json"]),
            (f"{stem}.checklist.md", expected["checklist.md"]),
            (f"{stem}.missing.json", expected["missing.json"]),
        ]
        for name, expected_bytes in comparisons:
            actual = _read_regular_under(root_fd, name, max_bytes=MAX_PACKET_BYTES, where=f"bundle[{name}]")
            if actual != expected_bytes:
                _fail(f"bundle semantic verification failed for {name}")
    finally:
        os.close(root_fd)
    return receipt


def _compile_command(args: argparse.Namespace) -> int:
    packet = load_packet(args.packet)
    receipt = compile_packet(packet, args.artifact_root)
    digests = publish_bundle(receipt, args.output_dir, stem=args.stem)
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "receipt_sha256": receipt["receipt_sha256"],
                "published": digests,
                "external_submission_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0


def _verify_command(args: argparse.Namespace) -> int:
    receipt = verify_bundle(args.packet, args.artifact_root, args.output_dir, stem=args.stem)
    print(
        json.dumps(
            {
                "verified": True,
                "status": receipt["status"],
                "receipt_sha256": receipt["receipt_sha256"],
                "external_submission_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("compile", _compile_command), ("verify", _verify_command)):
        child = sub.add_parser(name)
        child.add_argument("--packet", required=True)
        child.add_argument("--artifact-root", required=True)
        child.add_argument("--output-dir", required=True)
        child.add_argument("--stem", default="submission")
        child.set_defaults(handler=handler)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except AssemblyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

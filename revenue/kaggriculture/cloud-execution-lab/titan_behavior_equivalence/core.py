# SPDX-License-Identifier: Apache-2.0
"""Strict family declarations and pre-result executable-alias refusal."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence



FAMILY_SCHEMA = "titan-behavior-family/v1"
OBSERVATIONS_SCHEMA = "titan-behavior-observations/v1"
PREFLIGHT_SCHEMA = "titan-behavior-family-preflight/v1"
REPORT_SCHEMA = "titan-behavior-equivalence-report/v1"
LEDGER_ENTRY_SCHEMA = "titan-behavior-equivalence-ledger-entry/v1"
CLOSURE_SCHEMA = "titan-executable-closure/v1"
COMPLETE_STATUSES = frozenset({"DONE", "COMPLETE", "COMPLETED", "PASS"})
EXPECTED_SEATS = frozenset({0, 1})
ZERO_SHA256 = "0" * 64


class BehaviorGateError(ValueError):
    """Raised when an input or receipt fails exact validation."""


def _reject_constant(value: str) -> Any:
    raise BehaviorGateError(f"non-finite JSON constant is forbidden: {value}")


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BehaviorGateError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def loads_strict(text: str, where: str = "JSON") -> Any:
    """Decode RFC-style JSON while rejecting duplicate keys and NaN/Infinity."""
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise BehaviorGateError(f"invalid JSON in {where}: {exc}") from exc


def load_strict(path: str | Path) -> Any:
    path = Path(path)
    try:
        return loads_strict(path.read_text(encoding="utf-8"), str(path))
    except FileNotFoundError as exc:
        raise BehaviorGateError(f"missing input: {path}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise BehaviorGateError(f"value is not canonical finite JSON: {exc}") from exc
    return encoded.encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BehaviorGateError(f"{where} must be an object")
    return value


def _sequence(value: Any, where: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise BehaviorGateError(f"{where} must be an array")
    return value


def _nonempty_string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BehaviorGateError(f"{where} must be a nonempty string")
    return value.strip()


def _sha256(value: Any, where: str) -> str:
    if not isinstance(value, str):
        raise BehaviorGateError(f"{where} must be a lowercase 64-hex SHA-256")
    value = value.strip()
    if (
        len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise BehaviorGateError(f"{where} must be a lowercase 64-hex SHA-256")
    return value


def _nonnegative_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BehaviorGateError(f"{where} must be a nonnegative integer")
    return value


def _finite_number(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BehaviorGateError(f"{where} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise BehaviorGateError(f"{where} must be finite")
    # Canonicalize signed zero so semantically equal ledgers hash equally.
    return 0.0 if result == 0.0 else result


def _seal(report: Mapping[str, Any]) -> dict[str, Any]:
    sealed = dict(report)
    sealed.pop("receipt_sha256", None)
    sealed["receipt_sha256"] = sha256_json(sealed)
    return sealed


@dataclass(frozen=True, order=True)
class ClosureMember:
    path: str
    sha256: str
    bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "bytes": self.bytes}


@dataclass(frozen=True, order=True)
class CandidateSpec:
    candidate_id: str
    archive_sha256: str
    executable_closure_sha256: str
    invocation_sha256: str
    entrypoint: str
    closure_members: tuple[ClosureMember, ...]

    @property
    def executable_key(self) -> tuple[str, str, str]:
        return (
            self.entrypoint,
            self.executable_closure_sha256,
            self.invocation_sha256,
        )

    def closure_dict(self) -> dict[str, Any]:
        return {
            "schema": CLOSURE_SCHEMA,
            "complete": True,
            "members": [member.as_dict() for member in self.closure_members],
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "archive_sha256": self.archive_sha256,
            "executable_closure_sha256": self.executable_closure_sha256,
            "invocation_sha256": self.invocation_sha256,
            "entrypoint": self.entrypoint,
            "executable_closure": self.closure_dict(),
        }


@dataclass(frozen=True)
class FamilySpec:
    family_id: str
    engine_sha256: str
    evaluator_sha256: str
    schedule_sha256: str
    candidates: tuple[CandidateSpec, ...]
    family_sha256: str

    @property
    def candidates_by_id(self) -> Mapping[str, CandidateSpec]:
        return {candidate.candidate_id: candidate for candidate in self.candidates}

    def normalized(self) -> dict[str, Any]:
        return {
            "schema": FAMILY_SCHEMA,
            "family_id": self.family_id,
            "declared_before_results": True,
            "engine_sha256": self.engine_sha256,
            "evaluator_sha256": self.evaluator_sha256,
            "schedule_sha256": self.schedule_sha256,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


def validate_family(raw: Mapping[str, Any]) -> FamilySpec:
    raw = _mapping(raw, "family")
    if raw.get("schema") != FAMILY_SCHEMA:
        raise BehaviorGateError(f"family.schema must equal {FAMILY_SCHEMA!r}")
    if raw.get("declared_before_results") is not True:
        raise BehaviorGateError("family.declared_before_results must be exactly true")

    family_id = _nonempty_string(raw.get("family_id"), "family.family_id")
    engine = _sha256(raw.get("engine_sha256"), "family.engine_sha256")
    evaluator = _sha256(raw.get("evaluator_sha256"), "family.evaluator_sha256")
    schedule = _sha256(raw.get("schedule_sha256"), "family.schedule_sha256")
    rows = _sequence(raw.get("candidates"), "family.candidates")
    if not rows:
        raise BehaviorGateError("family.candidates must be nonempty")

    candidates: list[CandidateSpec] = []
    ids: set[str] = set()
    archives: dict[str, tuple[str, str, str]] = {}
    for index, value in enumerate(rows):
        where = f"family.candidates[{index}]"
        row = _mapping(value, where)
        candidate_id = _nonempty_string(row.get("candidate_id"), f"{where}.candidate_id")
        if candidate_id in ids:
            raise BehaviorGateError(f"duplicate candidate_id: {candidate_id!r}")
        ids.add(candidate_id)

        archive = _sha256(row.get("archive_sha256"), f"{where}.archive_sha256")
        entrypoint = _nonempty_string(row.get("entrypoint"), f"{where}.entrypoint")
        invocation = _sha256(row.get("invocation_sha256"), f"{where}.invocation_sha256")
        closure_raw = _mapping(row.get("executable_closure"), f"{where}.executable_closure")
        if closure_raw.get("schema") != CLOSURE_SCHEMA:
            raise BehaviorGateError(
                f"{where}.executable_closure.schema must equal {CLOSURE_SCHEMA!r}"
            )
        if closure_raw.get("complete") is not True:
            raise BehaviorGateError(f"{where}.executable_closure.complete must be exactly true")
        members_raw = _sequence(
            closure_raw.get("members"), f"{where}.executable_closure.members"
        )
        if not members_raw:
            raise BehaviorGateError(f"{where}.executable_closure.members must be nonempty")
        members: list[ClosureMember] = []
        member_paths: set[str] = set()
        for member_index, member_value in enumerate(members_raw):
            member_where = f"{where}.executable_closure.members[{member_index}]"
            member_row = _mapping(member_value, member_where)
            member_path = _nonempty_string(member_row.get("path"), f"{member_where}.path")
            posix = PurePosixPath(member_path)
            if (
                "\\" in member_path
                or "\x00" in member_path
                or posix.is_absolute()
                or any(part in ("", ".", "..") for part in posix.parts)
                or str(posix) != member_path
            ):
                raise BehaviorGateError(f"{member_where}.path is not a safe canonical relative path")
            if member_path in member_paths:
                raise BehaviorGateError(f"duplicate executable closure member path: {member_path!r}")
            member_paths.add(member_path)
            members.append(
                ClosureMember(
                    member_path,
                    _sha256(member_row.get("sha256"), f"{member_where}.sha256"),
                    _nonnegative_int(member_row.get("bytes"), f"{member_where}.bytes"),
                )
            )
        members.sort(key=lambda member: member.path)
        entrypoint_path = entrypoint.split("::", 1)[0]
        if entrypoint_path not in member_paths:
            raise BehaviorGateError(
                f"{where}.entrypoint path {entrypoint_path!r} is absent from executable closure"
            )
        closure_normalized = {
            "schema": CLOSURE_SCHEMA,
            "complete": True,
            "members": [member.as_dict() for member in members],
        }
        closure = sha256_json(closure_normalized)
        declared_closure = _sha256(
            row.get("executable_closure_sha256"),
            f"{where}.executable_closure_sha256",
        )
        if declared_closure != closure:
            raise BehaviorGateError(
                f"{where}.executable_closure_sha256 mismatch: declared={declared_closure} actual={closure}"
            )
        identity = (closure, invocation, entrypoint)
        prior = archives.get(archive)
        if prior is not None and prior != identity:
            raise BehaviorGateError(
                f"archive {archive} is assigned contradictory executable identities"
            )
        archives[archive] = identity
        candidates.append(
            CandidateSpec(
                candidate_id,
                archive,
                closure,
                invocation,
                entrypoint,
                tuple(members),
            )
        )

    candidates.sort(key=lambda candidate: candidate.candidate_id)
    normalized = {
        "schema": FAMILY_SCHEMA,
        "family_id": family_id,
        "declared_before_results": True,
        "engine_sha256": engine,
        "evaluator_sha256": evaluator,
        "schedule_sha256": schedule,
        "candidates": [candidate.as_dict() for candidate in candidates],
    }
    digest = sha256_json(normalized)
    declared_digest = raw.get("family_sha256")
    if declared_digest is not None:
        declared_digest = _sha256(declared_digest, "family.family_sha256")
        if declared_digest != digest:
            raise BehaviorGateError(
                f"family.family_sha256 mismatch: declared={declared_digest} actual={digest}"
            )
    return FamilySpec(
        family_id=family_id,
        engine_sha256=engine,
        evaluator_sha256=evaluator,
        schedule_sha256=schedule,
        candidates=tuple(candidates),
        family_sha256=digest,
    )


def preflight_family(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Reject duplicate exact executable registrations before outcomes exist."""
    family = validate_family(raw)
    groups: dict[tuple[str, str, str], list[CandidateSpec]] = defaultdict(list)
    for candidate in family.candidates:
        groups[candidate.executable_key].append(candidate)

    duplicates = []
    for (entrypoint, closure, invocation), members in sorted(groups.items()):
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda member: member.candidate_id)
        duplicates.append(
            {
                "entrypoint": entrypoint,
                "executable_closure_sha256": closure,
                "invocation_sha256": invocation,
                "representative_candidate_id": ordered[0].candidate_id,
                "duplicate_candidate_ids": [member.candidate_id for member in ordered[1:]],
                "all_candidate_ids": [member.candidate_id for member in ordered],
                "safe_registration_deduplication": True,
                "reason": "exact executable identity was known before outcomes",
            }
        )

    verdict = "PASS" if not duplicates else "REFUSED_DUPLICATE_EXECUTABLES"
    return _seal(
        {
            "schema": PREFLIGHT_SCHEMA,
            "verdict": verdict,
            "family_id": family.family_id,
            "family_sha256": family.family_sha256,
            "declared_candidates": len(family.candidates),
            "unique_executable_identities": len(groups),
            "duplicate_executable_groups": duplicates,
            "outcomes_consumed": False,
            "familywise_semantics": {
                "retroactive_multiplicity_reduction_allowed": False,
                "validation_seed_reuse_authorized": False,
                "selection_or_promotion_authorized": False,
            },
        }
    )

"""Deterministic evidence compiler for a bounded youth AI training subcontract.

This module intentionally does *not* decide participant eligibility, authorize
stipends/incentives, place participants, or claim credential issuance. It
compiles synthetic/approved training evidence into tamper-evident receipts that
a prime workforce provider can review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import math
import re
from typing import Any, Mapping, Sequence

CONTRACT = "lawrence-youth-ai-training-evidence/v1"
READY = "TECHNICAL_TRAINING_EVIDENCE_READY"
HOLD = "HOLD"
PARTICIPANT_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,96}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

PLAN_KEYS = {
    "contract",
    "program_id",
    "program_version",
    "curriculum",
    "credential_tracks",
    "employer_projects",
    "as_of",
}
MODULE_KEYS = {
    "module_id",
    "title",
    "topics",
    "required_labs",
    "required_assessments",
    "min_assessment_score",
}
TRACK_KEYS = {"track_id", "credential_name", "required_modules"}
PROJECT_KEYS = {
    "project_id",
    "title",
    "required_modules",
    "acceptance_checks",
}
EVIDENCE_KEYS = {
    "contract",
    "participant_token",
    "program_id",
    "program_version",
    "module_events",
    "assessment_events",
    "lab_events",
    "credential_events",
    "employer_project_events",
}
MODULE_EVENT_KEYS = {"event_id", "module_id", "completed_at"}
ASSESSMENT_EVENT_KEYS = {"event_id", "assessment_id", "module_id", "score", "recorded_at"}
LAB_EVENT_KEYS = {"event_id", "lab_id", "module_id", "status", "artifact_sha256", "recorded_at"}
CREDENTIAL_EVENT_KEYS = {"event_id", "track_id", "status", "evidence_sha256", "recorded_at"}
EMPLOYER_PROJECT_EVENT_KEYS = {
    "event_id",
    "project_id",
    "status",
    "acceptance_checks",
    "artifact_sha256",
    "recorded_at",
}


class EvidenceError(ValueError):
    """Fail-closed validation error."""


def _require_plain_dict(value: Any, *, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise EvidenceError(f"{where}: expected plain object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, where: str) -> None:
    keys = set(value)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        raise EvidenceError(f"{where}: schema mismatch missing={missing} extra={extra}")


def _require_list(value: Any, *, where: str) -> list[Any]:
    if type(value) is not list:
        raise EvidenceError(f"{where}: expected array")
    return value


def _require_str(value: Any, *, where: str, nonempty: bool = True) -> str:
    if type(value) is not str:
        raise EvidenceError(f"{where}: expected string")
    if nonempty and not value.strip():
        raise EvidenceError(f"{where}: empty string")
    return value


def _require_id(value: Any, *, where: str) -> str:
    text = _require_str(value, where=where)
    if not ID_RE.fullmatch(text):
        raise EvidenceError(f"{where}: invalid identifier")
    return text


def _require_hex64(value: Any, *, where: str) -> str:
    text = _require_str(value, where=where)
    if not HEX64_RE.fullmatch(text):
        raise EvidenceError(f"{where}: expected lowercase sha256 hex")
    return text


def _require_score(value: Any, *, where: str) -> int:
    if type(value) is not int:
        raise EvidenceError(f"{where}: score must be integer")
    if not 0 <= value <= 100:
        raise EvidenceError(f"{where}: score outside 0..100")
    return value


def _parse_utc(value: Any, *, where: str) -> datetime:
    text = _require_str(value, where=where)
    if not text.endswith("Z"):
        raise EvidenceError(f"{where}: timestamp must use UTC Z form")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise EvidenceError(f"{where}: invalid timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise EvidenceError(f"{where}: timestamp must be UTC")
    return parsed


def loads_strict(text: str) -> Any:
    """JSON loader that rejects duplicate keys and non-finite floats."""

    def pairs_hook(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise EvidenceError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    def bad_constant(value: str) -> None:
        raise EvidenceError(f"non-finite JSON number: {value}")

    try:
        return json.loads(text, object_pairs_hook=pairs_hook, parse_constant=bad_constant)
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid JSON: {exc.msg}") from exc


def canonical_json(value: Any) -> str:
    _reject_noncanonical_scalars(value, where="$")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _reject_noncanonical_scalars(value: Any, *, where: str) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise EvidenceError(f"{where}: non-finite float")
        raise EvidenceError(f"{where}: floats are not allowed")
    if type(value) is list:
        for idx, item in enumerate(value):
            _reject_noncanonical_scalars(item, where=f"{where}[{idx}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise EvidenceError(f"{where}: object key must be string")
            _reject_noncanonical_scalars(item, where=f"{where}.{key}")
        return
    raise EvidenceError(f"{where}: unsupported type {type(value).__name__}")


def digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Module:
    module_id: str
    title: str
    topics: tuple[str, ...]
    required_labs: tuple[str, ...]
    required_assessments: tuple[str, ...]
    min_assessment_score: int


@dataclass(frozen=True)
class CredentialTrack:
    track_id: str
    credential_name: str
    required_modules: tuple[str, ...]


@dataclass(frozen=True)
class EmployerProject:
    project_id: str
    title: str
    required_modules: tuple[str, ...]
    acceptance_checks: tuple[str, ...]


@dataclass(frozen=True)
class Plan:
    program_id: str
    program_version: str
    as_of: datetime
    raw: dict[str, Any]
    modules: tuple[Module, ...]
    tracks: tuple[CredentialTrack, ...]
    projects: tuple[EmployerProject, ...]


def parse_plan(raw: Any, *, trusted_as_of: str) -> Plan:
    obj = _require_plain_dict(raw, where="plan")
    _exact_keys(obj, PLAN_KEYS, where="plan")
    if obj["contract"] != CONTRACT:
        raise EvidenceError("plan.contract: unsupported contract")
    program_id = _require_id(obj["program_id"], where="plan.program_id")
    program_version = _require_id(obj["program_version"], where="plan.program_version")
    declared_as_of = _parse_utc(obj["as_of"], where="plan.as_of")
    trusted_dt = _parse_utc(trusted_as_of, where="trusted_as_of")
    if declared_as_of != trusted_dt:
        raise EvidenceError("plan.as_of: must equal trusted verifier time")

    curriculum = _require_list(obj["curriculum"], where="plan.curriculum")
    if not curriculum:
        raise EvidenceError("plan.curriculum: at least one module required")
    modules: list[Module] = []
    seen_module: set[str] = set()
    all_labs: set[str] = set()
    all_assessments: set[str] = set()
    for idx, item in enumerate(curriculum):
        m = _require_plain_dict(item, where=f"plan.curriculum[{idx}]")
        _exact_keys(m, MODULE_KEYS, where=f"plan.curriculum[{idx}]")
        mid = _require_id(m["module_id"], where=f"plan.curriculum[{idx}].module_id")
        if mid in seen_module:
            raise EvidenceError(f"duplicate module_id: {mid}")
        seen_module.add(mid)
        title = _require_str(m["title"], where=f"module {mid}.title")
        topics = tuple(_require_unique_ids(m["topics"], where=f"module {mid}.topics"))
        labs = tuple(_require_unique_ids(m["required_labs"], where=f"module {mid}.required_labs"))
        assessments = tuple(
            _require_unique_ids(m["required_assessments"], where=f"module {mid}.required_assessments")
        )
        if not topics or not labs or not assessments:
            raise EvidenceError(f"module {mid}: topics/labs/assessments may not be empty")
        overlap = all_labs.intersection(labs)
        if overlap:
            raise EvidenceError(f"lab IDs must be globally unique: {sorted(overlap)}")
        overlap = all_assessments.intersection(assessments)
        if overlap:
            raise EvidenceError(f"assessment IDs must be globally unique: {sorted(overlap)}")
        all_labs.update(labs)
        all_assessments.update(assessments)
        modules.append(
            Module(mid, title, topics, labs, assessments, _require_score(
                m["min_assessment_score"], where=f"module {mid}.min_assessment_score"
            ))
        )

    tracks = _parse_tracks(obj["credential_tracks"], seen_module)
    projects = _parse_projects(obj["employer_projects"], seen_module)
    if not tracks:
        raise EvidenceError("plan.credential_tracks: at least one credential track required")
    if not projects:
        raise EvidenceError("plan.employer_projects: at least one employer project required")
    return Plan(program_id, program_version, trusted_dt, obj, tuple(modules), tuple(tracks), tuple(projects))


def _require_unique_ids(value: Any, *, where: str) -> list[str]:
    items = _require_list(value, where=where)
    out: list[str] = []
    seen: set[str] = set()
    for idx, item in enumerate(items):
        ident = _require_id(item, where=f"{where}[{idx}]")
        if ident in seen:
            raise EvidenceError(f"{where}: duplicate identifier {ident}")
        seen.add(ident)
        out.append(ident)
    return out


def _parse_tracks(value: Any, module_ids: set[str]) -> list[CredentialTrack]:
    rows = _require_list(value, where="plan.credential_tracks")
    out: list[CredentialTrack] = []
    seen: set[str] = set()
    for idx, row in enumerate(rows):
        obj = _require_plain_dict(row, where=f"track[{idx}]")
        _exact_keys(obj, TRACK_KEYS, where=f"track[{idx}]")
        tid = _require_id(obj["track_id"], where=f"track[{idx}].track_id")
        if tid in seen:
            raise EvidenceError(f"duplicate track_id: {tid}")
        seen.add(tid)
        credential = _require_str(obj["credential_name"], where=f"track {tid}.credential_name")
        required = tuple(_require_unique_ids(obj["required_modules"], where=f"track {tid}.required_modules"))
        if not required or not set(required).issubset(module_ids):
            raise EvidenceError(f"track {tid}: unknown/empty required_modules")
        out.append(CredentialTrack(tid, credential, required))
    return out


def _parse_projects(value: Any, module_ids: set[str]) -> list[EmployerProject]:
    rows = _require_list(value, where="plan.employer_projects")
    out: list[EmployerProject] = []
    seen: set[str] = set()
    for idx, row in enumerate(rows):
        obj = _require_plain_dict(row, where=f"project[{idx}]")
        _exact_keys(obj, PROJECT_KEYS, where=f"project[{idx}]")
        pid = _require_id(obj["project_id"], where=f"project[{idx}].project_id")
        if pid in seen:
            raise EvidenceError(f"duplicate project_id: {pid}")
        seen.add(pid)
        title = _require_str(obj["title"], where=f"project {pid}.title")
        required = tuple(_require_unique_ids(obj["required_modules"], where=f"project {pid}.required_modules"))
        checks = tuple(_require_unique_ids(obj["acceptance_checks"], where=f"project {pid}.acceptance_checks"))
        if not required or not set(required).issubset(module_ids):
            raise EvidenceError(f"project {pid}: unknown/empty required_modules")
        if not checks:
            raise EvidenceError(f"project {pid}: acceptance_checks may not be empty")
        out.append(EmployerProject(pid, title, required, checks))
    return out


def compile_participant_evidence(
    plan_raw: Any,
    evidence_raw: Any,
    *,
    trusted_as_of: str,
) -> dict[str, Any]:
    plan = parse_plan(plan_raw, trusted_as_of=trusted_as_of)
    evidence = _require_plain_dict(evidence_raw, where="evidence")
    _exact_keys(evidence, EVIDENCE_KEYS, where="evidence")
    if evidence["contract"] != CONTRACT:
        raise EvidenceError("evidence.contract: unsupported contract")
    token = _require_str(evidence["participant_token"], where="evidence.participant_token")
    if not PARTICIPANT_TOKEN_RE.fullmatch(token):
        raise EvidenceError("evidence.participant_token: opaque token shape required")
    if evidence["program_id"] != plan.program_id or evidence["program_version"] != plan.program_version:
        raise EvidenceError("evidence: program identity/version mismatch")

    module_ids = {m.module_id for m in plan.modules}
    lab_owner = {lab: m.module_id for m in plan.modules for lab in m.required_labs}
    assessment_owner = {a: m.module_id for m in plan.modules for a in m.required_assessments}
    track_map = {t.track_id: t for t in plan.tracks}
    project_map = {p.project_id: p for p in plan.projects}

    event_ids: set[str] = set()
    modules_done: dict[str, datetime] = {}
    for idx, row in enumerate(_require_list(evidence["module_events"], where="module_events")):
        obj = _event(row, MODULE_EVENT_KEYS, f"module_events[{idx}]", event_ids)
        mid = _require_id(obj["module_id"], where=f"module_events[{idx}].module_id")
        if mid not in module_ids:
            raise EvidenceError(f"module_events[{idx}]: unknown module {mid}")
        at = _bounded_event_time(obj["completed_at"], plan.as_of, where=f"module_events[{idx}].completed_at")
        if mid in modules_done and modules_done[mid] != at:
            raise EvidenceError(f"module {mid}: conflicting completion events")
        modules_done[mid] = at

    assessments: dict[str, tuple[str, int]] = {}
    for idx, row in enumerate(_require_list(evidence["assessment_events"], where="assessment_events")):
        obj = _event(row, ASSESSMENT_EVENT_KEYS, f"assessment_events[{idx}]", event_ids)
        aid = _require_id(obj["assessment_id"], where=f"assessment_events[{idx}].assessment_id")
        mid = _require_id(obj["module_id"], where=f"assessment_events[{idx}].module_id")
        if aid not in assessment_owner or assessment_owner[aid] != mid:
            raise EvidenceError(f"assessment {aid}: module binding mismatch")
        _bounded_event_time(obj["recorded_at"], plan.as_of, where=f"assessment_events[{idx}].recorded_at")
        score = _require_score(obj["score"], where=f"assessment {aid}.score")
        current = assessments.get(aid)
        if current is not None and current != (mid, score):
            raise EvidenceError(f"assessment {aid}: conflicting evidence")
        assessments[aid] = (mid, score)

    labs: dict[str, str] = {}
    for idx, row in enumerate(_require_list(evidence["lab_events"], where="lab_events")):
        obj = _event(row, LAB_EVENT_KEYS, f"lab_events[{idx}]", event_ids)
        lid = _require_id(obj["lab_id"], where=f"lab_events[{idx}].lab_id")
        mid = _require_id(obj["module_id"], where=f"lab_events[{idx}].module_id")
        if lid not in lab_owner or lab_owner[lid] != mid:
            raise EvidenceError(f"lab {lid}: module binding mismatch")
        _bounded_event_time(obj["recorded_at"], plan.as_of, where=f"lab_events[{idx}].recorded_at")
        if obj["status"] != "PASS":
            raise EvidenceError(f"lab {lid}: only PASS evidence is admissible")
        artifact = _require_hex64(obj["artifact_sha256"], where=f"lab {lid}.artifact_sha256")
        current = labs.get(lid)
        if current is not None and current != artifact:
            raise EvidenceError(f"lab {lid}: conflicting artifact evidence")
        labs[lid] = artifact

    credentials: dict[str, str] = {}
    for idx, row in enumerate(_require_list(evidence["credential_events"], where="credential_events")):
        obj = _event(row, CREDENTIAL_EVENT_KEYS, f"credential_events[{idx}]", event_ids)
        tid = _require_id(obj["track_id"], where=f"credential_events[{idx}].track_id")
        if tid not in track_map:
            raise EvidenceError(f"credential event: unknown track {tid}")
        _bounded_event_time(obj["recorded_at"], plan.as_of, where=f"credential_events[{idx}].recorded_at")
        if obj["status"] != "VERIFIED_EXTERNAL":
            raise EvidenceError(f"credential {tid}: external verification required")
        evid = _require_hex64(obj["evidence_sha256"], where=f"credential {tid}.evidence_sha256")
        current = credentials.get(tid)
        if current is not None and current != evid:
            raise EvidenceError(f"credential {tid}: conflicting evidence")
        credentials[tid] = evid

    project_results: dict[str, str] = {}
    for idx, row in enumerate(_require_list(evidence["employer_project_events"], where="employer_project_events")):
        obj = _event(row, EMPLOYER_PROJECT_EVENT_KEYS, f"employer_project_events[{idx}]", event_ids)
        pid = _require_id(obj["project_id"], where=f"employer_project_events[{idx}].project_id")
        if pid not in project_map:
            raise EvidenceError(f"employer project: unknown project {pid}")
        _bounded_event_time(obj["recorded_at"], plan.as_of, where=f"employer_project_events[{idx}].recorded_at")
        if obj["status"] != "ACCEPTED":
            raise EvidenceError(f"employer project {pid}: accepted evidence required")
        got_checks = tuple(_require_unique_ids(
            obj["acceptance_checks"], where=f"employer project {pid}.acceptance_checks"
        ))
        expected_checks = project_map[pid].acceptance_checks
        if set(got_checks) != set(expected_checks) or len(got_checks) != len(expected_checks):
            raise EvidenceError(f"employer project {pid}: acceptance-check set mismatch")
        artifact = _require_hex64(obj["artifact_sha256"], where=f"employer project {pid}.artifact_sha256")
        current = project_results.get(pid)
        if current is not None and current != artifact:
            raise EvidenceError(f"employer project {pid}: conflicting artifact evidence")
        project_results[pid] = artifact

    module_status: list[dict[str, Any]] = []
    complete_modules: set[str] = set()
    for module in plan.modules:
        missing_labs = [x for x in module.required_labs if x not in labs]
        missing_assessments = [x for x in module.required_assessments if x not in assessments]
        failing_assessments = [
            aid for aid in module.required_assessments
            if aid in assessments and assessments[aid][1] < module.min_assessment_score
        ]
        complete = (
            module.module_id in modules_done
            and not missing_labs
            and not missing_assessments
            and not failing_assessments
        )
        if complete:
            complete_modules.add(module.module_id)
        module_status.append({
            "module_id": module.module_id,
            "complete": complete,
            "missing_labs": missing_labs,
            "missing_assessments": missing_assessments,
            "below_threshold_assessments": failing_assessments,
        })

    track_status = [{
        "track_id": track.track_id,
        "modules_complete": set(track.required_modules).issubset(complete_modules),
        "credential_externally_verified": track.track_id in credentials,
    } for track in plan.tracks]

    project_status = [{
        "project_id": project.project_id,
        "modules_complete": set(project.required_modules).issubset(complete_modules),
        "employer_acceptance_evidence": project.project_id in project_results,
    } for project in plan.projects]

    training_ready = len(complete_modules) == len(plan.modules)
    any_track_ready = any(
        row["modules_complete"] and row["credential_externally_verified"] for row in track_status
    )
    any_project_ready = any(
        row["modules_complete"] and row["employer_acceptance_evidence"] for row in project_status
    )
    reasons: list[str] = []
    if not training_ready:
        reasons.append("INCOMPLETE_TRAINING_EVIDENCE")
    if not any_track_ready:
        reasons.append("NO_VERIFIED_CREDENTIAL_TRACK")
    if not any_project_ready:
        reasons.append("NO_ACCEPTED_EMPLOYER_PROJECT")
    state = READY if not reasons else HOLD

    body = {
        "contract": CONTRACT,
        "state": state,
        "reasons": reasons,
        "participant_token": token,
        "program_id": plan.program_id,
        "program_version": plan.program_version,
        "evaluated_at": trusted_as_of,
        "plan_sha256": digest(plan.raw),
        "evidence_sha256": digest(evidence),
        "module_status": module_status,
        "credential_track_status": track_status,
        "employer_project_status": project_status,
        "authority": {
            "participant_eligibility": False,
            "case_management": False,
            "stipend_or_incentive_payment": False,
            "credential_issuance": False,
            "employment_placement": False,
            "buyer_acceptance": False,
            "contract_or_revenue": False,
        },
    }
    body["receipt_sha256"] = digest(body)
    return body


def verify_receipt(receipt: Any) -> bool:
    obj = _require_plain_dict(receipt, where="receipt")
    expected = {
        "contract", "state", "reasons", "participant_token", "program_id", "program_version",
        "evaluated_at", "plan_sha256", "evidence_sha256", "module_status",
        "credential_track_status", "employer_project_status", "authority", "receipt_sha256",
    }
    _exact_keys(obj, expected, where="receipt")
    claimed = _require_hex64(obj["receipt_sha256"], where="receipt.receipt_sha256")
    unsigned = dict(obj)
    unsigned.pop("receipt_sha256")
    return hmac.compare_digest(claimed, digest(unsigned))


def _event(row: Any, keys: set[str], where: str, event_ids: set[str]) -> dict[str, Any]:
    obj = _require_plain_dict(row, where=where)
    _exact_keys(obj, keys, where=where)
    event_id = _require_id(obj["event_id"], where=f"{where}.event_id")
    if event_id in event_ids:
        raise EvidenceError(f"duplicate event_id: {event_id}")
    event_ids.add(event_id)
    return obj


def _bounded_event_time(value: Any, as_of: datetime, *, where: str) -> datetime:
    at = _parse_utc(value, where=where)
    if at > as_of:
        raise EvidenceError(f"{where}: event is in the future relative to trusted time")
    return at

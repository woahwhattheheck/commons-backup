#!/usr/bin/env python3
"""Deterministic, side-effect-free OffboardMesh competition demo.

Model output is proposal material only. The compiler digest-binds caller-asserted
input into one canonical owner-review packet. Verification reconstructs that
packet from the candidate; a caller-recomputed public receipt is never treated
as proof that arbitrary packet contents correspond to the candidate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Sequence

_NATIVE_DATETIME = datetime
_NATIVE_UTC = timezone.utc
INPUT_SCHEMA = "tjl.offboardmesh-demo-input/v1"
PACKET_SCHEMA = "tjl.offboardmesh-review-packet/v1"
_MAX_BYTES = 1024 * 1024
_MAX_EVIDENCE_AGE_SECONDS = 14 * 24 * 60 * 60
_SAFE_REF = re.compile(r"^[A-Z][A-Z0-9_.:/-]{2,95}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_ACTIONS = {
    "DOCUMENT_HANDOFF",
    "ACCESS_REVOKE",
    "BILLING_CLOSE",
    "ASSET_RETURN",
    "DATA_EXPORT_REVIEW",
    "CONTRACT_CLOSE_REVIEW",
}
_FORBIDDEN_REF_TERMS = ("SECRET", "PASSWORD", "API_KEY", "APIKEY", "TOKEN", "BEARER")
AUTHORITY = {
    "externalSendAuthorized": False,
    "customerContactAuthorized": False,
    "providerMutationAuthorized": False,
    "credentialHandlingAuthorized": False,
    "accessRevocationAuthorized": False,
    "dataDeletionOrExportExecutionAuthorized": False,
    "assetShipmentAuthorized": False,
    "contractTerminationAuthorized": False,
    "invoiceOrPaymentAuthorized": False,
    "accountingMutationAuthorized": False,
    "legalOrPrivacyConclusionAuthorized": False,
    "crmMutationAuthorized": False,
}


class OffboardMeshError(ValueError):
    def __init__(self, code: str, message: str | None = None):
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code


def _fail(code: str, message: str | None = None) -> None:
    raise OffboardMeshError(code, message)


def _canonical(value: Any) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise OffboardMeshError("NONCANONICAL_JSON") from exc
    if len(raw) > _MAX_BYTES:
        _fail("JSON_TOO_LARGE")
    return raw


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _parse_time(value: Any, field: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        _fail("TIME_INVALID", field)
    try:
        parsed = _NATIVE_DATETIME.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise OffboardMeshError("TIME_INVALID", field) from exc
    if parsed.tzinfo is None:
        _fail("TIME_INVALID", field)
    return parsed.astimezone(_NATIVE_UTC)


def _safe_ref(value: Any, field: str) -> str:
    if type(value) is not str or not _SAFE_REF.fullmatch(value):
        _fail("OPAQUE_REF_REQUIRED", field)
    upper = value.upper()
    if "@" in value or any(term in upper for term in _FORBIDDEN_REF_TERMS):
        _fail("CONTACT_OR_SECRET_SHAPED_REF", field)
    return value


def _summary(value: Any, field: str) -> str:
    if type(value) is not str or not value or value != value.strip() or len(value) > 280 or any(ord(ch) < 32 for ch in value):
        _fail("SUMMARY_INVALID", field)
    lowered = value.lower()
    if "@" in value or "http://" in lowered or "https://" in lowered:
        _fail("CONTACT_ROUTE_IN_SUMMARY", field)
    return value


def _exact_keys(obj: Any, expected: set[str], field: str) -> dict[str, Any]:
    if type(obj) is not dict or set(obj) != expected:
        _fail("FIELDS_INVALID", field)
    return obj


def _validate_candidate(candidate: Any) -> dict[str, Any]:
    root = _exact_keys(
        candidate,
        {"schema", "organizationRef", "engagementId", "planVersion", "requestedAt", "requestedCloseoutAt", "modelProposal", "evidence"},
        "candidate",
    )
    if root["schema"] != INPUT_SCHEMA:
        _fail("SCHEMA_INVALID")
    organization = _safe_ref(root["organizationRef"], "organizationRef")
    engagement = _safe_ref(root["engagementId"], "engagementId")
    plan_version = _safe_ref(root["planVersion"], "planVersion")
    requested_at = _parse_time(root["requestedAt"], "requestedAt")
    closeout_at = _parse_time(root["requestedCloseoutAt"], "requestedCloseoutAt")
    if closeout_at < requested_at:
        _fail("CLOSEOUT_BEFORE_REQUEST")

    proposal = _exact_keys(root["modelProposal"], {"sourceModelRef", "generatedAt", "suggestions"}, "modelProposal")
    source_model = _safe_ref(proposal["sourceModelRef"], "modelProposal.sourceModelRef")
    generated_at = _parse_time(proposal["generatedAt"], "modelProposal.generatedAt")
    if generated_at < requested_at or generated_at > closeout_at:
        _fail("MODEL_TIME_OUTSIDE_REQUEST_WINDOW")
    if type(proposal["suggestions"]) is not list or not proposal["suggestions"]:
        _fail("SUGGESTIONS_REQUIRED")

    if type(root["evidence"]) is not list or not root["evidence"]:
        _fail("EVIDENCE_REQUIRED")
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(root["evidence"]):
        ev = _exact_keys(raw, {"evidenceId", "kind", "observedAt", "sha256", "sourceRef", "ownerSupplied"}, f"evidence[{index}]")
        evidence_id = _safe_ref(ev["evidenceId"], f"evidence[{index}].evidenceId")
        if evidence_id in evidence_by_id:
            _fail("DUPLICATE_EVIDENCE_ID", evidence_id)
        kind = _safe_ref(ev["kind"], f"evidence[{index}].kind")
        source_ref = _safe_ref(ev["sourceRef"], f"evidence[{index}].sourceRef")
        observed = _parse_time(ev["observedAt"], f"evidence[{index}].observedAt")
        if observed > requested_at:
            _fail("FUTURE_EVIDENCE", evidence_id)
        if (requested_at - observed).total_seconds() > _MAX_EVIDENCE_AGE_SECONDS:
            _fail("STALE_EVIDENCE_AT_REQUEST", evidence_id)
        if type(ev["sha256"]) is not str or not _SHA256.fullmatch(ev["sha256"]):
            _fail("EVIDENCE_SHA256_INVALID", evidence_id)
        if type(ev["ownerSupplied"]) is not bool:
            _fail("OWNER_SUPPLIED_ASSERTION_INVALID", evidence_id)
        evidence_by_id[evidence_id] = {
            "evidenceId": evidence_id,
            "kind": kind,
            "observedAt": ev["observedAt"],
            "sha256": ev["sha256"],
            "sourceRef": source_ref,
            "ownerSupplied": ev["ownerSupplied"],
            "provenance": "CALLER_ASSERTED_UNVERIFIED",
        }

    tasks: list[dict[str, Any]] = []
    seen_tasks: set[str] = set()
    for index, raw in enumerate(proposal["suggestions"]):
        task = _exact_keys(raw, {"taskId", "actionClass", "summary", "ownerRef", "evidenceRefs", "proposedState"}, f"suggestions[{index}]")
        task_id = _safe_ref(task["taskId"], f"suggestions[{index}].taskId")
        if task_id in seen_tasks:
            _fail("DUPLICATE_TASK_ID", task_id)
        seen_tasks.add(task_id)
        action = _safe_ref(task["actionClass"], f"suggestions[{index}].actionClass")
        if action not in _ALLOWED_ACTIONS:
            _fail("ACTION_CLASS_UNSUPPORTED", action)
        if task["proposedState"] != "PROPOSAL_ONLY":
            _fail("MODEL_STATE_MUST_BE_PROPOSAL_ONLY", task_id)
        owner_ref = _safe_ref(task["ownerRef"], f"suggestions[{index}].ownerRef")
        summary = _summary(task["summary"], f"suggestions[{index}].summary")
        refs = task["evidenceRefs"]
        if type(refs) is not list or not refs:
            _fail("TASK_EVIDENCE_REQUIRED", task_id)
        normalized_refs: list[str] = []
        seen_refs: set[str] = set()
        for ref in refs:
            evidence_ref = _safe_ref(ref, f"{task_id}.evidenceRefs")
            if evidence_ref in seen_refs:
                _fail("DUPLICATE_TASK_EVIDENCE_REF", evidence_ref)
            seen_refs.add(evidence_ref)
            if evidence_ref not in evidence_by_id:
                _fail("UNKNOWN_EVIDENCE_REF", evidence_ref)
            normalized_refs.append(evidence_ref)
        tasks.append({
            "taskId": task_id,
            "actionClass": action,
            "summary": summary,
            "ownerRef": owner_ref,
            "evidenceRefs": sorted(normalized_refs),
            "modelState": "PROPOSAL_ONLY",
            "reviewState": "OWNER_REVIEW_REQUIRED",
            "executionAuthorized": False,
        })

    return {
        "schema": INPUT_SCHEMA,
        "organizationRef": organization,
        "engagementId": engagement,
        "planVersion": plan_version,
        "requestedAt": root["requestedAt"],
        "requestedCloseoutAt": root["requestedCloseoutAt"],
        "modelProposal": {"sourceModelRef": source_model, "generatedAt": proposal["generatedAt"], "suggestions": tasks},
        "evidence": [evidence_by_id[k] for k in sorted(evidence_by_id)],
    }


def compile_packet(candidate: Any) -> dict[str, Any]:
    normalized = _validate_candidate(candidate)
    core = {
        "schema": PACKET_SCHEMA,
        "source": {
            "sourceSha256": _digest(candidate),
            "organizationRef": normalized["organizationRef"],
            "engagementId": normalized["engagementId"],
            "planVersion": normalized["planVersion"],
            "requestedAt": normalized["requestedAt"],
            "requestedCloseoutAt": normalized["requestedCloseoutAt"],
            "sourceModelRef": normalized["modelProposal"]["sourceModelRef"],
            "modelGeneratedAt": normalized["modelProposal"]["generatedAt"],
        },
        "bindings": {
            "evidenceSha256": _digest(normalized["evidence"]),
            "tasksSha256": _digest(normalized["modelProposal"]["suggestions"]),
            "evidenceCount": len(normalized["evidence"]),
            "taskCount": len(normalized["modelProposal"]["suggestions"]),
        },
        "tasks": normalized["modelProposal"]["suggestions"],
        "authority": dict(AUTHORITY),
        "truth": {
            "modelOutputsAreProposalOnly": True,
            "evidenceDigestBound": True,
            "ownerEvidenceBound": False,
            "evidenceProvenance": "CALLER_ASSERTED_UNVERIFIED",
            "currentEvidenceRequired": True,
            "externalExecutionApiExposed": False,
            "customerContactRouteExposed": False,
            "productionModelProviderInferenceClaimed": False,
            "organizerRegistrationClaimed": False,
            "customerAdoptionClaimed": False,
            "revenueClaimed": False,
        },
    }
    result = dict(core)
    result["receiptSha256"] = _digest(core)
    return result


def _packet_integrity(packet: Any) -> bool:
    try:
        if type(packet) is not dict or packet.get("schema") != PACKET_SCHEMA:
            return False
        receipt = packet.get("receiptSha256")
        if type(receipt) is not str or not _SHA256.fullmatch(receipt):
            return False
        unsigned = {k: v for k, v in packet.items() if k != "receiptSha256"}
        if _digest(unsigned) != receipt or packet.get("authority") != AUTHORITY:
            return False
        truth = packet.get("truth")
        if type(truth) is not dict or truth.get("ownerEvidenceBound") is not False or truth.get("evidenceProvenance") != "CALLER_ASSERTED_UNVERIFIED":
            return False
        tasks = packet.get("tasks")
        return bool(
            type(tasks) is list
            and tasks
            and all(
                type(task) is dict
                and task.get("modelState") == "PROPOSAL_ONLY"
                and task.get("reviewState") == "OWNER_REVIEW_REQUIRED"
                and task.get("executionAuthorized") is False
                for task in tasks
            )
        )
    except OffboardMeshError:
        return False


def _verification_facts(candidate: Any, packet: Any) -> tuple[dict[str, bool], dict[str, Any] | None]:
    packet_valid = _packet_integrity(packet)
    candidate_valid = True
    normalized: dict[str, Any] | None
    expected: dict[str, Any] | None
    try:
        normalized = _validate_candidate(candidate)
        expected = compile_packet(candidate)
    except OffboardMeshError:
        candidate_valid = False
        normalized = None
        expected = None

    source = packet.get("source") if type(packet) is dict else None
    same_work = same_plan = source_matches = compiler_projection_matches = False
    if candidate_valid and normalized is not None and type(source) is dict:
        same_work = source.get("organizationRef") == normalized["organizationRef"] and source.get("engagementId") == normalized["engagementId"]
        same_plan = source.get("planVersion") == normalized["planVersion"]
        source_matches = source.get("sourceSha256") == _digest(candidate)
    if candidate_valid and expected is not None and packet_valid:
        try:
            compiler_projection_matches = _canonical(packet) == _canonical(expected)
        except OffboardMeshError:
            compiler_projection_matches = False

    return {
        "packetIntegrityValid": bool(packet_valid),
        "candidateValid": bool(candidate_valid),
        "sameEngagement": bool(same_work),
        "samePlanVersion": bool(same_plan),
        "sourceMatches": bool(source_matches),
        "compilerProjectionMatches": bool(compiler_projection_matches),
    }, normalized


def _build_current_verifier(
    verification_facts: Callable[[Any, Any], tuple[dict[str, bool], dict[str, Any] | None]],
    native_datetime: type[datetime],
    native_utc: Any,
    max_evidence_age_seconds: int,
) -> Callable[[Any, Any], dict[str, Any]]:
    """Capture CURRENT authority once; module-global helper rebinding is ignored."""

    def parse_time(value: str) -> datetime:
        parsed = native_datetime.fromisoformat(value[:-1] + "+00:00")
        return parsed.astimezone(native_utc)

    def is_current(normalized: dict[str, Any], evaluated_at: datetime) -> bool:
        requested = parse_time(normalized["requestedAt"])
        closeout = parse_time(normalized["requestedCloseoutAt"])
        generated = parse_time(normalized["modelProposal"]["generatedAt"])
        if evaluated_at < requested or evaluated_at > closeout or generated > evaluated_at:
            return False
        for evidence in normalized["evidence"]:
            observed = parse_time(evidence["observedAt"])
            if observed > evaluated_at or (evaluated_at - observed).total_seconds() > max_evidence_age_seconds:
                return False
        return True

    def verify(candidate: Any, packet: Any) -> dict[str, Any]:
        facts, normalized = verification_facts(candidate, packet)
        evaluated_at = native_datetime.now(native_utc)
        current_fresh = bool(normalized is not None and is_current(normalized, evaluated_at))
        valid = bool(
            facts["packetIntegrityValid"]
            and facts["candidateValid"]
            and facts["sameEngagement"]
            and facts["samePlanVersion"]
            and facts["sourceMatches"]
            and facts["compilerProjectionMatches"]
            and current_fresh
        )
        return {"externalSendAuthorized": False, "validCurrent": valid, "currentEvidenceFresh": current_fresh, **facts}

    return verify


verify_current = _build_current_verifier(
    _verification_facts,
    datetime,
    timezone.utc,
    14 * 24 * 60 * 60,
)


def verify_historical(candidate: Any, packet: Any) -> dict[str, Any]:
    """Require exact compiler correspondence without asserting present freshness."""
    facts, _ = _verification_facts(candidate, packet)
    valid = bool(
        facts["packetIntegrityValid"]
        and facts["candidateValid"]
        and facts["sameEngagement"]
        and facts["samePlanVersion"]
        and facts["sourceMatches"]
        and facts["compilerProjectionMatches"]
    )
    return {"externalSendAuthorized": False, "validHistorical": valid, **facts}


def _strict_load(path: str | Path) -> Any:
    text = Path(path).read_text(encoding="utf-8")

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in pairs:
            if key in obj:
                _fail("DUPLICATE_JSON_KEY", key)
            obj[key] = value
        return obj

    def reject_constant(value: str) -> None:
        _fail("JSON_NONFINITE", value)

    try:
        return json.loads(text, object_pairs_hook=hook, parse_constant=reject_constant)
    except OffboardMeshError:
        raise
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise OffboardMeshError("JSON_INVALID") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="offboardmesh.py")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("candidate")
    verify_current_cmd = sub.add_parser("verify-current")
    verify_current_cmd.add_argument("candidate")
    verify_current_cmd.add_argument("packet")
    verify_historical_cmd = sub.add_parser("verify-historical")
    verify_historical_cmd.add_argument("candidate")
    verify_historical_cmd.add_argument("packet")
    args = parser.parse_args(argv)
    try:
        if args.command == "compile":
            print(json.dumps(compile_packet(_strict_load(args.candidate)), sort_keys=True, separators=(",", ":")))
            return 0
        if args.command == "verify-current":
            result = verify_current(_strict_load(args.candidate), _strict_load(args.packet))
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return 0 if result["validCurrent"] else 2
        result = verify_historical(_strict_load(args.candidate), _strict_load(args.packet))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["validHistorical"] else 2
    except (OSError, OffboardMeshError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Fixed-host current gate and historical verifier for DCSA Innovation Call #01."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    AUTHORITY_SCHEMA, CANDIDATE_SCHEMA, CONCEPT_DEADLINE, DOCUMENT_SPECS,
    ESTIMATED_START_DATE, FLOOR_SCHEMA, GENERAL_SOLICITATION_ID, HOST_SOURCE_SCHEMA,
    LIVE_QA_AT, MAX_CURRENT_REPORT_AGE, MAX_SOURCE_OBSERVATION_AGE, NOTICE_ID,
    QUESTION_DEADLINE, REPORT_SCHEMA, REQUIRED_CAPABILITIES, REQUIRED_DOCUMENTS,
    SOURCE_SCHEMA, _sha256, authority_sha256, normalize_authority, normalize_candidate,
    normalize_floor, normalize_host_source_generation, normalize_source_ledger,
)
from .decision import compile_historical_report
from .strict import (
    CustodyError, DcsaError, ValidationError, canonical_json_bytes, format_utc,
    parse_utc, read_root_owned_regular_file, require_bool, require_exact_keys,
    require_hex64, strict_json_loads,
)

HOST_ROOT = Path("/etc/commons/dcsa-innovation-call-01")
HOST_AUTHORITY_PATH = HOST_ROOT / "authority.json"
HOST_FLOOR_PATH = HOST_ROOT / "authority-floor.json"
HOST_SOURCE_GENERATION_PATH = HOST_ROOT / "source-generation.json"
HOST_SOURCE_DIR = HOST_ROOT / "sources"
ZERO_DIGEST = "0" * 64


def _load_fixed_source_generation() -> dict[str, Any]:
    record = strict_json_loads(read_root_owned_regular_file(HOST_SOURCE_GENERATION_PATH))
    retained: dict[str, bytes] = {}
    for document_id in REQUIRED_DOCUMENTS:
        path = HOST_SOURCE_DIR / DOCUMENT_SPECS[document_id]["filename"]
        retained[document_id] = read_root_owned_regular_file(path, limit=64 * 1024 * 1024)
    return normalize_host_source_generation(record, retained)


def _load_fixed_authority() -> dict[str, Any]:
    return normalize_authority(strict_json_loads(read_root_owned_regular_file(HOST_AUTHORITY_PATH)))


def _load_fixed_floor() -> dict[str, Any]:
    return normalize_floor(strict_json_loads(read_root_owned_regular_file(HOST_FLOOR_PATH)))


def _capture_fixed_current_trust() -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None, list[str]]:
    """Acquire current trust from code-owned paths. It accepts no caller selectors."""
    blockers: list[str] = []
    try:
        source = _load_fixed_source_generation()
    except (DcsaError, OSError):
        source = None
        blockers.append("HOST_SOURCE_GENERATION_UNAVAILABLE")
    try:
        authority = _load_fixed_authority()
    except (DcsaError, OSError):
        authority = None
        blockers.append("HOST_AUTHORITY_UNAVAILABLE")
    try:
        floor = _load_fixed_floor()
    except (DcsaError, OSError):
        floor = None
        blockers.append("HOST_AUTHORITY_FLOOR_UNAVAILABLE")
    return source, authority, floor, blockers


def compile_current(candidate_bytes: bytes) -> dict[str, Any]:
    """Compile current owner-review readiness from process UTC and fixed-host trust only."""
    candidate = normalize_candidate(strict_json_loads(candidate_bytes))
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    source, authority, floor, capture_blockers = _capture_fixed_current_trust()

    def evaluate_fixed_current() -> tuple[str, list[str], dict[str, Any]]:
        blockers = list(capture_blockers)
        evidence: dict[str, Any] = {
            "source_complete": source is not None and bool(source["complete"]),
            "source_authority_origin": None if source is None else source["authority_origin"],
            "authority_loaded": authority is not None,
            "authority_floor_loaded": floor is not None,
            "required_capabilities_declared": set(candidate["declared_capabilities"]) == set(REQUIRED_CAPABILITIES),
        }
        if source is None:
            blockers.append("CONTROLLING_SOURCE_BYTES_INCOMPLETE")
        else:
            observed = parse_utc(source["observed_at"], field="host source observed_at")
            if observed > now:
                blockers.append("SOURCE_OBSERVED_IN_FUTURE")
            if now - observed > MAX_SOURCE_OBSERVATION_AGE:
                blockers.append("SOURCE_OBSERVATION_STALE")
            if not source["complete"] or source["authority_origin"] != "FIXED_HOST_RETAINED_BYTES":
                blockers.append("CONTROLLING_SOURCE_BYTES_INCOMPLETE")
        if now >= CONCEPT_DEADLINE:
            blockers.append("CONCEPT_PAPER_DEADLINE_CLOSED")
        if set(candidate["declared_capabilities"]) != set(REQUIRED_CAPABILITIES):
            blockers.append("REQUIRED_CAPABILITY_DECLARATIONS_INCOMPLETE")
        if source is None or authority is None or floor is None:
            return "HOLD", sorted(set(blockers)), evidence

        auth_digest = authority_sha256(authority)
        evidence.update({
            "source_generation": source["generation"],
            "source_generation_sha256": source["source_generation_sha256"],
            "authority_generation": authority["generation"],
            "authority_sha256": auth_digest,
            "authority_valid_until": authority["valid_until"],
        })
        if authority["generation"] != floor["generation"]:
            blockers.append("AUTHORITY_GENERATION_NOT_CURRENT")
        if not hmac.compare_digest(auth_digest, floor["authority_sha256"]):
            blockers.append("AUTHORITY_DIGEST_NOT_CURRENT")
        if not hmac.compare_digest(authority["source_generation_sha256"], floor["source_generation_sha256"]):
            blockers.append("AUTHORITY_SOURCE_FLOOR_MISMATCH")
        if not hmac.compare_digest(source["source_generation_sha256"], authority["source_generation_sha256"]):
            blockers.append("AUTHORITY_SOURCE_GENERATION_MISMATCH")
        if authority["subject_id"] != candidate["subject_id"]:
            blockers.append("AUTHORITY_SUBJECT_MISMATCH")
        issued = parse_utc(authority["issued_at"], field="authority issued_at")
        valid = parse_utc(authority["valid_until"], field="authority valid_until")
        if issued > now:
            blockers.append("AUTHORITY_ISSUED_IN_FUTURE")
        if valid <= now:
            blockers.append("AUTHORITY_EXPIRED")
        unverified = sorted(row["capability"] for row in authority["capability_evidence"] if row["state"] != "VERIFIED")
        evidence["unverified_capabilities"] = unverified
        if unverified:
            blockers.append("CAPABILITY_EVIDENCE_INCOMPLETE")
        owner = authority["owner_decisions"]
        if candidate["rom_state"] != "OWNER_APPROVED" or not owner["rom_approved"]:
            blockers.append("ROM_OWNER_APPROVAL_REQUIRED")

        def verified(row: Mapping[str, Any]) -> bool:
            return row["state"] == "VERIFIED"

        direct_rows = [
            authority["direct_clearance"]["active_top_secret_fcl"],
            authority["personnel"]["all_assigned_us_citizens"],
            authority["personnel"]["all_assigned_interim_secret_or_higher"],
            authority["personnel"]["privileged_users_t5_or_ts_start"],
            authority["personnel"]["cac_operability"],
            authority["ota_eligibility"]["direct_path"],
        ]
        direct_ready = all(verified(row) for row in direct_rows)
        team_ready = verified(authority["ota_eligibility"]["teaming_prime_path"])
        evidence["direct_eligibility_verified"] = direct_ready
        evidence["teaming_prime_eligibility_verified"] = team_ready
        common = {
            "SOURCE_OBSERVED_IN_FUTURE", "SOURCE_OBSERVATION_STALE",
            "CONTROLLING_SOURCE_BYTES_INCOMPLETE", "CONCEPT_PAPER_DEADLINE_CLOSED",
            "REQUIRED_CAPABILITY_DECLARATIONS_INCOMPLETE", "AUTHORITY_GENERATION_NOT_CURRENT",
            "AUTHORITY_DIGEST_NOT_CURRENT", "AUTHORITY_SOURCE_FLOOR_MISMATCH",
            "AUTHORITY_SOURCE_GENERATION_MISMATCH", "AUTHORITY_SUBJECT_MISMATCH",
            "AUTHORITY_ISSUED_IN_FUTURE", "AUTHORITY_EXPIRED",
            "CAPABILITY_EVIDENCE_INCOMPLETE", "ROM_OWNER_APPROVAL_REQUIRED",
        }
        if common.intersection(blockers):
            return "HOLD", sorted(set(blockers)), evidence
        preference = candidate["route_preference"]
        if preference in {"AUTO", "DIRECT"} and direct_ready and owner["direct_route_approved"]:
            return "DIRECT_READY", [], evidence
        if team_ready and owner["teaming_route_approved"]:
            if preference == "DIRECT" and direct_ready and not owner["direct_route_approved"]:
                blockers.append("DIRECT_ROUTE_NOT_OWNER_APPROVED")
            return "TEAMING_REQUIRED", sorted(set(blockers)), evidence
        if not direct_ready:
            blockers.append("DIRECT_CLEARANCE_OR_PERSONNEL_NOT_VERIFIED")
        if not owner["direct_route_approved"]:
            blockers.append("DIRECT_ROUTE_NOT_OWNER_APPROVED")
        if not team_ready:
            blockers.append("TEAMING_PRIME_ELIGIBILITY_NOT_VERIFIED")
        if not owner["teaming_route_approved"]:
            blockers.append("TEAMING_ROUTE_NOT_OWNER_APPROVED")
        return "HOLD", sorted(set(blockers)), evidence

    state, blockers, evidence = evaluate_fixed_current()
    source_digest = ZERO_DIGEST if source is None else source["source_generation_sha256"]
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "mode": "CURRENT",
        "evaluated_at": format_utc(now),
        "notice_id": NOTICE_ID,
        "general_solicitation_id": GENERAL_SOLICITATION_ID,
        "subject_id": candidate["subject_id"],
        "operation_id": candidate["operation_id"],
        "concept_title": candidate["concept_title"],
        "state": state,
        "historical_route_projection": None,
        "blockers": blockers,
        "question_window": "OPEN" if now < QUESTION_DEADLINE else "CLOSED",
        "question_deadline": format_utc(QUESTION_DEADLINE),
        "live_qa_at": format_utc(LIVE_QA_AT),
        "concept_deadline": format_utc(CONCEPT_DEADLINE),
        "estimated_start_date": ESTIMATED_START_DATE,
        "source_generation_sha256": source_digest,
        "evidence_summary": evidence,
        "external_contact_authorized": False,
        "external_submission_authorized": False,
        "signature_authorized": False,
        "pricing_commitment_authorized": False,
        "clearance_claim_authorized": False,
        "award_or_revenue_claimed": False,
        "current_work_authorized": state in {"DIRECT_READY", "TEAMING_REQUIRED"},
        "receipt_sha256": "",
    }
    report["receipt_sha256"] = _sha256(canonical_json_bytes({**report, "receipt_sha256": ""}))
    return report


def compile_historical(candidate_bytes: bytes, source_bytes: bytes, authority_bytes: bytes, floor_bytes: bytes, *, as_of: str) -> dict[str, Any]:
    return compile_historical_report(
        strict_json_loads(candidate_bytes), strict_json_loads(source_bytes),
        strict_json_loads(authority_bytes), strict_json_loads(floor_bytes),
        as_of=parse_utc(as_of, field="historical as_of"),
    )


def verify_report_shape(report_value: Any) -> dict[str, Any]:
    report = require_exact_keys(report_value, {
        "schema", "mode", "evaluated_at", "notice_id", "general_solicitation_id",
        "subject_id", "operation_id", "concept_title", "state",
        "historical_route_projection", "blockers", "question_window",
        "question_deadline", "live_qa_at", "concept_deadline", "estimated_start_date",
        "source_generation_sha256", "evidence_summary", "external_contact_authorized",
        "external_submission_authorized", "signature_authorized",
        "pricing_commitment_authorized", "clearance_claim_authorized",
        "award_or_revenue_claimed", "current_work_authorized", "receipt_sha256",
    }, field="qualification report")
    if report["schema"] != REPORT_SCHEMA:
        raise ValidationError("qualification report schema is unsupported")
    if report["mode"] not in {"CURRENT", "HISTORICAL_INTEGRITY_ONLY"}:
        raise ValidationError("qualification report mode is unsupported")
    digest = require_hex64(report["receipt_sha256"], field="report receipt_sha256")
    expected = _sha256(canonical_json_bytes({**dict(report), "receipt_sha256": ""}))
    if not hmac.compare_digest(digest, expected):
        raise ValidationError("qualification report receipt does not verify")
    for key in (
        "external_contact_authorized", "external_submission_authorized",
        "signature_authorized", "pricing_commitment_authorized",
        "clearance_claim_authorized", "award_or_revenue_claimed",
    ):
        if require_bool(report[key], field=key):
            raise ValidationError(f"qualification report illegally grants {key}")
    current_auth = require_bool(report["current_work_authorized"], field="current_work_authorized")
    if report["mode"] == "HISTORICAL_INTEGRITY_ONLY" and (report["state"] != "HOLD" or current_auth):
        raise ValidationError("historical report cannot grant current work authority")
    if current_auth != (report["mode"] == "CURRENT" and report["state"] in {"DIRECT_READY", "TEAMING_REQUIRED"}):
        raise ValidationError("current_work_authorized is inconsistent with report state")
    return dict(report)


def verify_current(candidate_bytes: bytes, report_bytes: bytes) -> bool:
    retained = verify_report_shape(strict_json_loads(report_bytes))
    if retained["mode"] != "CURRENT":
        return False
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    retained_at = parse_utc(retained["evaluated_at"], field="report evaluated_at")
    if retained_at > now or now - retained_at > MAX_CURRENT_REPORT_AGE:
        return False
    fresh = compile_current(candidate_bytes)
    retained_semantics, fresh_semantics = dict(retained), dict(fresh)
    for value in (retained_semantics, fresh_semantics):
        value.pop("evaluated_at", None)
        value.pop("receipt_sha256", None)
    return hmac.compare_digest(canonical_json_bytes(retained_semantics), canonical_json_bytes(fresh_semantics))


def verify_historical(candidate_bytes: bytes, source_bytes: bytes, authority_bytes: bytes, floor_bytes: bytes, report_bytes: bytes, *, as_of: str) -> bool:
    retained = verify_report_shape(strict_json_loads(report_bytes))
    if retained["mode"] != "HISTORICAL_INTEGRITY_ONLY":
        return False
    fresh = compile_historical(candidate_bytes, source_bytes, authority_bytes, floor_bytes, as_of=as_of)
    return hmac.compare_digest(canonical_json_bytes(retained), canonical_json_bytes(fresh))

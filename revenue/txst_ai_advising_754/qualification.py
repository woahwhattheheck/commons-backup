from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

SCHEMA = "txst-ai-advising-qualification/v1"
SOLICITATION_ID = "754-TXST-2027-RFP-513-VPGOI"
SOLICITATION_TITLE = "Artificial Intelligence (AI) Powered Advising Platform"
DISCOVERY_DEADLINE_UTC = "2026-09-28T22:00:00Z"

# These are intentionally absent until exact official packet / retained evidence bytes
# are acquired and independently reviewed. Candidate JSON cannot populate them.
TRUSTED_OFFICIAL_PACKET_SHA256: str | None = None
TRUSTED_OWNER_EVIDENCE_SHA256: str | None = None
TRUSTED_PARTNER_EVIDENCE_SHA256: str | None = None

OFFICIAL_HOSTS = {
    "txst.edu",
    "www.txst.edu",
    "bids.sciquest.com",
    "solutions.sciquest.com",
    "txsmartbuy.gov",
    "www.txsmartbuy.gov",
    "txsmartbuy.com",
    "www.txsmartbuy.com",
}
OWNER_GATES = (
    "legal_entity",
    "higher_ed_references",
    "named_key_personnel",
    "insurance",
    "financial_capacity",
    "student_data_privacy",
    "security",
    "accessibility",
    "integration_experience",
    "implementation_support",
    "ai_governance",
)
PROPOSAL_WORKSTREAMS = (
    "student_and_advisor_experience",
    "human_handoff_and_override",
    "sis_crm_lms_identity_integration",
    "advising_policy_and_ai_governance",
    "analytics_predictive_model_evaluation",
    "privacy_security_and_data_minimization",
    "accessibility_and_inclusive_design",
    "implementation_migration_training_support",
    "acceptance_observability_and_handoff",
)

class ContractError(ValueError):
    pass

def _reject_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON value rejected: {value}")

def strict_loads(raw: bytes) -> Any:
    if not isinstance(raw, bytes):
        raise ContractError("input must be bytes")
    if len(raw) > 1_000_000:
        raise ContractError("input too large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("input must be UTF-8") from exc

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise ContractError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=_reject_constant)
    except ContractError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ContractError("invalid JSON") from exc

def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")

def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError("timestamp must be canonical UTC seconds")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ContractError("invalid UTC timestamp") from exc
    return parsed

def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

def _must_exact_keys(obj: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise ContractError(f"{label} must be object")
    if set(obj) != keys:
        missing = sorted(keys - set(obj))
        extra = sorted(set(obj) - keys)
        raise ContractError(f"{label} key mismatch missing={missing} extra={extra}")
    return obj

def _safe_text(value: Any, label: str, *, max_len: int = 240) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise ContractError(f"{label} must be nonempty bounded string")
    if any(ord(ch) < 32 for ch in value):
        raise ContractError(f"{label} contains control characters")
    return value

def _validate_candidate(candidate: Any) -> dict[str, Any]:
    c = _must_exact_keys(
        candidate,
        {"opportunity_id", "requested_posture", "owner_claims", "partner_claims", "commercial"},
        "candidate",
    )
    if c["opportunity_id"] != SOLICITATION_ID:
        raise ContractError("wrong opportunity_id")
    if c["requested_posture"] not in {"AUTO", "PRIME", "TEAMING"}:
        raise ContractError("invalid requested_posture")

    owner = _must_exact_keys(c["owner_claims"], set(OWNER_GATES), "owner_claims")
    for requirement in OWNER_GATES:
        if owner[requirement] not in {"UNKNOWN", "CLAIMED_SUPPORTED", "CLAIMED_GAP"}:
            raise ContractError(f"invalid owner claim state for {requirement}")

    partner = _must_exact_keys(c["partner_claims"], {"status", "cures"}, "partner_claims")
    if partner["status"] not in {"NONE", "CANDIDATE_IDENTIFIED", "CLAIMED_COMMITTED"}:
        raise ContractError("invalid partner status")
    if type(partner["cures"]) is not list or len(partner["cures"]) > len(OWNER_GATES):
        raise ContractError("partner cures must be bounded list")
    if len(set(partner["cures"])) != len(partner["cures"]):
        raise ContractError("duplicate partner cure")
    for gate in partner["cures"]:
        if gate not in OWNER_GATES:
            raise ContractError(f"unknown partner cure gate: {gate}")

    commercial = _must_exact_keys(
        c["commercial"], {"pricing_status", "staffing_status"}, "commercial"
    )
    if commercial["pricing_status"] not in {"OWNER_DECISION_REQUIRED", "DRAFT_ONLY"}:
        raise ContractError("invalid pricing_status")
    if commercial["staffing_status"] not in {"OWNER_DECISION_REQUIRED", "DRAFT_ONLY"}:
        raise ContractError("invalid staffing_status")
    return c

def _official_host(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in OFFICIAL_HOSTS

def _validate_official_authority(authority: Any, raw: bytes, trusted_sha: str | None) -> tuple[bool, datetime | None, list[str]]:
    blockers: list[str] = []
    if trusted_sha is None:
        return False, None, ["official packet bytes/root not retained in reviewed source"]
    if sha256(raw) != trusted_sha:
        raise ContractError("official authority bytes do not match retained root")
    a = _must_exact_keys(
        authority,
        {
            "schema",
            "solicitation_id",
            "title",
            "packet_generation",
            "packet_complete",
            "captured_at_utc",
            "deadline_utc",
            "source_url",
            "documents",
            "requirements",
        },
        "official_authority",
    )
    if a["schema"] != "txst-ai-advising-official-authority/v1":
        raise ContractError("wrong official authority schema")
    if a["solicitation_id"] != SOLICITATION_ID or a["title"] != SOLICITATION_TITLE:
        raise ContractError("official authority solicitation identity mismatch")
    _safe_text(a["packet_generation"], "packet_generation", max_len=96)
    _parse_utc(a["captured_at_utc"])
    official_deadline = _parse_utc(a["deadline_utc"])
    if type(a["packet_complete"]) is not bool:
        raise ContractError("packet_complete must be bool")
    if not _official_host(_safe_text(a["source_url"], "source_url", max_len=500)):
        raise ContractError("official authority source must use approved TXST/Texas procurement host")
    if type(a["documents"]) is not list or not (1 <= len(a["documents"]) <= 100):
        raise ContractError("official documents must be nonempty bounded list")
    docs: dict[str, str] = {}
    for i, item in enumerate(a["documents"]):
        d = _must_exact_keys(item, {"document_id", "sha256", "source_url"}, f"document[{i}]")
        did = _safe_text(d["document_id"], "document_id", max_len=96)
        digest = _safe_text(d["sha256"], "document sha256", max_len=64)
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ContractError("document sha256 invalid")
        if did in docs:
            raise ContractError("duplicate official document id")
        if not _official_host(_safe_text(d["source_url"], "document source_url", max_len=500)):
            raise ContractError("official document has non-official source host")
        docs[did] = digest
    if type(a["requirements"]) is not list or not a["requirements"]:
        raise ContractError("requirements must be nonempty list")
    requirement_ids: set[str] = set()
    for i, item in enumerate(a["requirements"]):
        r = _must_exact_keys(
            item,
            {"requirement_id", "category", "mandatory", "source_document_id", "source_sha256"},
            f"requirement[{i}]",
        )
        rid = _safe_text(r["requirement_id"], "requirement_id", max_len=96)
        if rid in requirement_ids:
            raise ContractError("duplicate requirement id")
        requirement_ids.add(rid)
        _safe_text(r["category"], "requirement category", max_len=96)
        if type(r["mandatory"]) is not bool:
            raise ContractError("mandatory must be bool")
        sid = _safe_text(r["source_document_id"], "source_document_id", max_len=96)
        sdigest = _safe_text(r["source_sha256"], "source_sha256", max_len=64)
        if sid not in docs or docs[sid] != sdigest:
            raise ContractError("requirement is not bound to exact official document digest")
    if not a["packet_complete"]:
        blockers.append("official packet capture explicitly incomplete")
    return a["packet_complete"], official_deadline, blockers

def _validate_evidence_ledger(
    evidence: Any,
    raw: bytes,
    trusted_sha: str | None,
    *,
    schema: str,
    label: str,
) -> tuple[set[str], list[str]]:
    if trusted_sha is None:
        return set(), [f"{label} retained evidence root not present"]
    if sha256(raw) != trusted_sha:
        raise ContractError(f"{label} evidence bytes do not match retained root")
    e = _must_exact_keys(evidence, {"schema", "opportunity_id", "generation", "records"}, label)
    if e["schema"] != schema or e["opportunity_id"] != SOLICITATION_ID:
        raise ContractError(f"{label} evidence identity mismatch")
    _safe_text(e["generation"], f"{label} generation", max_len=96)
    if type(e["records"]) is not list or len(e["records"]) > 100:
        raise ContractError(f"{label} records must be bounded list")
    proven: set[str] = set()
    seen_ids: set[str] = set()
    seen_gates: set[str] = set()
    for i, item in enumerate(e["records"]):
        r = _must_exact_keys(
            item,
            {"record_id", "gate", "evidence_sha256", "status"},
            f"{label}.record[{i}]",
        )
        rid = _safe_text(r["record_id"], "record_id", max_len=96)
        if rid in seen_ids:
            raise ContractError(f"duplicate {label} record id")
        seen_ids.add(rid)
        gate = _safe_text(r["gate"], "evidence gate", max_len=96)
        if gate not in OWNER_GATES:
            raise ContractError(f"unknown evidence gate: {gate}")
        if gate in seen_gates:
            raise ContractError(f"duplicate {label} evidence gate: {gate}")
        seen_gates.add(gate)
        digest = _safe_text(r["evidence_sha256"], "evidence_sha256", max_len=64)
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ContractError("evidence sha256 invalid")
        if r["status"] not in {"PROVEN", "GAP"}:
            raise ContractError("invalid evidence status")
        if r["status"] == "PROVEN":
            proven.add(gate)
    return proven, []

def _compile_at(
    candidate_raw: bytes,
    official_raw: bytes | None,
    owner_raw: bytes | None,
    partner_raw: bytes | None,
    *,
    now: datetime,
    trusted_official_sha: str | None,
    trusted_owner_sha: str | None,
    trusted_partner_sha: str | None,
    historical: bool,
) -> dict[str, Any]:
    candidate = _validate_candidate(strict_loads(candidate_raw))
    if now.tzinfo is None or now.utcoffset() is None:
        raise ContractError("evaluation time must be timezone aware")
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    blockers: list[str] = []
    warnings: list[str] = []

    official_ok = False
    official_deadline: datetime | None = None
    if official_raw is None:
        blockers.append("official controlling RFP package not acquired")
    else:
        official_ok, official_deadline, found = _validate_official_authority(
            strict_loads(official_raw), official_raw, trusted_official_sha
        )
        blockers.extend(found)

    owner_proven: set[str] = set()
    if owner_raw is None:
        blockers.append("retained owner evidence ledger not acquired")
    else:
        owner_proven, found = _validate_evidence_ledger(
            strict_loads(owner_raw),
            owner_raw,
            trusted_owner_sha,
            schema="txst-ai-advising-owner-evidence/v1",
            label="owner",
        )
        blockers.extend(found)

    partner_proven: set[str] = set()
    if partner_raw is None:
        warnings.append("no retained partner evidence ledger")
    else:
        partner_proven, found = _validate_evidence_ledger(
            strict_loads(partner_raw),
            partner_raw,
            trusted_partner_sha,
            schema="txst-ai-advising-partner-evidence/v1",
            label="partner",
        )
        warnings.extend(found)

    missing_prime = sorted(set(OWNER_GATES) - owner_proven)
    combined = owner_proven | partner_proven
    missing_team = sorted(set(OWNER_GATES) - combined)

    if not official_ok:
        state = "HOLD_OFFICIAL_PACKET_REQUIRED"
        route_states = {"PRIME": "HOLD_OFFICIAL_PACKET_REQUIRED", "TEAMING": "HOLD_OFFICIAL_PACKET_REQUIRED"}
    elif official_deadline is not None and now > official_deadline:
        state = "NO_RESPONSE_DEADLINE_PASSED"
        route_states = {"PRIME": "CLOSED", "TEAMING": "CLOSED"}
        blockers.append("controlling response deadline passed")
    else:
        if not missing_prime:
            prime = "READY_FOR_OWNER_PRIME_REVIEW"
        else:
            prime = "HOLD_OWNER_EVIDENCE_REQUIRED"
        if not missing_team and partner_proven:
            team = "READY_FOR_OWNER_TEAMING_REVIEW"
        elif partner_proven:
            team = "HOLD_PARTNER_OR_OWNER_EVIDENCE_REQUIRED"
        else:
            team = "TEAMING_EVIDENCE_REQUIRED"
        route_states = {"PRIME": prime, "TEAMING": team}
        requested = candidate["requested_posture"]
        if requested == "PRIME":
            state = prime
        elif requested == "TEAMING":
            state = team
        elif prime == "READY_FOR_OWNER_PRIME_REVIEW":
            state = prime
        elif team == "READY_FOR_OWNER_TEAMING_REVIEW":
            state = team
        else:
            state = "HOLD_OWNER_OR_PARTNER_EVIDENCE_REQUIRED"

    # Caller-authored claims are advisory only and never change proven evidence.
    claimed_supported = sorted(
        gate for gate, status in candidate["owner_claims"].items()
        if status == "CLAIMED_SUPPORTED" and gate not in owner_proven
    )
    if claimed_supported:
        warnings.append(
            "candidate claims ignored without retained evidence: " + ",".join(claimed_supported)
        )
    if candidate["partner_claims"]["status"] == "CLAIMED_COMMITTED" and not partner_proven:
        warnings.append("candidate partner commitment claim ignored without retained partner evidence")

    payload = {
        "schema": SCHEMA,
        "solicitation": {
            "id": SOLICITATION_ID,
            "title": SOLICITATION_TITLE,
            "discovery_deadline_utc": DISCOVERY_DEADLINE_UTC,
            "official_deadline_utc": (
                official_deadline.strftime("%Y-%m-%dT%H:%M:%SZ")
                if official_deadline is not None
                else None
            ),
        },
        "evaluation_class": "HISTORICAL_INTEGRITY_ONLY" if historical else "CURRENT_OWNER_REVIEW",
        "evaluated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "state": state,
        "route_states": route_states,
        "official_packet_retained": official_ok,
        "owner_evidence_proven_gates": sorted(owner_proven),
        "partner_evidence_proven_gates": sorted(partner_proven),
        "missing_prime_gates": missing_prime,
        "missing_teaming_gates": missing_team,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "proposal_workstreams": list(PROPOSAL_WORKSTREAMS),
        "commercial": {
            "pricing_status": candidate["commercial"]["pricing_status"],
            "staffing_status": candidate["commercial"]["staffing_status"],
        },
        "authority": {
            "buyer_contact_authorized": False,
            "portal_registration_authorized": False,
            "proposal_submission_authorized": False,
            "signature_or_certification_authorized": False,
            "pricing_commitment_authorized": False,
            "personnel_commitment_authorized": False,
            "award_claim_authorized": False,
            "payment_or_revenue_claim_authorized": False,
        },
    }
    payload["receipt_sha256"] = sha256(canonical_bytes(payload))
    return payload

def compile_current(
    candidate_raw: bytes,
    *,
    official_raw: bytes | None = None,
    owner_raw: bytes | None = None,
    partner_raw: bytes | None = None,
) -> dict[str, Any]:
    return _compile_at(
        candidate_raw,
        official_raw,
        owner_raw,
        partner_raw,
        now=_now_utc(),
        trusted_official_sha=TRUSTED_OFFICIAL_PACKET_SHA256,
        trusted_owner_sha=TRUSTED_OWNER_EVIDENCE_SHA256,
        trusted_partner_sha=TRUSTED_PARTNER_EVIDENCE_SHA256,
        historical=False,
    )

def verify_report(
    candidate_raw: bytes,
    report_raw: bytes,
    *,
    official_raw: bytes | None = None,
    owner_raw: bytes | None = None,
    partner_raw: bytes | None = None,
) -> dict[str, Any]:
    report = strict_loads(report_raw)
    if type(report) is not dict:
        raise ContractError("report must be object")
    receipt = report.get("receipt_sha256")
    if type(receipt) is not str or not re.fullmatch(r"[0-9a-f]{64}", receipt):
        raise ContractError("report receipt missing/invalid")
    unsigned = dict(report)
    unsigned.pop("receipt_sha256", None)
    if sha256(canonical_bytes(unsigned)) != receipt:
        raise ContractError("report receipt tamper detected")

    current = compile_current(
        candidate_raw,
        official_raw=official_raw,
        owner_raw=owner_raw,
        partner_raw=partner_raw,
    )
    semantic_keys = (
        "schema",
        "solicitation",
        "evaluation_class",
        "state",
        "route_states",
        "official_packet_retained",
        "owner_evidence_proven_gates",
        "partner_evidence_proven_gates",
        "missing_prime_gates",
        "missing_teaming_gates",
        "blockers",
        "warnings",
        "proposal_workstreams",
        "commercial",
        "authority",
    )
    semantic_match = all(report.get(k) == current.get(k) for k in semantic_keys)
    return {
        "integrity_valid": True,
        "current_semantics_match": semantic_match,
        "current_state": current["state"],
        "current_receipt_sha256": current["receipt_sha256"],
    }

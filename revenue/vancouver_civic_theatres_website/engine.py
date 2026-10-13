from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

EVIDENCE_REGISTRY_SHA256 = "f292a32f3b6bdf92e62c51ffc506bf758aca34ce57afee04972fc8169f8cddf1"
SCHEMA = "vct-pursuit/v1"
REPORT_SCHEMA = "vct-pursuit-report/v1"

_ROOT = Path(__file__).resolve().parent
_EVIDENCE_PATH = _ROOT / "buyer_evidence.json"

_ALLOWED_TOP = {"schema", "company_evidence", "commercial", "owner_decision"}
_ALLOWED_GATE = {"status", "evidence_ref", "notes"}
_GATE_KEYS = (
    "legal_identity",
    "key_contact",
    "wcag_aa_capability",
    "existing_insurance_certificate",
    "insurance_capacity_letter",
    "supplier_code_declaration",
    "workers_comp_coverage",
    "indigenous_participation_response",
    "supplier_diversity_response",
    "key_personnel_privacy",
    "subcontractor_disclosure",
    "agreement_amendments",
    "conflict_disclosure",
)
_GATE_STATUSES = {"UNKNOWN", "READY", "NOT_APPLICABLE"}
_CONDITIONAL_GATES = {
    "key_personnel_privacy",
    "subcontractor_disclosure",
    "agreement_amendments",
}
_DECISIONS = {None, "PRIME", "PARTNER", "PASS"}
_COMMERCIAL_STATUSES = {"NO_ESTIMATE", "PROPOSED_INTERNAL_NOT_SUBMITTED"}

_ACTION_KEYS = (
    "accept_legal_terms",
    "create_supplier_account",
    "contact_buyer",
    "submit_question",
    "submit_proposal",
    "sign_or_certify",
    "commit_staffing",
    "commit_price",
    "accept_contract",
    "spend",
    "claim_award",
    "claim_payment",
    "recognize_revenue",
)


class ContractError(ValueError):
    """Raised when a pursuit packet or report violates the carrier contract."""


def _reject_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON constant is forbidden: {value}")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ContractError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_strict(raw: bytes | str, source: str = "<memory>") -> Any:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractError(f"{source}: not UTF-8") from exc
    if not isinstance(raw, str):
        raise ContractError(f"{source}: expected bytes or string")
    try:
        return json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)
    except ContractError:
        raise
    except json.JSONDecodeError as exc:
        raise ContractError(f"{source}: invalid JSON: {exc.msg}") from exc


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load_evidence() -> dict[str, Any]:
    evidence = load_json_strict(_EVIDENCE_PATH.read_bytes(), str(_EVIDENCE_PATH))
    if not isinstance(evidence, dict):
        raise ContractError("buyer evidence registry must be an object")
    actual = _sha(evidence)
    if actual != EVIDENCE_REGISTRY_SHA256:
        raise ContractError(
            f"buyer evidence registry digest mismatch: expected {EVIDENCE_REGISTRY_SHA256}, got {actual}"
        )
    if evidence.get("opportunity_id") != "PS20261832-ACCS-RFP":
        raise ContractError("buyer evidence registry opportunity id mismatch")
    return evidence


def _require_exact_keys(obj: Any, required: set[str], allowed: set[str], label: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ContractError(f"{label} must be an object")
    missing = sorted(required - obj.keys())
    extra = sorted(obj.keys() - allowed)
    if missing:
        raise ContractError(f"{label} missing fields: {', '.join(missing)}")
    if extra:
        raise ContractError(f"{label} unknown fields: {', '.join(extra)}")
    return obj


def _normalize_gate(name: str, raw: Any) -> dict[str, Any]:
    gate = _require_exact_keys(raw, {"status", "evidence_ref", "notes"}, _ALLOWED_GATE, f"company_evidence.{name}")
    status = gate["status"]
    if status not in _GATE_STATUSES:
        raise ContractError(f"company_evidence.{name}.status invalid")
    evidence_ref = gate["evidence_ref"]
    notes = gate["notes"]
    if evidence_ref is not None and (not isinstance(evidence_ref, str) or not evidence_ref.strip()):
        raise ContractError(f"company_evidence.{name}.evidence_ref must be null or non-empty string")
    if notes is not None and (not isinstance(notes, str) or not notes.strip()):
        raise ContractError(f"company_evidence.{name}.notes must be null or non-empty string")
    if status == "READY" and not evidence_ref:
        raise ContractError(f"company_evidence.{name}: READY requires evidence_ref")
    if status == "NOT_APPLICABLE" and name not in _CONDITIONAL_GATES:
        raise ContractError(f"company_evidence.{name}: NOT_APPLICABLE is invalid for this required response")
    return {"status": status, "evidence_ref": evidence_ref, "notes": notes}


def _normalize_packet(packet: Any) -> dict[str, Any]:
    packet = _require_exact_keys(packet, _ALLOWED_TOP, _ALLOWED_TOP, "packet")
    if packet["schema"] != SCHEMA:
        raise ContractError(f"packet.schema must equal {SCHEMA}")

    raw_evidence = packet["company_evidence"]
    if not isinstance(raw_evidence, dict):
        raise ContractError("packet.company_evidence must be an object")
    if set(raw_evidence) != set(_GATE_KEYS):
        missing = sorted(set(_GATE_KEYS) - raw_evidence.keys())
        extra = sorted(raw_evidence.keys() - set(_GATE_KEYS))
        problems = []
        if missing:
            problems.append("missing " + ", ".join(missing))
        if extra:
            problems.append("unknown " + ", ".join(extra))
        raise ContractError("packet.company_evidence schema mismatch: " + "; ".join(problems))
    company = {name: _normalize_gate(name, raw_evidence[name]) for name in _GATE_KEYS}

    commercial = _require_exact_keys(
        packet["commercial"],
        {"status", "internal_estimate_cad", "basis"},
        {"status", "internal_estimate_cad", "basis"},
        "packet.commercial",
    )
    c_status = commercial["status"]
    if c_status not in _COMMERCIAL_STATUSES:
        raise ContractError("packet.commercial.status invalid")
    estimate = commercial["internal_estimate_cad"]
    if isinstance(estimate, bool):
        raise ContractError("packet.commercial.internal_estimate_cad cannot be boolean")
    if estimate is not None:
        if not isinstance(estimate, (int, float)) or not math.isfinite(estimate) or estimate < 0:
            raise ContractError("packet.commercial.internal_estimate_cad must be finite non-negative number or null")
        estimate = round(float(estimate), 2)
    basis = commercial["basis"]
    if basis is not None and (not isinstance(basis, str) or not basis.strip()):
        raise ContractError("packet.commercial.basis must be null or non-empty string")
    if c_status == "NO_ESTIMATE" and (estimate is not None or basis is not None):
        raise ContractError("NO_ESTIMATE requires null estimate and basis")
    if c_status == "PROPOSED_INTERNAL_NOT_SUBMITTED" and (estimate is None or not basis):
        raise ContractError("PROPOSED_INTERNAL_NOT_SUBMITTED requires estimate and basis")

    decision = packet["owner_decision"]
    if decision not in _DECISIONS:
        raise ContractError("packet.owner_decision must be null, PRIME, PARTNER, or PASS")

    return {
        "schema": SCHEMA,
        "company_evidence": company,
        "commercial": {"status": c_status, "internal_estimate_cad": estimate, "basis": basis},
        "owner_decision": decision,
    }


def _parse_dt(text: str) -> datetime:
    if not isinstance(text, str):
        raise ContractError("evidence datetime must be string")
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"invalid evidence datetime: {text}") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ContractError(f"evidence datetime must include timezone: {text}")
    return dt


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _deadline_state(evidence: dict[str, Any], now: datetime) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ContractError("clock must be timezone-aware")
    official = next(s for s in evidence["sources"] if s["authority"] == "BUYER_PUBLIC_SUPPLIER_PORTAL")
    close = _parse_dt(official["facts"]["closes_at"])
    return "OPEN" if now < close else "CLOSED"


def _company_blockers(company: dict[str, Any]) -> list[str]:
    return [name for name, gate in company.items() if gate["status"] == "UNKNOWN"]


def _controlling_blockers(evidence: dict[str, Any]) -> list[str]:
    return [g["gap_id"] for g in evidence["controlling_gaps"] if g.get("blocking") is True]


def _response_spine() -> list[dict[str, Any]]:
    return [
        {
            "section": "Executive approach",
            "state": "INTERNAL_DRAFT",
            "content": "Deliver an evidence-driven website replacement program covering design, development, implementation, and a controlled transition into maintenance, support, and hosting. Final commitments wait for the buyer attachments and annexes.",
        },
        {
            "section": "Accessibility",
            "state": "SOURCE_BACKED_PREREQUISITE",
            "content": "Treat WCAG Level AA confirmation as an explicit bid prerequisite. Define automated and manual accessibility acceptance evidence only after Annex 2/3 requirements are recovered.",
        },
        {
            "section": "Delivery and cutover",
            "state": "INTERNAL_DRAFT",
            "content": "Plan discovery, information architecture/content inventory, implementation, regression/UAT, launch rehearsal, cutover/rollback, training, and handover. Exact milestones and migration quantities remain uncommitted until the Scope of Work is retained.",
        },
        {
            "section": "Operations",
            "state": "SOURCE_BACKED_SCOPE",
            "content": "Include post-implementation maintenance, support, CMS operations, and hosting. SLA, security, backup, residency, incident, patching, and support-hour commitments remain unresolved pending technical, functional, and agreement documents.",
        },
        {
            "section": "Commercial",
            "state": "SOURCE_BACKED_FORMAT_ONLY",
            "content": "The City requests a single lump-sum Total Project Fee for the initial two-year contract: Year 1 design/development/implementation plus Year 2 maintenance/support for CMS and hosting, exclusive of GST/PST. Annex 4 controls the actual financial response and is not yet retained.",
        },
    ]


def _compile_at(packet: Any, now: datetime) -> dict[str, Any]:
    normalized = _normalize_packet(packet)
    evidence = _load_evidence()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ContractError("clock must be timezone-aware")
    now = now.astimezone(timezone.utc)

    deadline = _deadline_state(evidence, now)
    source_blockers = _controlling_blockers(evidence)
    company_blockers = _company_blockers(normalized["company_evidence"])

    if deadline == "CLOSED":
        posture = "CLOSED_NO_SUBMIT"
    elif source_blockers:
        posture = "HOLD_CONTROLLING_ATTACHMENTS"
    elif company_blockers:
        posture = "HOLD_COMPANY_EVIDENCE"
    elif normalized["owner_decision"] == "PASS":
        posture = "PASS_INTERNAL"
    elif normalized["owner_decision"] == "PARTNER":
        posture = "PARTNER_INTERNAL_READY_FOR_OWNER_REVIEW"
    elif normalized["owner_decision"] == "PRIME":
        posture = "PRIME_INTERNAL_READY_FOR_OWNER_REVIEW"
    else:
        posture = "READY_FOR_OWNER_DECISION"

    official = next(s for s in evidence["sources"] if s["authority"] == "BUYER_PUBLIC_SUPPLIER_PORTAL")
    facts = official["facts"]
    authority = {key: False for key in _ACTION_KEYS}

    payload = {
        "schema": REPORT_SCHEMA,
        "compiled_at": now.isoformat().replace("+00:00", "Z"),
        "opportunity": {
            "buyer": evidence["buyer"],
            "project": evidence["project"],
            "number": evidence["opportunity_id"],
            "currency": facts["currency"],
            "opened_at": facts["opened_at"],
            "closes_at": facts["closes_at"],
            "contact": {
                "name": facts["contact_name"],
                "email": facts["contact_email"],
                "phone": facts["contact_phone"],
            },
            "scope_summary": facts["scope_summary"],
        },
        "deadline_state": deadline,
        "pursuit_posture": posture,
        "source_readiness": "HOLD_CONTROLLING_ATTACHMENTS" if source_blockers else "SOURCE_COMPLETE",
        "company_readiness": "HOLD_COMPANY_EVIDENCE" if company_blockers else "COMPANY_EVIDENCE_COMPLETE",
        "source_blockers": source_blockers,
        "company_blockers": company_blockers,
        "required_submission_components": deepcopy(facts["required_submission_components"]),
        "bid_prerequisites": deepcopy(facts["bid_prerequisites"]),
        "commercial": {
            "buyer_format": deepcopy(facts["service_line"]),
            "internal_estimate": deepcopy(normalized["commercial"]),
            "buyer_facing_price_authorized": False,
            "note": "Annex 4 is controlling and unretrieved; any internal estimate remains internal and cannot be promoted to buyer-facing pricing authority.",
        },
        "owner_decision": normalized["owner_decision"],
        "external_submission_authorized": False,
        "response_spine": _response_spine(),
        "authority": authority,
        "evidence": {
            "registry_sha256": EVIDENCE_REGISTRY_SHA256,
            "official_source_id": official["source_id"],
            "official_source_url": official["url"],
            "observed_at": evidence["observed_at"],
            "limitations": deepcopy(official["limitations"]),
        },
    }
    report = deepcopy(payload)
    report["integrity"] = {
        "packet_sha256": _sha(normalized),
        "evidence_registry_sha256": EVIDENCE_REGISTRY_SHA256,
        "report_payload_sha256": _sha(payload),
    }
    return report


def compile_pursuit(packet: Any) -> dict[str, Any]:
    """Compile a current internal pursuit report. Caller cannot select the clock or evidence root."""
    return _compile_at(packet, _now_utc())


def verify_report(packet: Any, report: Any) -> dict[str, Any]:
    """Verify historical report integrity and report the current deadline state."""
    if not isinstance(report, dict):
        raise ContractError("report must be an object")
    compiled_at = report.get("compiled_at")
    when = _parse_dt(compiled_at)
    expected = _compile_at(packet, when)
    historical_match = expected == report
    evidence = _load_evidence()
    current_deadline = _deadline_state(evidence, _now_utc())
    if not historical_match:
        verdict = "TAMPERED_OR_NONCANONICAL"
    elif current_deadline == "CLOSED":
        verdict = "HISTORICAL_VERIFIED_DEADLINE_CLOSED"
    else:
        verdict = "CURRENT_VERIFIED_INTERNAL_ONLY"
    return {
        "schema": "vct-pursuit-verification/v1",
        "verdict": verdict,
        "historical_match": historical_match,
        "current_deadline_state": current_deadline,
        "external_submission_authorized": False,
        "evidence_registry_sha256": EVIDENCE_REGISTRY_SHA256,
    }


def render_markdown(report: Any) -> str:
    if not isinstance(report, dict) or report.get("schema") != REPORT_SCHEMA:
        raise ContractError("render_markdown requires a compiled vct pursuit report")
    opp = report["opportunity"]
    lines = [
        "# Vancouver Civic Theatres Website Replacement — internal pursuit packet",
        "",
        "> **NOT A SUBMISSION. No buyer contact, portal action, terms acceptance, signature, staffing commitment, or price commitment is authorized by this artifact.**",
        "",
        f"- RFP: `{opp['number']}`",
        f"- Buyer: {opp['buyer']}",
        f"- Close: {opp['closes_at']}",
        f"- Posture: **{report['pursuit_posture']}**",
        f"- Source readiness: **{report['source_readiness']}**",
        f"- Company readiness: **{report['company_readiness']}**",
        "",
        "## Controlling-source blockers",
    ]
    for blocker in report["source_blockers"]:
        lines.append(f"- `{blocker}`")
    if not report["source_blockers"]:
        lines.append("- None")
    lines += ["", "## Company-evidence blockers"]
    for blocker in report["company_blockers"]:
        lines.append(f"- `{blocker}`")
    if not report["company_blockers"]:
        lines.append("- None")
    lines += ["", "## Response spine"]
    for section in report["response_spine"]:
        lines += [f"### {section['section']} — {section['state']}", section["content"], ""]
    lines += [
        "## Commercial guardrail",
        report["commercial"]["note"],
        "",
        "## Authority",
        "Every external-action authority bit is `false`; this carrier is internal research, qualification, drafting, and repository evidence only.",
        "",
        f"Evidence registry SHA-256: `{report['evidence']['registry_sha256']}`",
    ]
    return "\n".join(lines).rstrip() + "\n"

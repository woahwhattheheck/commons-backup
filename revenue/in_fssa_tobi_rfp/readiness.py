from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any

RFP_ID = "26-86873"
EVENT_ID = "004100000086873"
# Addendum 2 and the revised RFP section 1.24, recovered 2026-10-03.
DUE_AT = datetime.fromisoformat("2026-10-08T15:00:00-04:00")
OFFICIAL_BOARD_URL = "https://www.in.gov/idoa/procurement/current-business-opportunities/"

_SECRET_KEY_RE = re.compile(r"(?:password|passwd|secret|api[_-]?key|auth(?:orization)?[_-]?header|bearer|private[_-]?key)", re.I)


class InputError(ValueError):
    pass


class Decision(str, Enum):
    PRIME_READY = "PRIME_READY"
    SUBCONTRACT_READY = "SUBCONTRACT_READY"
    HOLD = "HOLD"
    NO_BID = "NO_BID"


@dataclass(frozen=True)
class Finding:
    code: str
    status: str
    detail: str


@dataclass(frozen=True)
class ReadinessReceipt:
    schema_version: str
    rfp_id: str
    event_id: str
    decision: str
    evaluated_at: str
    due_at: str
    input_digest: str
    findings: tuple[Finding, ...]
    may_contact_buyer: bool = False
    may_submit_bid: bool = False
    may_quote_price: bool = False
    revenue_status: str = "UNREALIZED"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["findings"] = [asdict(x) for x in self.findings]
        return d


def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field}: RFC3339 timestamp required")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError(f"{field}: invalid timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise InputError(f"{field}: timezone offset required")
    return dt


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _reject_secret_shapes(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise InputError(f"{path}: object keys must be strings")
            if _SECRET_KEY_RE.search(key):
                raise InputError(f"{path}.{key}: secret-shaped field is forbidden")
            _reject_secret_shapes(item, f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _reject_secret_shapes(item, f"{path}[{i}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise InputError(f"{path}: non-finite number forbidden")
    elif isinstance(value, str) and len(value) > 4096:
        raise InputError(f"{path}: string too large")


def loads_strict(text: str) -> dict[str, Any]:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in pairs:
            if k in out:
                raise InputError(f"duplicate JSON key: {k}")
            out[k] = v
        return out

    try:
        obj = json.loads(text, object_pairs_hook=hook, parse_constant=lambda x: (_ for _ in ()).throw(InputError(f"non-finite JSON constant: {x}")))
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(obj, dict):
        raise InputError("top-level JSON object required")
    _reject_secret_shapes(obj)
    return obj


def _bool(d: dict[str, Any], key: str) -> bool:
    v = d.get(key)
    return type(v) is bool and v


def _string(d: dict[str, Any], key: str) -> str:
    v = d.get(key)
    return v.strip() if isinstance(v, str) else ""


def _source_findings(data: dict[str, Any], evaluated: datetime) -> tuple[list[Finding], bool]:
    source = data.get("official_source")
    if not isinstance(source, dict):
        return [Finding("OFFICIAL_SOURCE_MISSING", "HOLD", "Official IDOA source evidence is required")], False
    if source.get("url") != OFFICIAL_BOARD_URL:
        return [Finding("OFFICIAL_SOURCE_WRONG", "HOLD", "Source must be the current IDOA business-opportunities board")], False
    if source.get("rfp_id") != RFP_ID or source.get("event_id") != EVENT_ID:
        return [Finding("SOURCE_IDENTITY_MISMATCH", "HOLD", "RFP/event identity does not match Tobi solicitation")], False
    observed = _parse_time(source.get("observed_at"), "official_source.observed_at")
    if observed > evaluated:
        return [Finding("SOURCE_FROM_FUTURE", "HOLD", "Official source observation cannot postdate evaluation")], False
    age = (evaluated.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
    if age > 7 * 86400:
        return [Finding("SOURCE_STALE", "HOLD", "Official source must be rechecked within seven days")], False
    return [Finding("OFFICIAL_SOURCE_CURRENT", "PASS", "Current IDOA board evidence is bound to the exact RFP/event")], True


def _reference_findings(data: dict[str, Any], evaluated: datetime) -> tuple[list[Finding], bool]:
    refs = data.get("references")
    if not isinstance(refs, list):
        return [Finding("REFERENCES_MISSING", "HOLD", "Reference list required for prime readiness")], False
    good = len(refs) >= 3
    seen: set[str] = set()
    for i, ref in enumerate(refs):
        if not isinstance(ref, dict):
            good = False
            continue
        rid = _string(ref, "reference_id")
        if not rid or rid in seen:
            good = False
        seen.add(rid)
        if not (_string(ref, "client") and _string(ref, "contact_name") and _string(ref, "contact_method")):
            good = False
        if not _bool(ref, "permission_confirmed"):
            good = False
        if not (_bool(ref, "case_management_relevant") or _bool(ref, "state_human_services_relevant")):
            good = False
        try:
            if _parse_time(ref.get("observed_at"), f"references[{i}].observed_at") > evaluated:
                good = False
        except InputError:
            good = False
    status = "PASS" if good else "HOLD"
    detail = "At least three unique, permission-confirmed relevant references with contacts" if good else "Need three unique, permission-confirmed relevant client references with contacts"
    return [Finding("THREE_REFERENCES", status, detail)], good


def _capability_findings(data: dict[str, Any]) -> tuple[list[Finding], bool]:
    cap = data.get("capabilities")
    if not isinstance(cap, dict):
        return [Finding("CAPABILITIES_MISSING", "HOLD", "Technical capability evidence required")], False
    findings: list[Finding] = []
    ok = True
    required = {
        "cloud_case_management": "cloud case-management operations",
        "information_security_framework": "Indiana/IOT information-security alignment",
        "accessibility": "accessible user/training experience",
        "provider_management_application": "provider onboarding/tracking capability",
    }
    for key, label in required.items():
        passed = _bool(cap, key)
        findings.append(Finding(f"CAP_{key.upper()}", "PASS" if passed else "HOLD", label))
        ok &= passed
    ints = cap.get("bidirectional_integrations")
    have = {str(x).upper() for x in ints} if isinstance(ints, list) and all(isinstance(x, str) for x in ints) else set()
    int_ok = {"CMHW_PORTAL", "DARMHA", "COREMMIS"}.issubset(have)
    findings.append(Finding("BIDIRECTIONAL_INTEGRATIONS", "PASS" if int_ok else "HOLD", "CMHW Portal, DARMHA and COREMMIS bidirectional integration evidence"))
    ok &= int_ok
    modes = cap.get("training_modes")
    mode_set = {str(x).lower() for x in modes} if isinstance(modes, list) and all(isinstance(x, str) for x in modes) else set()
    training_ok = {"telephone", "virtual", "onsite"}.issubset(mode_set)
    findings.append(Finding("TRAINING_COVERAGE", "PASS" if training_ok else "HOLD", "Telephone, virtual and onsite training coverage"))
    ok &= training_ok
    support = cap.get("help_desk")
    support_ok = isinstance(support, dict) and _string(support, "ticketing").lower() == "jira"
    hours = support.get("response_business_hours") if isinstance(support, dict) else None
    support_ok = support_ok and isinstance(hours, (int, float)) and not isinstance(hours, bool) and math.isfinite(float(hours)) and 0 < float(hours) <= 48
    findings.append(Finding("HELP_DESK_SLA", "PASS" if support_ok else "HOLD", "Jira help desk with response target no slower than 48 business hours"))
    ok &= support_ok
    return findings, ok


def _prime_findings(data: dict[str, Any], evaluated: datetime) -> tuple[list[Finding], bool]:
    findings: list[Finding] = []
    authority = data.get("prime_authority") if isinstance(data.get("prime_authority"), dict) else {}
    for key, detail in (
        ("indiana_registration", "Registered/eligible to do business in Indiana before contract negotiations"),
        ("bidder_database_registration", "Indiana procurement bidder profile/registration evidenced"),
    ):
        passed = _bool(authority, key)
        findings.append(Finding(key.upper(), "PASS" if passed else "HOLD", detail))
    findings.append(Finding("FINANCIAL_RESPONSIBILITY_NOT_REQUIRED", "PASS", "The revised RFP sections 1.25 and 2.3.10 remove evidence of financial responsibility"))
    iv = authority.get("ivosb_plan")
    iv_pct = iv.get("target_percent") if isinstance(iv, dict) else None
    iv_ok = isinstance(iv_pct, (int, float)) and not isinstance(iv_pct, bool) and math.isfinite(float(iv_pct)) and float(iv_pct) >= 3 and _bool(iv, "evidence_backed")
    findings.append(Finding("IVOSB_PLAN", "PASS" if iv_ok else "HOLD", "Evidence-backed plan meets or exceeds the 3% IVOSB participation goal"))
    components = data.get("proposal_components") if isinstance(data.get("proposal_components"), dict) else {}
    needed = ("executive", "business", "technical", "cost", "state_forms", "reference_forms")
    component_ok = all(_bool(components, x) for x in needed)
    findings.append(Finding("PROPOSAL_COMPONENTS", "PASS" if component_ok else "HOLD", "Executive, business, technical, cost, state forms and reference forms are complete"))
    ref_findings, refs_ok = _reference_findings(data, evaluated)
    findings.extend(ref_findings)
    ok = _bool(authority, "indiana_registration") and _bool(authority, "bidder_database_registration") and iv_ok and component_ok and refs_ok
    return findings, ok


def _subcontract_findings(data: dict[str, Any]) -> tuple[list[Finding], bool]:
    sub = data.get("subcontract")
    if not isinstance(sub, dict):
        return [Finding("PRIME_PARTNER", "HOLD", "A named prime partner and bounded subcontract scope are required")], False
    partner_ok = _bool(sub, "prime_partner_confirmed") and bool(_string(sub, "prime_partner_id"))
    scope = sub.get("scope")
    scope_set = {str(x) for x in scope} if isinstance(scope, list) and all(isinstance(x, str) for x in scope) else set()
    allowed = {"integration_mapping", "migration_validation", "qa_automation", "accessibility_qa", "training_materials", "help_desk_automation", "acceptance_evidence"}
    scope_ok = bool(scope_set) and scope_set.issubset(allowed)
    no_prime_claim = not _bool(sub, "represents_prime_qualifications")
    findings = [
        Finding("PRIME_PARTNER", "PASS" if partner_ok else "HOLD", "Named prime partner commitment is evidenced"),
        Finding("BOUNDED_SCOPE", "PASS" if scope_ok else "HOLD", "Subcontract scope stays inside bounded technical/QA/training workstreams"),
        Finding("NO_PRIME_MISREPRESENTATION", "PASS" if no_prime_claim else "HOLD", "Subcontract packet does not claim prime qualifications"),
    ]
    return findings, partner_ok and scope_ok and no_prime_claim


def evaluate(data: dict[str, Any]) -> ReadinessReceipt:
    if not isinstance(data, dict):
        raise InputError("input must be an object")
    _reject_secret_shapes(data)
    if data.get("rfp_id") != RFP_ID or data.get("event_id") != EVENT_ID:
        raise InputError("exact RFP/event identity required")
    role = data.get("role_intent")
    if role not in {"prime", "subcontract", "auto"}:
        raise InputError("role_intent must be prime, subcontract, or auto")
    evaluated = _parse_time(data.get("evaluated_at"), "evaluated_at")
    due = _parse_time(data.get("proposal_due_at"), "proposal_due_at")
    if due != DUE_AT:
        raise InputError("proposal_due_at must match the verified controlling deadline")
    findings: list[Finding] = []
    source_findings, source_ok = _source_findings(data, evaluated)
    findings.extend(source_findings)
    if evaluated >= due:
        findings.append(Finding("DEADLINE", "NO_BID", "Evaluation occurred at or after the proposal deadline"))
        decision = Decision.NO_BID
    else:
        remaining = (due.astimezone(timezone.utc) - evaluated.astimezone(timezone.utc)).total_seconds()
        findings.append(Finding("DEADLINE", "PASS", f"{int(remaining // 3600)} whole hours remain before deadline"))
        cap_findings, caps_ok = _capability_findings(data)
        findings.extend(cap_findings)
        prime_findings, prime_ok = _prime_findings(data, evaluated)
        sub_findings, sub_ok = _subcontract_findings(data)
        if role in {"prime", "auto"}:
            findings.extend(prime_findings)
        if role in {"subcontract", "auto"}:
            findings.extend(sub_findings)
        if not source_ok or not caps_ok:
            decision = Decision.HOLD
        elif role == "prime":
            decision = Decision.PRIME_READY if prime_ok else Decision.HOLD
        elif role == "subcontract":
            decision = Decision.SUBCONTRACT_READY if sub_ok else Decision.HOLD
        else:
            decision = Decision.PRIME_READY if prime_ok else (Decision.SUBCONTRACT_READY if sub_ok else Decision.HOLD)
    return ReadinessReceipt(
        schema_version="tjlabs.in-fssa-tobi-readiness/v1",
        rfp_id=RFP_ID,
        event_id=EVENT_ID,
        decision=decision.value,
        evaluated_at=evaluated.isoformat(),
        due_at=due.isoformat(),
        input_digest=f"sha256:{_digest(data)}",
        findings=tuple(findings),
    )

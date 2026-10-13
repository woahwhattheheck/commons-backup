from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Any

SCHEMA = "procurement-runway-gate-input/v1"
OUTPUT_SCHEMA = "procurement-runway-gate-output/v1"
RECEIPT_SCHEMA = "procurement-runway-gate-receipt/v1"
RUNWAY_STATES = {"READY", "ASK_CAPACITY_FIRST", "TOO_LATE", "UNKNOWN"}
CAPACITY_STATES = {"EXPLICIT_EARLIEST_DATE", "EXPLICIT_LEAD_TIME_DAYS", "UNVERIFIED"}
RELATIONSHIP_STATES = {"CLEAR", "DNR", "INBOUND_ONLY", "UNKNOWN"}
COLLISION_STATES = {"CLEAR", "CLAIMED_ELSEWHERE", "UNKNOWN"}
AUTHORITY_FALSE = {
    "external_send_authorized": False,
    "provider_mutation_authorized": False,
    "submission_authorized": False,
    "payment_or_revenue_inferred": False,
}


class GateError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateError(f"{field} must be an object")
    return value


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise GateError(f"{field} must be an array")
    return value


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GateError(f"{field} must be a non-empty string")
    return value.strip()


def _require_int(value: Any, field: str, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise GateError(f"{field} must be an integer")
    if minimum is not None and value < minimum:
        raise GateError(f"{field} must be >= {minimum}")
    return value


def _parse_date(value: Any, field: str) -> date:
    text = _require_str(value, field)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise GateError(f"{field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != text:
        raise GateError(f"{field} must use canonical YYYY-MM-DD")
    return parsed


def _urls(value: Any, field: str, *, required: bool = True) -> list[str]:
    rows = _require_list(value, field)
    out: list[str] = []
    seen: set[str] = set()
    for idx, raw in enumerate(rows):
        url = _require_str(raw, f"{field}[{idx}]")
        if not (url.startswith("https://") or url.startswith("http://")):
            raise GateError(f"{field}[{idx}] must be http(s)")
        if url in seen:
            raise GateError(f"{field} contains duplicate URL")
        seen.add(url)
        out.append(url)
    if required and not out:
        raise GateError(f"{field} must contain evidence")
    return sorted(out)


def _date_fact(raw: Any, field: str, *, required: bool = False) -> dict[str, Any] | None:
    if raw is None:
        if required:
            raise GateError(f"{field} is required")
        return None
    obj = _require_dict(raw, field)
    allowed = {"date", "label", "evidence_urls"}
    unknown = set(obj) - allowed
    if unknown:
        raise GateError(f"{field} has unknown keys: {sorted(unknown)}")
    parsed = _parse_date(obj.get("date"), f"{field}.date")
    label = _require_str(obj.get("label"), f"{field}.label")
    urls = _urls(obj.get("evidence_urls"), f"{field}.evidence_urls")
    return {"date": parsed.isoformat(), "label": label, "evidence_urls": urls}


def _validate_partner(raw: Any, field: str) -> dict[str, Any]:
    obj = _require_dict(raw, field)
    allowed = {"name", "capability_evidence_urls", "capacity", "conflicts_dnr"}
    unknown = set(obj) - allowed
    if unknown:
        raise GateError(f"{field} has unknown keys: {sorted(unknown)}")
    name = _require_str(obj.get("name"), f"{field}.name")
    capability = _urls(obj.get("capability_evidence_urls"), f"{field}.capability_evidence_urls")
    conflicts = [
        _require_str(v, f"{field}.conflicts_dnr[{i}]")
        for i, v in enumerate(_require_list(obj.get("conflicts_dnr", []), f"{field}.conflicts_dnr"))
    ]
    capacity = _require_dict(obj.get("capacity"), f"{field}.capacity")
    allowed_capacity = {"state", "earliest_date", "lead_time_days", "evidence_urls"}
    unknown_capacity = set(capacity) - allowed_capacity
    if unknown_capacity:
        raise GateError(f"{field}.capacity has unknown keys: {sorted(unknown_capacity)}")
    state = _require_str(capacity.get("state"), f"{field}.capacity.state")
    if state not in CAPACITY_STATES:
        raise GateError(f"{field}.capacity.state invalid")
    earliest: str | None = None
    lead: int | None = None
    evidence = _urls(
        capacity.get("evidence_urls", []),
        f"{field}.capacity.evidence_urls",
        required=state != "UNVERIFIED",
    )
    if state == "EXPLICIT_EARLIEST_DATE":
        earliest = _parse_date(capacity.get("earliest_date"), f"{field}.capacity.earliest_date").isoformat()
        if "lead_time_days" in capacity and capacity.get("lead_time_days") is not None:
            raise GateError(f"{field}.capacity.lead_time_days forbidden for EXPLICIT_EARLIEST_DATE")
    elif state == "EXPLICIT_LEAD_TIME_DAYS":
        lead = _require_int(capacity.get("lead_time_days"), f"{field}.capacity.lead_time_days", 0)
        if "earliest_date" in capacity and capacity.get("earliest_date") is not None:
            raise GateError(f"{field}.capacity.earliest_date forbidden for EXPLICIT_LEAD_TIME_DAYS")
    else:
        if capacity.get("earliest_date") is not None or capacity.get("lead_time_days") is not None:
            raise GateError(f"{field}.capacity UNVERIFIED cannot carry invented timing")
        if evidence:
            raise GateError(f"{field}.capacity UNVERIFIED cannot label evidence as capacity evidence")
    return {
        "name": name,
        "capability_evidence_urls": capability,
        "capacity": {
            "state": state,
            "earliest_date": earliest,
            "lead_time_days": lead,
            "evidence_urls": evidence,
        },
        "conflicts_dnr": sorted(set(conflicts)),
    }


def _validate_workshare(raw: Any, field: str) -> dict[str, Any]:
    obj = _require_dict(raw, field)
    allowed = {"fixed_fee_minor", "currency", "scope", "acceptance_criteria", "exclusions"}
    unknown = set(obj) - allowed
    if unknown:
        raise GateError(f"{field} has unknown keys: {sorted(unknown)}")
    fee = _require_int(obj.get("fixed_fee_minor"), f"{field}.fixed_fee_minor", 1)
    currency = _require_str(obj.get("currency"), f"{field}.currency")
    if len(currency) != 3 or currency.upper() != currency or not currency.isalpha():
        raise GateError(f"{field}.currency must be uppercase ISO-like 3-letter code")
    scope = _require_str(obj.get("scope"), f"{field}.scope")
    acceptance = [
        _require_str(v, f"{field}.acceptance_criteria[{i}]")
        for i, v in enumerate(_require_list(obj.get("acceptance_criteria"), f"{field}.acceptance_criteria"))
    ]
    if not acceptance:
        raise GateError(f"{field}.acceptance_criteria must not be empty")
    exclusions = [
        _require_str(v, f"{field}.exclusions[{i}]")
        for i, v in enumerate(_require_list(obj.get("exclusions", []), f"{field}.exclusions"))
    ]
    return {
        "fixed_fee_minor": fee,
        "currency": currency,
        "scope": scope,
        "acceptance_criteria": acceptance,
        "exclusions": exclusions,
    }


def validate_input(raw: Any) -> dict[str, Any]:
    doc = _require_dict(raw, "input")
    allowed = {"schema", "as_of", "opportunities"}
    unknown = set(doc) - allowed
    if unknown:
        raise GateError(f"input has unknown keys: {sorted(unknown)}")
    if doc.get("schema") != SCHEMA:
        raise GateError(f"schema must be {SCHEMA}")
    as_of = _parse_date(doc.get("as_of"), "as_of")
    rows = _require_list(doc.get("opportunities"), "opportunities")
    if not rows:
        raise GateError("opportunities must not be empty")
    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    for idx, raw_opp in enumerate(rows):
        field = f"opportunities[{idx}]"
        opp = _require_dict(raw_opp, field)
        allowed_opp = {
            "id", "buyer", "source_urls", "dates", "mandatory_delivery_window_days",
            "partners", "workshare", "relationship_state", "collision_state",
        }
        unknown_opp = set(opp) - allowed_opp
        if unknown_opp:
            raise GateError(f"{field} has unknown keys: {sorted(unknown_opp)}")
        oid = _require_str(opp.get("id"), f"{field}.id")
        if oid in ids:
            raise GateError(f"duplicate opportunity id: {oid}")
        ids.add(oid)
        buyer = _require_str(opp.get("buyer"), f"{field}.buyer")
        source_urls = _urls(opp.get("source_urls"), f"{field}.source_urls")
        dates = _require_dict(opp.get("dates"), f"{field}.dates")
        allowed_dates = {
            "issue", "questions_due", "prebid", "proposal_due",
            "anticipated_award", "start", "go_live",
        }
        unknown_dates = set(dates) - allowed_dates
        if unknown_dates:
            raise GateError(f"{field}.dates has unknown keys: {sorted(unknown_dates)}")
        norm_dates = {
            "issue": _date_fact(dates.get("issue"), f"{field}.dates.issue"),
            "questions_due": _date_fact(dates.get("questions_due"), f"{field}.dates.questions_due"),
            "prebid": _date_fact(dates.get("prebid"), f"{field}.dates.prebid"),
            "proposal_due": _date_fact(dates.get("proposal_due"), f"{field}.dates.proposal_due", required=True),
            "anticipated_award": _date_fact(dates.get("anticipated_award"), f"{field}.dates.anticipated_award"),
            "start": _date_fact(dates.get("start"), f"{field}.dates.start"),
            "go_live": _date_fact(dates.get("go_live"), f"{field}.dates.go_live"),
        }
        mdw = opp.get("mandatory_delivery_window_days")
        if mdw is not None:
            mdw = _require_int(mdw, f"{field}.mandatory_delivery_window_days", 1)
        partners = [
            _validate_partner(v, f"{field}.partners[{i}]")
            for i, v in enumerate(_require_list(opp.get("partners"), f"{field}.partners"))
        ]
        partner_names = [p["name"].casefold() for p in partners]
        if len(partner_names) != len(set(partner_names)):
            raise GateError(f"{field}.partners contains duplicate names")
        relationship = _require_str(opp.get("relationship_state"), f"{field}.relationship_state")
        if relationship not in RELATIONSHIP_STATES:
            raise GateError(f"{field}.relationship_state invalid")
        collision = _require_str(opp.get("collision_state"), f"{field}.collision_state")
        if collision not in COLLISION_STATES:
            raise GateError(f"{field}.collision_state invalid")
        normalized.append({
            "id": oid,
            "buyer": buyer,
            "source_urls": source_urls,
            "dates": norm_dates,
            "mandatory_delivery_window_days": mdw,
            "partners": sorted(partners, key=lambda p: (p["name"].casefold(), p["name"])),
            "workshare": _validate_workshare(opp.get("workshare"), f"{field}.workshare"),
            "relationship_state": relationship,
            "collision_state": collision,
        })
    return {
        "schema": SCHEMA,
        "as_of": as_of.isoformat(),
        "opportunities": sorted(normalized, key=lambda r: r["id"]),
    }


def _target_date(opp: dict[str, Any]) -> date | None:
    for key in ("start", "go_live"):
        fact = opp["dates"].get(key)
        if fact:
            return date.fromisoformat(fact["date"])
    award = opp["dates"].get("anticipated_award")
    days = opp.get("mandatory_delivery_window_days")
    if award and days is not None:
        return date.fromisoformat(award["date"]) + timedelta(days=days)
    return None


def _partner_timing(partner: dict[str, Any], as_of: date, target: date | None) -> tuple[str, str]:
    cap = partner["capacity"]
    state = cap["state"]
    if state == "UNVERIFIED":
        return "UNKNOWN_CAPACITY", "public capability evidence does not establish delivery availability"
    if state == "EXPLICIT_EARLIEST_DATE":
        earliest = date.fromisoformat(cap["earliest_date"])
    else:
        earliest = as_of + timedelta(days=cap["lead_time_days"])
    if target is not None and earliest > target:
        return "EXPLICIT_MISS", f"evidenced earliest feasible date {earliest.isoformat()} is after target {target.isoformat()}"
    if target is None:
        return "EXPLICIT_NO_KNOWN_CONFLICT", f"capacity evidence implies earliest {earliest.isoformat()}; no mandatory target date is evidenced"
    return "EXPLICIT_FIT", f"capacity evidence implies earliest {earliest.isoformat()} on/before target {target.isoformat()}"


def _contact_state(opp: dict[str, Any]) -> str:
    if opp["relationship_state"] == "DNR":
        return "HOLD_DNR"
    if opp["relationship_state"] == "INBOUND_ONLY":
        return "WAIT_INBOUND"
    if opp["relationship_state"] != "CLEAR":
        return "HOLD_RELATIONSHIP_UNKNOWN"
    if opp["collision_state"] == "CLAIMED_ELSEWHERE":
        return "HOLD_COLLISION"
    if opp["collision_state"] != "CLEAR":
        return "HOLD_COLLISION_UNKNOWN"
    return "ELIGIBLE_FOR_SEPARATE_MUSE_ELECTION_ONLY"


def _score_opportunity(opp: dict[str, Any], as_of: date) -> dict[str, Any]:
    proposal_due = date.fromisoformat(opp["dates"]["proposal_due"]["date"])
    target = _target_date(opp)
    partner_rows: list[dict[str, Any]] = []
    statuses: list[str] = []
    for p in opp["partners"]:
        status, reason = _partner_timing(p, as_of, target)
        statuses.append(status)
        partner_rows.append({
            "name": p["name"],
            "timing_status": status,
            "timing_reason": reason,
            "capability_evidence_urls": p["capability_evidence_urls"],
            "capacity": p["capacity"],
            "conflicts_dnr": p["conflicts_dnr"],
        })

    if proposal_due <= as_of:
        runway = "TOO_LATE"
        reason = f"proposal due {proposal_due.isoformat()} is not after as_of {as_of.isoformat()}"
    elif not partner_rows:
        runway = "UNKNOWN"
        reason = "no plausible partner is bound to evidence"
    elif any(s in {"EXPLICIT_FIT", "EXPLICIT_NO_KNOWN_CONFLICT"} for s in statuses):
        runway = "READY"
        reason = "at least one partner has explicit capacity evidence with no known timing conflict"
    elif any(s == "UNKNOWN_CAPACITY" for s in statuses):
        runway = "ASK_CAPACITY_FIRST"
        reason = "partner capability is evidenced but public availability is not"
    else:
        runway = "TOO_LATE"
        reason = "all evidenced partner capacity misses the known delivery target"

    selected = partner_rows[:3] if runway in {"READY", "ASK_CAPACITY_FIRST"} else []
    return {
        "id": opp["id"],
        "buyer": opp["buyer"],
        "runway_state": runway,
        "runway_reason": reason,
        "proposal_due": opp["dates"]["proposal_due"],
        "target_date": target.isoformat() if target else None,
        "known_dates": opp["dates"],
        "source_urls": opp["source_urls"],
        "selected_partners": selected,
        "contact_state": _contact_state(opp),
        "workshare": opp["workshare"],
        **AUTHORITY_FALSE,
    }


def compile_gate(raw: Any) -> dict[str, Any]:
    doc = validate_input(raw)
    as_of = date.fromisoformat(doc["as_of"])
    rows = [_score_opportunity(opp, as_of) for opp in doc["opportunities"]]
    counts = {state: 0 for state in sorted(RUNWAY_STATES)}
    for row in rows:
        counts[row["runway_state"]] += 1
    return {
        "schema": OUTPUT_SCHEMA,
        "input_schema": SCHEMA,
        "as_of": doc["as_of"],
        "opportunities": rows,
        "summary": counts,
        **AUTHORITY_FALSE,
    }


def make_receipt(output: dict[str, Any]) -> dict[str, Any]:
    output_bytes = canonical_json_bytes(output)
    return {
        "schema": RECEIPT_SCHEMA,
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "output_bytes": len(output_bytes),
        **AUTHORITY_FALSE,
    }


def verify_bundle(raw_input: Any, output: Any, receipt: Any) -> None:
    expected = compile_gate(raw_input)
    if output != expected:
        raise GateError("output does not match deterministic recompilation")
    expected_receipt = make_receipt(expected)
    if receipt != expected_receipt:
        raise GateError("receipt does not match output")

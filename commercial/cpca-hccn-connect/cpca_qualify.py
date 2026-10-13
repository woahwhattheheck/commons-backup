#!/usr/bin/env python3
"""Deterministic truth-bound qualifier for CPCA HCCN Connect.

This tool never invents experience, pricing, signatures, references, or submission
state. It evaluates caller-supplied evidence against a source-bound gate spec.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

ALLOWED_GATE_STATUS = {"PROVEN", "PARTNER_CURABLE", "MISSING", "HOLD", "NOT_APPLICABLE"}
FINAL_STATES = {"PRIME_READY", "TEAMING_READY", "HOLD", "NO_BID"}
DERIVED_SOURCE_GATES = {"client_references", "recent_domain_engagements", "safety_net_experience"}
COMPLETED_STATES = {"COMPLETED", "SUBSTANTIALLY_COMPLETED"}
RELEVANT_ENGAGEMENT_STATES = COMPLETED_STATES | {"ACTIVE", "PILOT"}


def _load(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level JSON must be an object")
    return value


def _parse_when(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("current_time must contain an explicit UTC offset")
    return parsed


def _required_gate_ids(spec: Dict[str, Any], service_type: str) -> List[str]:
    all_ids = [g["id"] for g in spec["mandatory_direct_prime_gates"]]
    specific = set(spec["service_type_specific_gate_ids"][service_type])
    track_ids = {"technical_assistance_track_record", "group_training_track_record"}
    return [gid for gid in all_ids if gid not in track_ids or gid in specific]


def _validate_source(spec: Dict[str, Any], evidence: Dict[str, Any]) -> None:
    source = evidence.get("source_packet", {})
    expected = spec["source_packet"]
    for key in ("gmail_message_id", "filename", "sha256"):
        if source.get(key) != expected.get(key):
            raise ValueError(
                f"source packet mismatch for {key}: expected {expected.get(key)!r}, "
                f"got {source.get(key)!r}"
            )


def _status_map(evidence: Dict[str, Any]) -> Dict[str, str]:
    raw = evidence.get("gate_status", {})
    if not isinstance(raw, dict):
        raise ValueError("gate_status must be an object")
    out: Dict[str, str] = {}
    for key, value in raw.items():
        if value not in ALLOWED_GATE_STATUS:
            raise ValueError(f"invalid gate status {value!r} for {key}")
        out[str(key)] = str(value)
    return out


def _validate_proven_gate_sources(status: Dict[str, str], evidence: Dict[str, Any]) -> None:
    sources = evidence.get("gate_sources", {})
    if not isinstance(sources, dict):
        raise ValueError("gate_sources must be an object")
    for gate_id, gate_status in status.items():
        if gate_status != "PROVEN" or gate_id in DERIVED_SOURCE_GATES:
            continue
        bound = sources.get(gate_id)
        if isinstance(bound, str):
            bound = [bound] if bound.strip() else []
        if not isinstance(bound, list) or not bound or not all(isinstance(x, str) and x.strip() for x in bound):
            raise ValueError(f"{gate_id} cannot be PROVEN without >=1 bound source")


def _reference_identity(row: Dict[str, Any]) -> str | None:
    for key in ("reference_id", "name"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _engagement_domains(row: Dict[str, Any]) -> set[str]:
    raw = row.get("domains", [])
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if isinstance(x, str) and x.strip()}


def _engagement_date(row: Dict[str, Any]) -> dt.date | None:
    raw = row.get("completed_at", row.get("end_date"))
    if not isinstance(raw, str):
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


def _years_ago(day: dt.date, years: int) -> dt.date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        # February 29 -> February 28 in a non-leap target year.
        return day.replace(year=day.year - years, day=28)


def _engagement_identity(row: Dict[str, Any]) -> str | None:
    for key in ("engagement_id", "source"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _derive_count_gates(
    status: Dict[str, str],
    evidence: Dict[str, Any],
    domain: str,
    domain_meta: Dict[str, Any],
    now: dt.datetime,
) -> None:
    refs = evidence.get("client_references", [])
    if not isinstance(refs, list):
        raise ValueError("client_references must be a list")
    reference_ids = {
        identity
        for row in refs
        if isinstance(row, dict) and row.get("source") and (identity := _reference_identity(row))
    }
    if len(reference_ids) >= 3:
        status["client_references"] = "PROVEN"
    elif status.get("client_references") == "PROVEN":
        raise ValueError("client_references cannot be PROVEN without >=3 distinct source-bound references")

    engagements = evidence.get("comparable_engagements", [])
    if not isinstance(engagements, list):
        raise ValueError("comparable_engagements must be a list")
    relevant_by_id: Dict[str, Dict[str, Any]] = {}
    for row in engagements:
        if (
            not isinstance(row, dict)
            or not row.get("source")
            or domain not in _engagement_domains(row)
            or row.get("state") not in RELEVANT_ENGAGEMENT_STATES
        ):
            continue
        identity = _engagement_identity(row)
        if identity is None:
            continue
        if identity in relevant_by_id:
            raise ValueError(f"duplicate comparable engagement identity: {identity}")
        relevant_by_id[identity] = row
    relevant = list(relevant_by_id.values())

    rule = domain_meta.get("comparable_rule")
    if not isinstance(rule, dict):
        raise ValueError(f"domain {domain!r} missing comparable_rule")
    kind = rule.get("kind")
    today = now.astimezone(dt.timezone.utc).date()
    if kind == "emerging":
        window_years = rule.get("recent_window_years")
        recent_min = rule.get("recent_completed_min")
        total_min = rule.get("total_relevant_min")
        if not all(isinstance(x, int) and x > 0 for x in (window_years, recent_min, total_min)):
            raise ValueError(f"domain {domain!r} has malformed emerging comparable_rule")
        cutoff = _years_ago(today, window_years)
        recent_completed = [
            row
            for row in relevant
            if row.get("state") in COMPLETED_STATES
            and (ended := _engagement_date(row)) is not None
            and cutoff <= ended <= today
        ]
        recent_ok = len(recent_completed) >= recent_min and len(relevant) >= total_min
    elif kind == "established":
        window_years = rule.get("lookback_years")
        completed_min = rule.get("completed_min")
        if not all(isinstance(x, int) and x > 0 for x in (window_years, completed_min)):
            raise ValueError(f"domain {domain!r} has malformed established comparable_rule")
        cutoff = _years_ago(today, window_years)
        completed_only = [
            row
            for row in relevant
            if row.get("state") == "COMPLETED"
            and (ended := _engagement_date(row)) is not None
            and cutoff <= ended <= today
        ]
        recent_ok = len(completed_only) >= completed_min
    else:
        raise ValueError(f"domain {domain!r} has unsupported comparable_rule kind {kind!r}")
    if recent_ok:
        status["recent_domain_engagements"] = "PROVEN"
    elif status.get("recent_domain_engagements") == "PROVEN":
        raise ValueError(
            "recent_domain_engagements cannot be PROVEN without selected-domain, source-bound minimum counts inside the buyer lookback window"
        )

    safety_net = [row for row in relevant if row.get("safety_net_primary_care") is True]
    if safety_net:
        status["safety_net_experience"] = "PROVEN"
    elif status.get("safety_net_experience") == "PROVEN":
        raise ValueError(
            "safety_net_experience cannot be PROVEN without a selected-domain, source-bound safety-net comparable engagement"
        )


def evaluate(spec: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
    _validate_source(spec, evidence)
    service_type = evidence.get("service_type")
    if service_type not in spec["service_type_specific_gate_ids"]:
        raise ValueError(f"unsupported service_type: {service_type!r}")
    domain = evidence.get("domain")
    if domain not in spec["domains"]:
        raise ValueError(f"unsupported domain: {domain!r}")

    now = _parse_when(evidence["current_time"])
    due = dt.datetime.fromisoformat(spec["opportunity"]["due_at"])
    if now > due:
        return {
            "schema": "cpca-hccn-qualification-result/v1",
            "state": "NO_BID",
            "reason": "deadline_passed",
            "due_at": due.isoformat(),
            "evaluated_at": now.isoformat(),
            "blockers": [],
        }

    status = _status_map(evidence)
    _derive_count_gates(status, evidence, domain, spec["domains"][domain], now)
    _validate_proven_gate_sources(status, evidence)
    required_ids = _required_gate_ids(spec, service_type)
    normalized = {gid: status.get(gid, "MISSING") for gid in required_ids}
    blockers = [gid for gid, st in normalized.items() if st != "PROVEN"]

    bid_model = evidence.get("bid_model", "direct_prime")
    if bid_model == "direct_prime":
        state = "PRIME_READY" if not blockers else "HOLD"
        reason = "all_direct_prime_gates_proven" if not blockers else "unproven_direct_prime_gates"
    elif bid_model == "healthcare_prime_subcontract":
        prime = evidence.get("healthcare_prime", {})
        prime_ok = bool(
            prime.get("name")
            and prime.get("eligibility_source")
            and prime.get("safety_net_experience_source")
            and prime.get("relationship_authority") is True
        )
        support_ids = set(evidence.get("tjlabs_support_gate_ids", []))
        unsupported = [gid for gid in support_ids if normalized.get(gid, "MISSING") != "PROVEN"]
        if prime_ok and support_ids and not unsupported:
            state = "TEAMING_READY"
            reason = "named_healthcare_prime_and_support_scope_proven"
        else:
            state = "HOLD"
            reason = "teaming_prime_or_support_scope_unproven"
            if not prime_ok:
                blockers.append("named_healthcare_prime")
            blockers.extend(f"support:{gid}" for gid in unsupported)
    else:
        raise ValueError(f"unsupported bid_model: {bid_model!r}")

    result = {
        "schema": "cpca-hccn-qualification-result/v1",
        "state": state,
        "reason": reason,
        "domain": domain,
        "service_type": service_type,
        "bid_model": bid_model,
        "due_at": due.isoformat(),
        "evaluated_at": now.isoformat(),
        "gate_status": normalized,
        "blockers": sorted(set(blockers)),
        "authority": {
            "buyer_contact_authorized": False,
            "price_committed": False,
            "attestation_signed": False,
            "proposal_submitted": False,
            "award_claimed": False,
            "payment_claimed": False,
            "revenue_claimed": False
        }
    }
    assert result["state"] in FINAL_STATES
    return result


def canonical_digest(value: Dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--spec", type=Path, default=Path(__file__).with_name("qualification_spec.json"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)

    spec = _load(args.spec)
    evidence = _load(args.evidence)
    result = evaluate(spec, evidence)
    result["receipt_sha256"] = canonical_digest(result)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

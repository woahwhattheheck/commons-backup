"""Deterministic, authority-negative TPRM evidence engine.

This is a reference implementation for multi-tenant third-party risk workflows.
It does not assert compliance, currentness, procurement eligibility, or authority.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime
from typing import Any

ASSESSMENT_SCHEMA = "tjlabs.nm-ocs-tprm.assessment.v1"
PACKET_SCHEMA = "tjlabs.nm-ocs-tprm.packet.v1"
PORTFOLIO_SCHEMA = "tjlabs.nm-ocs-tprm.portfolio.v1"
PORTFOLIO_PACKET_SCHEMA = "tjlabs.nm-ocs-tprm.portfolio-packet.v1"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?Z"
)
_CONTROL_STATUS = {"SATISFIED", "GAP", "UNKNOWN"}
_EVENT_KIND = {
    "VULNERABILITY",
    "ATTACK_SURFACE",
    "INCIDENT_NOTICE",
    "CERTIFICATE",
    "OWNERSHIP_CHANGE",
    "MANUAL_REVIEW",
}
_FACTOR_KEYS = ("data_sensitivity", "privilege", "criticality", "internet_exposure")


class ValidationError(ValueError):
    """Input or packet failed the bounded reference contract."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"not canonical-json-safe: {exc}") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _exact_keys(value: Any, expected: set[str], where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{where} must be object")
    if any(type(key) is not str for key in value):
        raise ValidationError(f"{where} keys must be strings")
    got = set(value)
    if got != expected:
        raise ValidationError(
            f"{where} keys mismatch: missing={sorted(expected-got)} extra={sorted(got-expected)}"
        )
    return value


def _id(value: Any, where: str) -> str:
    if type(value) is not str or not _ID_RE.fullmatch(value):
        raise ValidationError(f"{where} must be bounded identifier")
    return value


def _text(value: Any, where: str, *, max_len: int = 512) -> str:
    if type(value) is not str or not value or len(value) > max_len or "\x00" in value:
        raise ValidationError(f"{where} must be non-empty bounded text")
    return value


def _sha256(value: Any, where: str) -> str:
    if type(value) is not str or not _SHA_RE.fullmatch(value):
        raise ValidationError(f"{where} must be lowercase sha256")
    return value


def _utc(value: Any, where: str) -> str:
    if type(value) is not str or len(value) > 40 or not _UTC_RE.fullmatch(value):
        raise ValidationError(f"{where} must be RFC3339 UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValidationError(f"{where} invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValidationError(f"{where} must be UTC")
    return value


def _utc_instant(value: str) -> tuple[datetime, str]:
    # _utc has validated a maximum 40-character Z timestamp. That leaves at
    # most 19 fractional digits. Compare all of them instead of letting
    # datetime silently truncate sub-microsecond evidence chronology.
    whole, separator, fraction = value[:-1].partition(".")
    second = datetime.fromisoformat(whole + "+00:00")
    return second, (fraction if separator else "").ljust(19, "0")


def _factor(value: Any, where: str) -> int:
    if type(value) is not int or value < 0 or value > 3:
        raise ValidationError(f"{where} must be integer 0..3")
    return value


def _tier(factors: dict[str, int]) -> str:
    """Reference triage tier, not a risk/compliance conclusion."""
    total = sum(factors.values())
    maximum = max(factors.values())
    if total >= 10 or (maximum == 3 and total >= 8):
        return "TIER_1"
    if total >= 6:
        return "TIER_2"
    return "TIER_3"


def normalize_assessment(payload: Any) -> dict[str, Any]:
    p = copy.deepcopy(payload)
    _exact_keys(
        p,
        {
            "schema",
            "tenant",
            "vendor",
            "factors",
            "controls",
            "monitoring_events",
            "assessment",
        },
        "assessment",
    )
    if p["schema"] != ASSESSMENT_SCHEMA:
        raise ValidationError("unsupported assessment schema")

    tenant = _exact_keys(p["tenant"], {"tenant_id", "display_name"}, "tenant")
    tenant["tenant_id"] = _id(tenant["tenant_id"], "tenant.tenant_id")
    tenant["display_name"] = _text(tenant["display_name"], "tenant.display_name", max_len=160)

    vendor = _exact_keys(p["vendor"], {"vendor_id", "display_name"}, "vendor")
    vendor["vendor_id"] = _id(vendor["vendor_id"], "vendor.vendor_id")
    vendor["display_name"] = _text(vendor["display_name"], "vendor.display_name", max_len=160)

    factors = _exact_keys(p["factors"], set(_FACTOR_KEYS), "factors")
    for key in _FACTOR_KEYS:
        factors[key] = _factor(factors[key], f"factors.{key}")

    if type(p["controls"]) is not list or len(p["controls"]) > 512:
        raise ValidationError("controls must be list <=512")
    seen_controls: set[tuple[str, str]] = set()
    controls: list[dict[str, Any]] = []
    for i, raw in enumerate(p["controls"]):
        c = _exact_keys(
            raw,
            {"framework", "control_id", "status", "evidence_sha256", "note"},
            f"controls[{i}]",
        )
        framework = _id(c["framework"], f"controls[{i}].framework")
        control_id = _id(c["control_id"], f"controls[{i}].control_id")
        key = (framework, control_id)
        if key in seen_controls:
            raise ValidationError("duplicate control identity")
        seen_controls.add(key)
        status = c["status"]
        if type(status) is not str or status not in _CONTROL_STATUS:
            raise ValidationError(f"controls[{i}].status unsupported")
        evidence = c["evidence_sha256"]
        if evidence is not None:
            evidence = _sha256(evidence, f"controls[{i}].evidence_sha256")
        if status == "SATISFIED" and evidence is None:
            raise ValidationError("SATISFIED control requires evidence digest")
        note = _text(c["note"], f"controls[{i}].note", max_len=512)
        controls.append(
            {
                "framework": framework,
                "control_id": control_id,
                "status": status,
                "evidence_sha256": evidence,
                "note": note,
            }
        )
    controls.sort(key=lambda c: (c["framework"], c["control_id"]))

    if type(p["monitoring_events"]) is not list or len(p["monitoring_events"]) > 1024:
        raise ValidationError("monitoring_events must be list <=1024")
    seen_events: set[str] = set()
    events: list[dict[str, Any]] = []
    for i, raw in enumerate(p["monitoring_events"]):
        e = _exact_keys(
            raw,
            {"event_id", "observed_at", "kind", "severity", "evidence_sha256", "summary"},
            f"monitoring_events[{i}]",
        )
        event_id = _id(e["event_id"], f"monitoring_events[{i}].event_id")
        if event_id in seen_events:
            raise ValidationError("duplicate event_id")
        seen_events.add(event_id)
        observed = _utc(e["observed_at"], f"monitoring_events[{i}].observed_at")
        kind = e["kind"]
        if type(kind) is not str or kind not in _EVENT_KIND:
            raise ValidationError(f"monitoring_events[{i}].kind unsupported")
        severity = e["severity"]
        if type(severity) is not int or severity < 0 or severity > 4:
            raise ValidationError("event severity must be integer 0..4")
        events.append(
            {
                "event_id": event_id,
                "observed_at": observed,
                "kind": kind,
                "severity": severity,
                "evidence_sha256": _sha256(
                    e["evidence_sha256"], f"monitoring_events[{i}].evidence_sha256"
                ),
                "summary": _text(e["summary"], f"monitoring_events[{i}].summary", max_len=512),
            }
        )
    events.sort(key=lambda e: (e["observed_at"], e["event_id"]))

    assessment = _exact_keys(
        p["assessment"], {"as_of", "review_id", "policy_id"}, "assessment"
    )
    as_of = _utc(assessment["as_of"], "assessment.as_of")
    review_id = _id(assessment["review_id"], "assessment.review_id")
    policy_id = _id(assessment["policy_id"], "assessment.policy_id")
    cutoff = _utc_instant(as_of)
    for event in events:
        if _utc_instant(event["observed_at"]) > cutoff:
            raise ValidationError("monitoring event after assessment.as_of")

    return {
        "schema": ASSESSMENT_SCHEMA,
        "tenant": tenant,
        "vendor": vendor,
        "factors": {k: factors[k] for k in _FACTOR_KEYS},
        "controls": controls,
        "monitoring_events": events,
        "assessment": {"as_of": as_of, "review_id": review_id, "policy_id": policy_id},
    }


def compile_assessment(payload: Any) -> dict[str, Any]:
    source = normalize_assessment(payload)
    counts = {status: 0 for status in sorted(_CONTROL_STATUS)}
    findings: list[dict[str, Any]] = []
    for control in source["controls"]:
        counts[control["status"]] += 1
        if control["status"] != "SATISFIED":
            findings.append(
                {
                    "kind": "CONTROL_" + control["status"],
                    "framework": control["framework"],
                    "control_id": control["control_id"],
                }
            )
    for event in source["monitoring_events"]:
        if event["severity"] >= 3:
            findings.append(
                {
                    "kind": "MONITORING_EVENT",
                    "event_id": event["event_id"],
                    "severity": event["severity"],
                }
            )
    findings.sort(key=lambda f: _canonical_bytes(f))

    core = {
        "schema": PACKET_SCHEMA,
        "source": source,
        "reference_tier": _tier(source["factors"]),
        "control_status_counts": counts,
        "findings": findings,
        "authority": {
            "compliance_claimed": False,
            "currentness_claimed": False,
            "procurement_eligibility_claimed": False,
            "submission_authorized": False,
            "external_action_authorized": False,
        },
    }
    return {**core, "receipt_sha256": _sha(core)}


def verify_assessment_packet(packet: Any) -> bool:
    if type(packet) is not dict or set(packet) != {
        "schema",
        "source",
        "reference_tier",
        "control_status_counts",
        "findings",
        "authority",
        "receipt_sha256",
    }:
        return False
    try:
        expected = compile_assessment(packet["source"])
        return _canonical_bytes(packet) == _canonical_bytes(expected)
    except (ValidationError, TypeError, ValueError, OverflowError, RecursionError):
        return False


def compile_portfolio(payload: Any) -> dict[str, Any]:
    p = copy.deepcopy(payload)
    _exact_keys(p, {"schema", "portfolio_id", "assessments"}, "portfolio")
    if p["schema"] != PORTFOLIO_SCHEMA:
        raise ValidationError("unsupported portfolio schema")
    portfolio_id = _id(p["portfolio_id"], "portfolio.portfolio_id")
    if type(p["assessments"]) is not list or not p["assessments"] or len(p["assessments"]) > 2048:
        raise ValidationError("assessments must be non-empty list <=2048")

    compiled: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    by_tenant: dict[str, list[dict[str, Any]]] = {}
    for raw in p["assessments"]:
        packet = compile_assessment(raw)
        key = (packet["source"]["tenant"]["tenant_id"], packet["source"]["vendor"]["vendor_id"])
        if key in seen:
            raise ValidationError("duplicate tenant/vendor assessment")
        seen.add(key)
        compiled.append(packet)
        by_tenant.setdefault(key[0], []).append(packet)

    compiled.sort(
        key=lambda packet: (
            packet["source"]["tenant"]["tenant_id"],
            packet["source"]["vendor"]["vendor_id"],
        )
    )
    tenant_roots = []
    for tenant_id in sorted(by_tenant):
        members = sorted(
            by_tenant[tenant_id],
            key=lambda packet: packet["source"]["vendor"]["vendor_id"],
        )
        tenant_roots.append(
            {
                "tenant_id": tenant_id,
                "assessment_receipts": [m["receipt_sha256"] for m in members],
                "tenant_root_sha256": _sha([m["receipt_sha256"] for m in members]),
            }
        )

    core = {
        "schema": PORTFOLIO_PACKET_SCHEMA,
        "portfolio_id": portfolio_id,
        "assessments": compiled,
        "tenant_roots": tenant_roots,
        "authority": {
            "cross_tenant_data_merge_authorized": False,
            "compliance_claimed": False,
            "submission_authorized": False,
        },
    }
    return {**core, "portfolio_root_sha256": _sha(core)}


def verify_portfolio_packet(packet: Any) -> bool:
    if type(packet) is not dict:
        return False
    try:
        source = {
            "schema": PORTFOLIO_SCHEMA,
            "portfolio_id": packet["portfolio_id"],
            "assessments": [p["source"] for p in packet["assessments"]],
        }
        expected = compile_portfolio(source)
        return _canonical_bytes(packet) == _canonical_bytes(expected)
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        return False

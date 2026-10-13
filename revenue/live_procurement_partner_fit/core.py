"""Deterministic pre-Muse qualification for live-procurement partner outreach.

This module is deliberately authority-negative: it can only return READY_FOR_MUSE
or HOLD. It cannot authorize an external send, provider mutation, payment,
submission, or revenue claim.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlparse

SCHEMA_VERSION = "live-procurement-partner-fit/v1"

OPPORTUNITY_MAX_AGE = timedelta(days=7)
PARTNER_FIT_MAX_AGE = timedelta(days=30)
RUNWAY_EVIDENCE_MAX_AGE = timedelta(days=30)
ROUTE_MAX_AGE = timedelta(days=30)
COLLISION_MAX_AGE = timedelta(hours=4)

_TOP_KEYS = frozenset({"opportunity", "workshare", "partner_fit", "delivery_runway", "route", "collision"})
_OPPORTUNITY_KEYS = frozenset({"opportunity_id", "buyer", "source_url", "observed_at", "submission_deadline_at", "delivery_start_at"})
_WORKSHARE_KEYS = frozenset({"source_repository", "source_path", "source_commit", "landed", "commercial_state", "role_statement", "deliverables", "acceptance_criteria"})
_PARTNER_FIT_KEYS = frozenset({"organization", "evidence_url", "observed_at", "fit_statement"})
_RUNWAY_KEYS = frozenset({"minimum_lead_days", "evidence_url", "observed_at"})
_ROUTE_KEYS = frozenset({"organization", "route", "kind", "evidence_url", "observed_at", "provenance", "state"})
_COLLISION_KEYS = frozenset({"buyer", "opportunity_id", "organization", "route", "purpose", "state", "observed_at", "evidence_refs"})

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+?[0-9][0-9 ().-]{5,31}$")
_ROLE_REQUIRED = (
    (("paid",), "ROLE_CLARITY_PAID_MISSING"),
    (("fixed-fee", "fixed fee"), "ROLE_CLARITY_FIXED_FEE_MISSING"),
    (("subcontract", "workshare"), "ROLE_CLARITY_WORKSHARE_MISSING"),
    (("not staffing",), "ROLE_CLARITY_NOT_STAFFING_MISSING"),
    (("not recruiting",), "ROLE_CLARITY_NOT_RECRUITING_MISSING"),
    (("not platform replacement",), "ROLE_CLARITY_NOT_PLATFORM_REPLACEMENT_MISSING"),
)
_ROLE_CONTRADICTIONS = (
    "unpaid",
    "not paid",
    "not fixed-fee",
    "not fixed fee",
    "not subcontract",
    "not workshare",
)

_CLEAR_ROUTE_PROVENANCE = "FIRST_PARTY_CURRENT"
_CLEAR_ROUTE_STATE = "CLEAR"
_CLEAR_COLLISION_STATE = "CLEAR"
_COMMERCIAL_STATE = "PROPOSED_NOT_ACCEPTED"

_AUTHORITY_FALSE = {
    "external_send_authorized": False,
    "muse_selected": False,
    "provider_mutation_authorized": False,
    "payment_authorized": False,
    "revenue_claim_authorized": False,
}


class QualificationError(ValueError):
    """Malformed input/receipt shape; ordinary commercial blockers become HOLD."""


def canonical_json(value: Any) -> str:
    """Return deterministic JSON after rejecting unsafe/non-portable values."""
    _validate_json_tree(value, "$")
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise QualificationError(f"non-canonical JSON value: {exc}") from exc


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _validate_json_tree(value: Any, path: str) -> None:
    if value is None or isinstance(value, str):
        if isinstance(value, str) and "\x00" in value:
            raise QualificationError(f"{path}: NUL is not allowed")
        return
    if isinstance(value, bool):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        raise QualificationError(f"{path}: floats are not allowed")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_tree(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise QualificationError(f"{path}: object keys must be non-empty strings")
            if "\x00" in key:
                raise QualificationError(f"{path}: NUL is not allowed in object keys")
            _validate_json_tree(item, f"{path}.{key}")
        return
    raise QualificationError(f"{path}: unsupported value type {type(value).__name__}")


def _require_exact_keys(value: Any, expected: frozenset[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise QualificationError(f"{path}: expected object")
    actual = frozenset(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        raise QualificationError(f"{path}: schema mismatch missing={missing} unknown={unknown}")
    return value


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise QualificationError(f"{path}: expected string")
    normalized = value.strip()
    if not normalized:
        raise QualificationError(f"{path}: empty string")
    if "\x00" in normalized:
        raise QualificationError(f"{path}: NUL is not allowed")
    return normalized


def _url(value: Any, path: str) -> str:
    url = _text(value, path)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise QualificationError(f"{path}: expected credential-free https URL")
    return url


def _timestamp(value: Any, path: str) -> datetime:
    text = _text(value, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QualificationError(f"{path}: invalid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise QualificationError(f"{path}: timezone is required")
    return parsed.astimezone(timezone.utc)


def _z(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    text = dt.isoformat(timespec="microseconds" if dt.microsecond else "seconds")
    return text.replace("+00:00", "Z")


def _int(value: Any, path: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise QualificationError(f"{path}: expected integer (boolean is not accepted)")
    if value < minimum or value > maximum:
        raise QualificationError(f"{path}: expected {minimum}..{maximum}")
    return value


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise QualificationError(f"{path}: expected boolean")
    return value


def _string_list(value: Any, path: str, *, minimum_items: int = 1) -> list[str]:
    if not isinstance(value, list):
        raise QualificationError(f"{path}: expected array")
    if len(value) < minimum_items:
        raise QualificationError(f"{path}: requires at least {minimum_items} item(s)")
    items = [_text(item, f"{path}[{idx}]") for idx, item in enumerate(value)]
    folded = [item.casefold() for item in items]
    if len(set(folded)) != len(folded):
        raise QualificationError(f"{path}: duplicate entries are not allowed")
    return items


def _freshness_reason(observed_at: datetime, now: datetime, max_age: timedelta, code: str) -> str | None:
    if observed_at > now:
        return f"{code}_FUTURE_OBSERVATION"
    if now - observed_at > max_age:
        return f"{code}_STALE"
    return None


def _contains_phrase(text: str, phrase: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(phrase).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def _normalize(payload: Mapping[str, Any]) -> dict[str, Any]:
    root = _require_exact_keys(dict(payload), _TOP_KEYS, "$")
    opportunity = _require_exact_keys(root["opportunity"], _OPPORTUNITY_KEYS, "$.opportunity")
    workshare = _require_exact_keys(root["workshare"], _WORKSHARE_KEYS, "$.workshare")
    partner = _require_exact_keys(root["partner_fit"], _PARTNER_FIT_KEYS, "$.partner_fit")
    runway = _require_exact_keys(root["delivery_runway"], _RUNWAY_KEYS, "$.delivery_runway")
    route = _require_exact_keys(root["route"], _ROUTE_KEYS, "$.route")
    collision = _require_exact_keys(root["collision"], _COLLISION_KEYS, "$.collision")

    route_kind = _text(route["kind"], "$.route.kind").lower()
    route_value = _text(route["route"], "$.route.route")
    if route_kind == "email":
        route_value = route_value.lower()
        if not _EMAIL.fullmatch(route_value):
            raise QualificationError("$.route.route: invalid email route")
    elif route_kind == "contact_form":
        route_value = _url(route_value, "$.route.route")
    elif route_kind == "phone":
        if not _PHONE.fullmatch(route_value):
            raise QualificationError("$.route.route: invalid phone route")
    else:
        raise QualificationError("$.route.kind: allowed values are email, contact_form, phone")

    collision_route = _text(collision["route"], "$.collision.route")
    if route_kind == "email":
        collision_route = collision_route.lower()
    elif route_kind == "contact_form":
        collision_route = _url(collision_route, "$.collision.route")

    source_commit = _text(workshare["source_commit"], "$.workshare.source_commit").lower()
    if not _SHA40.fullmatch(source_commit):
        raise QualificationError("$.workshare.source_commit: expected 40 lowercase hex characters")

    return {
        "opportunity": {
            "opportunity_id": _text(opportunity["opportunity_id"], "$.opportunity.opportunity_id"),
            "buyer": _text(opportunity["buyer"], "$.opportunity.buyer"),
            "source_url": _url(opportunity["source_url"], "$.opportunity.source_url"),
            "observed_at": _z(_timestamp(opportunity["observed_at"], "$.opportunity.observed_at")),
            "submission_deadline_at": _z(_timestamp(opportunity["submission_deadline_at"], "$.opportunity.submission_deadline_at")),
            "delivery_start_at": _z(_timestamp(opportunity["delivery_start_at"], "$.opportunity.delivery_start_at")),
        },
        "workshare": {
            "source_repository": _text(workshare["source_repository"], "$.workshare.source_repository"),
            "source_path": _text(workshare["source_path"], "$.workshare.source_path"),
            "source_commit": source_commit,
            "landed": _bool(workshare["landed"], "$.workshare.landed"),
            "commercial_state": _text(workshare["commercial_state"], "$.workshare.commercial_state"),
            "role_statement": _text(workshare["role_statement"], "$.workshare.role_statement"),
            "deliverables": _string_list(workshare["deliverables"], "$.workshare.deliverables"),
            "acceptance_criteria": _string_list(workshare["acceptance_criteria"], "$.workshare.acceptance_criteria"),
        },
        "partner_fit": {
            "organization": _text(partner["organization"], "$.partner_fit.organization"),
            "evidence_url": _url(partner["evidence_url"], "$.partner_fit.evidence_url"),
            "observed_at": _z(_timestamp(partner["observed_at"], "$.partner_fit.observed_at")),
            "fit_statement": _text(partner["fit_statement"], "$.partner_fit.fit_statement"),
        },
        "delivery_runway": {
            "minimum_lead_days": _int(runway["minimum_lead_days"], "$.delivery_runway.minimum_lead_days", minimum=0, maximum=366),
            "evidence_url": _url(runway["evidence_url"], "$.delivery_runway.evidence_url"),
            "observed_at": _z(_timestamp(runway["observed_at"], "$.delivery_runway.observed_at")),
        },
        "route": {
            "organization": _text(route["organization"], "$.route.organization"),
            "route": route_value,
            "kind": route_kind,
            "evidence_url": _url(route["evidence_url"], "$.route.evidence_url"),
            "observed_at": _z(_timestamp(route["observed_at"], "$.route.observed_at")),
            "provenance": _text(route["provenance"], "$.route.provenance"),
            "state": _text(route["state"], "$.route.state"),
        },
        "collision": {
            "buyer": _text(collision["buyer"], "$.collision.buyer"),
            "opportunity_id": _text(collision["opportunity_id"], "$.collision.opportunity_id"),
            "organization": _text(collision["organization"], "$.collision.organization"),
            "route": collision_route,
            "purpose": _text(collision["purpose"], "$.collision.purpose"),
            "state": _text(collision["state"], "$.collision.state"),
            "observed_at": _z(_timestamp(collision["observed_at"], "$.collision.observed_at")),
            "evidence_refs": _string_list(collision["evidence_refs"], "$.collision.evidence_refs"),
        },
    }


def _identity(normalized: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "opportunity_id": normalized["opportunity"]["opportunity_id"],
        "buyer": normalized["opportunity"]["buyer"],
        "organization": normalized["partner_fit"]["organization"],
        "route_kind": normalized["route"]["kind"],
        "route": normalized["route"]["route"],
        "purpose": normalized["collision"]["purpose"],
        "workshare_source_commit": normalized["workshare"]["source_commit"],
    }


def _code(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")
    return cleaned or "UNKNOWN"


def compile_partner_fit(payload: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
    """Compile a deterministic READY_FOR_MUSE/HOLD receipt."""
    if not isinstance(payload, Mapping):
        raise QualificationError("$: expected object")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise QualificationError("now: timezone-aware datetime required")
    now = now.astimezone(timezone.utc)

    normalized = _normalize(payload)
    reasons: list[str] = []

    observations = (
        (_timestamp(normalized["opportunity"]["observed_at"], "$.opportunity.observed_at"), OPPORTUNITY_MAX_AGE, "OPPORTUNITY_SOURCE"),
        (_timestamp(normalized["partner_fit"]["observed_at"], "$.partner_fit.observed_at"), PARTNER_FIT_MAX_AGE, "PARTNER_FIT"),
        (_timestamp(normalized["delivery_runway"]["observed_at"], "$.delivery_runway.observed_at"), RUNWAY_EVIDENCE_MAX_AGE, "RUNWAY_EVIDENCE"),
        (_timestamp(normalized["route"]["observed_at"], "$.route.observed_at"), ROUTE_MAX_AGE, "ROUTE_EVIDENCE"),
        (_timestamp(normalized["collision"]["observed_at"], "$.collision.observed_at"), COLLISION_MAX_AGE, "COLLISION_EVIDENCE"),
    )
    for observed, max_age, code in observations:
        reason = _freshness_reason(observed, now, max_age, code)
        if reason:
            reasons.append(reason)

    deadline = _timestamp(normalized["opportunity"]["submission_deadline_at"], "$.opportunity.submission_deadline_at")
    delivery_start = _timestamp(normalized["opportunity"]["delivery_start_at"], "$.opportunity.delivery_start_at")
    if deadline <= now:
        reasons.append("OPPORTUNITY_DEADLINE_CLOSED")
    if delivery_start <= now:
        reasons.append("DELIVERY_START_CLOSED")

    lead = normalized["delivery_runway"]["minimum_lead_days"]
    if now + timedelta(days=lead) > delivery_start:
        reasons.append("INSUFFICIENT_DELIVERY_RUNWAY")

    if not normalized["workshare"]["landed"]:
        reasons.append("WORKSHARE_NOT_LANDED")
    if normalized["workshare"]["commercial_state"] != _COMMERCIAL_STATE:
        reasons.append("WORKSHARE_COMMERCIAL_STATE_UNSUPPORTED")

    role = " ".join(normalized["workshare"]["role_statement"].casefold().split())
    for alternatives, reason in _ROLE_REQUIRED:
        if not any(_contains_phrase(role, token) for token in alternatives):
            reasons.append(reason)
    if any(_contains_phrase(role, token) for token in _ROLE_CONTRADICTIONS):
        reasons.append("ROLE_CLARITY_CONTRADICTORY")

    if normalized["route"]["organization"].casefold() != normalized["partner_fit"]["organization"].casefold():
        reasons.append("ROUTE_ORGANIZATION_MISMATCH")
    if normalized["route"]["provenance"] != _CLEAR_ROUTE_PROVENANCE:
        reasons.append("ROUTE_PROVENANCE_NOT_CURRENT_FIRST_PARTY")
    route_state = normalized["route"]["state"]
    if route_state != _CLEAR_ROUTE_STATE:
        reasons.append(f"ROUTE_STATE_{_code(route_state)}")

    if normalized["collision"]["buyer"].casefold() != normalized["opportunity"]["buyer"].casefold():
        reasons.append("COLLISION_BUYER_MISMATCH")
    if normalized["collision"]["opportunity_id"].casefold() != normalized["opportunity"]["opportunity_id"].casefold():
        reasons.append("COLLISION_OPPORTUNITY_MISMATCH")
    if normalized["collision"]["organization"].casefold() != normalized["partner_fit"]["organization"].casefold():
        reasons.append("COLLISION_ORGANIZATION_MISMATCH")
    if normalized["collision"]["route"].casefold() != normalized["route"]["route"].casefold():
        reasons.append("COLLISION_ROUTE_MISMATCH")
    collision_state = normalized["collision"]["state"]
    if collision_state != _CLEAR_COLLISION_STATE:
        reasons.append(f"COLLISION_STATE_{_code(collision_state)}")

    reasons = sorted(set(reasons))
    status = "READY_FOR_MUSE" if not reasons else "HOLD"
    identity = _identity(normalized)
    receipt_without_hash = {
        "schema": SCHEMA_VERSION,
        "compiled_at": _z(now),
        "source_sha256": sha256_json(normalized),
        "status": status,
        "reasons": reasons,
        "policy": {
            "opportunity_max_age_seconds": int(OPPORTUNITY_MAX_AGE.total_seconds()),
            "partner_fit_max_age_seconds": int(PARTNER_FIT_MAX_AGE.total_seconds()),
            "runway_evidence_max_age_seconds": int(RUNWAY_EVIDENCE_MAX_AGE.total_seconds()),
            "route_max_age_seconds": int(ROUTE_MAX_AGE.total_seconds()),
            "collision_max_age_seconds": int(COLLISION_MAX_AGE.total_seconds()),
        },
        "muse_handoff": {
            "publication_key": "lp-partner-fit:" + sha256_json(identity),
            "candidate": identity,
            "state": "PREPARED_NOT_REQUESTED",
        },
        "authority": deepcopy(_AUTHORITY_FALSE),
    }
    receipt = deepcopy(receipt_without_hash)
    receipt["receipt_sha256"] = sha256_json(receipt_without_hash)
    return receipt


def verify_receipt(payload: Mapping[str, Any], receipt: Mapping[str, Any], *, now: datetime) -> bool:
    """True only when receipt exactly matches deterministic compilation."""
    if not isinstance(receipt, Mapping):
        return False
    try:
        expected = compile_partner_fit(payload, now=now)
        supplied = deepcopy(dict(receipt))
        canonical_json(supplied)
    except (QualificationError, TypeError, ValueError):
        return False
    return supplied == expected

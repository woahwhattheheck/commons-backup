from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any
from types import MappingProxyType

INPUT_SCHEMA = "revenue-targeting-allocator-input/v1"
OUTPUT_SCHEMA = "revenue-targeting-allocator-output/v1"
RECEIPT_SCHEMA = "revenue-targeting-allocator-receipt/v1"
MAX_CANDIDATES = 10_000
HEX64_RE = re.compile(r"[0-9a-f]{64}")
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}")
CURRENCY_RE = re.compile(r"[A-Z]{3}")

ROUTE_STATES = {"VERIFIED_CLEAR", "MISSING", "UNKNOWN", "INVALID"}
RELATIONSHIP_STATES = {"CLEAR", "DNR", "OPTOUT", "CONFLICT", "UNKNOWN"}
COLLISION_STATES = {"CLEAR", "OWNED_OTHER", "CONFLICT", "UNKNOWN"}
FRESHNESS_STATES = {"FRESH", "STALE", "UNKNOWN"}
BUYER_STAGES = {
    "PUBLIC_FIT",
    "INBOUND_INTEREST",
    "MEETING_REQUESTED",
    "PROPOSAL_REQUESTED",
    "COMMERCIAL_TERMS_DISCUSSION",
    "OWNER_VERIFIED_ACCEPTANCE",
}
BUYER_STAGE_STATES = {"VERIFIED", "CONFLICT", "UNKNOWN"}
FIT_STATES = {"STRONG", "MEDIUM", "WEAK", "UNKNOWN"}
DELIVERY_STATES = {"READY", "HOLD", "UNKNOWN"}

STAGE_POINTS = {
    "PUBLIC_FIT": 100,
    "INBOUND_INTEREST": 300,
    "MEETING_REQUESTED": 500,
    "PROPOSAL_REQUESTED": 700,
    "COMMERCIAL_TERMS_DISCUSSION": 850,
    "OWNER_VERIFIED_ACCEPTANCE": 1000,
}
FIT_POINTS = {"STRONG": 300, "MEDIUM": 200, "WEAK": 100, "UNKNOWN": 0}

ROOT_KEYS = {"schema", "portfolio_id", "candidates"}
CANDIDATE_KEYS = {
    "opportunity_id",
    "offer_id",
    "currency",
    "commercial_value_minor",
    "probability_bps",
    "route_state",
    "relationship_state",
    "collision_state",
    "freshness_state",
    "buyer_stage",
    "buyer_stage_state",
    "fit_state",
    "delivery_state",
    "evidence_bundle_sha256",
}
REQUIRED_CANDIDATE_KEYS = CANDIDATE_KEYS - {"probability_bps"}

AUTHORITY_FALSE = {
    "external_send_authorized": False,
    "provider_mutation_authorized": False,
    "payment_or_revenue_inferred": False,
}


class AllocationError(ValueError):
    pass


def _plain(value: Any, field: str) -> Any:
    if type(value) not in (dict, list, str, int, bool, type(None)):
        raise AllocationError(f"{field} must contain plain JSON values")
    if isinstance(value, dict):
        if type(value) is not dict:
            raise AllocationError(f"{field} must be a plain object")
        return {k: _plain(v, field) for k, v in value.items()}
    if isinstance(value, list):
        if type(value) is not list:
            raise AllocationError(f"{field} must be a plain list")
        return [_plain(v, field) for v in value]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _plain(value, "document"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_document(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _token(value: Any, field: str, _token_re: re.Pattern[str] = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}")) -> str:
    if not isinstance(value, str) or not _token_re.fullmatch(value):
        raise AllocationError(f"{field} must be a bounded machine token")
    return value


def _enum(value: Any, field: str, allowed: set[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise AllocationError(f"{field} invalid")
    return value


def _exact_keys(obj: Any, allowed: set[str], required: set[str], field: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise AllocationError(f"{field} must be a plain object")
    keys = set(obj)
    missing = required - keys
    extra = keys - allowed
    if missing:
        raise AllocationError(f"{field} missing keys: {','.join(sorted(missing))}")
    if extra:
        raise AllocationError(f"{field} unknown keys: {','.join(sorted(extra))}")
    return dict(obj)


def _validate_candidate(
    raw: Any,
    _candidate_keys: frozenset[str] = frozenset(CANDIDATE_KEYS),
    _required_candidate_keys: frozenset[str] = frozenset(REQUIRED_CANDIDATE_KEYS),
    _currency_re: re.Pattern[str] = re.compile(r"[A-Z]{3}"),
    _hex64_re: re.Pattern[str] = re.compile(r"[0-9a-f]{64}"),
    _route_states: frozenset[str] = frozenset(ROUTE_STATES),
    _relationship_states: frozenset[str] = frozenset(RELATIONSHIP_STATES),
    _collision_states: frozenset[str] = frozenset(COLLISION_STATES),
    _freshness_states: frozenset[str] = frozenset(FRESHNESS_STATES),
    _buyer_stages: frozenset[str] = frozenset(BUYER_STAGES),
    _buyer_stage_states: frozenset[str] = frozenset(BUYER_STAGE_STATES),
    _fit_states: frozenset[str] = frozenset(FIT_STATES),
    _delivery_states: frozenset[str] = frozenset(DELIVERY_STATES),
) -> dict[str, Any]:
    c = _exact_keys(raw, set(_candidate_keys), set(_required_candidate_keys), "candidate")
    opportunity_id = _token(c["opportunity_id"], "opportunity_id")
    offer_id = _token(c["offer_id"], "offer_id")
    currency = c["currency"]
    if not isinstance(currency, str) or not _currency_re.fullmatch(currency):
        raise AllocationError("currency must be uppercase ISO-like 3-letter code")
    value = c["commercial_value_minor"]
    if type(value) is not int:
        raise AllocationError("commercial_value_minor must be integer minor units")
    probability = c.get("probability_bps")
    if probability is not None and (type(probability) is not int or not 0 <= probability <= 10_000):
        raise AllocationError("probability_bps must be integer 0..10000")
    evidence = c["evidence_bundle_sha256"]
    if not isinstance(evidence, str) or not _hex64_re.fullmatch(evidence):
        raise AllocationError("evidence_bundle_sha256 must be lowercase SHA-256")
    return {
        "opportunity_id": opportunity_id,
        "offer_id": offer_id,
        "currency": currency,
        "commercial_value_minor": value,
        **({"probability_bps": probability} if probability is not None else {}),
        "route_state": _enum(c["route_state"], "route_state", set(_route_states)),
        "relationship_state": _enum(c["relationship_state"], "relationship_state", set(_relationship_states)),
        "collision_state": _enum(c["collision_state"], "collision_state", set(_collision_states)),
        "freshness_state": _enum(c["freshness_state"], "freshness_state", set(_freshness_states)),
        "buyer_stage": _enum(c["buyer_stage"], "buyer_stage", set(_buyer_stages)),
        "buyer_stage_state": _enum(c["buyer_stage_state"], "buyer_stage_state", set(_buyer_stage_states)),
        "fit_state": _enum(c["fit_state"], "fit_state", set(_fit_states)),
        "delivery_state": _enum(c["delivery_state"], "delivery_state", set(_delivery_states)),
        "evidence_bundle_sha256": evidence,
    }


def validate_input(
    document: Any,
    _root_keys: frozenset[str] = frozenset(ROOT_KEYS),
    _input_schema: str = INPUT_SCHEMA,
    _max_candidates: int = MAX_CANDIDATES,
) -> dict[str, Any]:
    root = _exact_keys(document, set(_root_keys), set(_root_keys), "input")
    if root.get("schema") != _input_schema:
        raise AllocationError("input schema mismatch")
    portfolio_id = _token(root["portfolio_id"], "portfolio_id")
    candidates = root["candidates"]
    if type(candidates) is not list or not candidates:
        raise AllocationError("candidates must be a non-empty plain list")
    if len(candidates) > _max_candidates:
        raise AllocationError("candidate limit exceeded")
    normalized = [_validate_candidate(c) for c in candidates]

    pairs: set[tuple[str, str]] = set()
    offer_by_opportunity: dict[str, str] = {}
    for c in normalized:
        pair = (c["opportunity_id"], c["offer_id"])
        if pair in pairs:
            raise AllocationError("duplicate opportunity/offer identity")
        pairs.add(pair)
        prior = offer_by_opportunity.setdefault(c["opportunity_id"], c["offer_id"])
        if prior != c["offer_id"]:
            raise AllocationError("one opportunity cannot switch offers in one generation")
    return {"schema": _input_schema, "portfolio_id": portfolio_id, "candidates": normalized}



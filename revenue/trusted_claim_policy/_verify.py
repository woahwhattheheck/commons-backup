from __future__ import annotations

from datetime import datetime
from typing import Any

from revenue.trusted_evidence_authority.strict_json import (
    StrictJsonError,
    canonical_json,
)

from ._common import (
    AUTHORITY_CEILING,
    CURRENT_LEVEL,
    HISTORICAL_LEVEL,
    HOLD_LEVEL,
    RECEIPT_SCHEMA,
    UTC,
    ClaimPolicyError,
    _aware_utc,
    _exact_keys,
    _json_guard,
    _optional_utc,
    _parse_utc,
    _require_hex64,
    _utc_z,
    sha256_text,
)
from ._model import TrustedClaimPolicy, _trusted_policy_snapshot
from ._packet import validate_packet

def _policy_reasons(
    packet: dict[str, Any],
    policy_raw: dict[str, Any],
    at: datetime,
    *,
    enforce_freshness: bool,
) -> list[str]:
    reasons: list[str] = []
    at = _aware_utc(at, "evaluation time")
    issued_at = _parse_utc(policy_raw["issued_at"], "issued_at")
    valid_from = _optional_utc(policy_raw["valid_from"], "valid_from")
    valid_before = _optional_utc(policy_raw["valid_before"], "valid_before")
    period_end = _optional_utc(policy_raw["period_end"], "period_end")

    if at < issued_at:
        reasons.append("POLICY_FROM_FUTURE")
    if valid_from is not None and at < valid_from:
        reasons.append("POLICY_NOT_YET_VALID")
    if valid_before is not None and at >= valid_before:
        reasons.append("POLICY_EXPIRED")

    packet_sources = {row["source_id"]: row for row in packet["sources"]}
    trusted_sources = {row["source_id"]: row for row in policy_raw["sources"]}
    for source_id in sorted(set(trusted_sources) - set(packet_sources)):
        reasons.append(f"MISSING_SOURCE:{source_id}")
    for source_id in sorted(set(packet_sources) - set(trusted_sources)):
        reasons.append(f"UNKNOWN_SOURCE:{source_id}")
    for source_id in sorted(set(packet_sources) & set(trusted_sources)):
        actual = packet_sources[source_id]
        expected = trusted_sources[source_id]
        for field in (
            "provider",
            "scope",
            "resource",
            "generation",
            "content_sha256",
            "captured_at",
        ):
            if actual[field] != expected[field]:
                reasons.append(f"SOURCE_MISMATCH:{source_id}:{field}")
        captured_at = _parse_utc(expected["captured_at"], "captured_at")
        if at < captured_at:
            reasons.append(f"SOURCE_FROM_FUTURE:{source_id}")
        elif enforce_freshness and (at - captured_at).total_seconds() > expected["max_age_seconds"]:
            reasons.append(f"STALE_SOURCE:{source_id}")

    packet_claims = {row["claim_id"]: row for row in packet["claims"]}
    trusted_claims = {row["claim_id"]: row for row in policy_raw["claims"]}
    required_claim_ids = {row["claim_id"] for row in policy_raw["claims"] if row["required"]}
    for claim_id in sorted(required_claim_ids - set(packet_claims)):
        reasons.append(f"MISSING_REQUIRED_CLAIM:{claim_id}")
    for claim_id in sorted(set(packet_claims) - set(trusted_claims)):
        reasons.append(f"UNKNOWN_CLAIM:{claim_id}")
    for claim_id in sorted(set(packet_claims) & set(trusted_claims)):
        actual = packet_claims[claim_id]
        expected = trusted_claims[claim_id]
        if actual["statement"] != expected["statement"]:
            reasons.append(f"CLAIM_MISMATCH:{claim_id}:statement")
        if actual["statement_sha256"] != expected["statement_sha256"]:
            reasons.append(f"CLAIM_MISMATCH:{claim_id}:statement_sha256")
        if actual["source_ids"] != expected["source_ids"]:
            reasons.append(f"CLAIM_MISMATCH:{claim_id}:source_ids")
        if expected["requires_closed_period"]:
            if period_end is None:
                reasons.append(f"PERIOD_END_MISSING:{claim_id}")
                continue
            if at < period_end:
                reasons.append(f"PERIOD_OPEN:{claim_id}")
            for source_id in expected["source_ids"]:
                source = trusted_sources[source_id]
                if not source["complete"]:
                    reasons.append(f"INCOMPLETE_SOURCE:{claim_id}:{source_id}")
                captured_at = _parse_utc(source["captured_at"], "captured_at")
                if captured_at < period_end:
                    reasons.append(f"SOURCE_CAPTURE_BEFORE_PERIOD_END:{claim_id}:{source_id}")

    return sorted(set(reasons))

def _receipt(
    packet: dict[str, Any],
    policy: TrustedClaimPolicy,
    policy_id: str,
    *,
    level: str,
    verified_at: datetime,
    reasons: list[str],
) -> dict[str, Any]:
    body = {
        "schema": RECEIPT_SCHEMA,
        "evidence_level": level,
        "current_claim_authority": level == CURRENT_LEVEL and not reasons,
        "policy_id": policy_id,
        "policy_canonical_sha256": policy.canonical_sha256,
        "policy_pin_sha256": policy.pin_sha256,
        "subject_id": packet["subject_id"],
        "decision_id": packet["decision_id"],
        "context_sha256": packet["context_sha256"],
        "packet_sha256": sha256_text(canonical_json(packet)),
        "claim_ids": [row["claim_id"] for row in packet["claims"]],
        "verified_at": _utc_z(verified_at),
        "reasons": sorted(set(reasons)),
        "authority_ceiling": AUTHORITY_CEILING,
    }
    return {**body, "receipt_sha256": sha256_text(canonical_json(body))}

def _verify_at(
    packet: dict[str, Any],
    policy: TrustedClaimPolicy,
    *,
    at: datetime,
    historical: bool,
) -> dict[str, Any]:
    packet = validate_packet(packet)
    policy_raw = _trusted_policy_snapshot(policy)
    policy_id = policy_raw["policy_id"]
    if packet["policy_id"] != policy_id:
        raise ClaimPolicyError("packet policy_id mismatch")
    at = _aware_utc(at, "evaluation time")
    reasons = _policy_reasons(packet, policy_raw, at, enforce_freshness=not historical)
    if historical:
        level = HISTORICAL_LEVEL
    else:
        level = CURRENT_LEVEL if not reasons else HOLD_LEVEL
    return _receipt(
        packet,
        policy,
        policy_id,
        level=level,
        verified_at=at,
        reasons=reasons,
    )

def verify_current(packet: dict[str, Any], policy: TrustedClaimPolicy) -> dict[str, Any]:
    """Evaluate CURRENT authority using process UTC. No caller-selected clock is accepted."""
    return _verify_at(packet, policy, at=datetime.now(UTC), historical=False)

def _verify_current_at_for_tests(
    packet: dict[str, Any], policy: TrustedClaimPolicy, *, now: datetime
) -> dict[str, Any]:
    """Private deterministic seam for tests and historical fixtures; not a production current API."""
    return _verify_at(packet, policy, at=now, historical=False)

def verify_historical(
    packet: dict[str, Any], policy: TrustedClaimPolicy, *, as_of: datetime
) -> dict[str, Any]:
    """Forensic replay only. It never emits CURRENT_CLAIM_AUTHORITY."""
    return _verify_at(packet, policy, at=as_of, historical=True)

def verify_receipt(
    receipt: dict[str, Any], packet: dict[str, Any], policy: TrustedClaimPolicy
) -> bool:
    """Recompute a recorded receipt at its recorded instant; this is not a fresh CURRENT check."""
    try:
        _json_guard(receipt)
        if not isinstance(receipt, dict):
            return False
        _exact_keys(
            receipt,
            {
                "schema",
                "evidence_level",
                "current_claim_authority",
                "policy_id",
                "policy_canonical_sha256",
                "policy_pin_sha256",
                "subject_id",
                "decision_id",
                "context_sha256",
                "packet_sha256",
                "claim_ids",
                "verified_at",
                "reasons",
                "authority_ceiling",
                "receipt_sha256",
            },
        )
        if receipt["schema"] != RECEIPT_SCHEMA:
            return False
        digest = _require_hex64(receipt["receipt_sha256"], "receipt_sha256")
        body = dict(receipt)
        body.pop("receipt_sha256")
        if sha256_text(canonical_json(body)) != digest:
            return False
        level = receipt["evidence_level"]
        if level not in {CURRENT_LEVEL, HOLD_LEVEL, HISTORICAL_LEVEL}:
            return False
        verified_at = _parse_utc(receipt["verified_at"], "verified_at")
        expected = _verify_at(
            packet,
            policy,
            at=verified_at,
            historical=level == HISTORICAL_LEVEL,
        )
        return canonical_json(expected) == canonical_json(receipt)
    except (ClaimPolicyError, StrictJsonError, TypeError, ValueError, KeyError):
        return False

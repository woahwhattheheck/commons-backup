from __future__ import annotations

from typing import Any, Iterable

from revenue.trusted_evidence_authority.strict_json import (
    StrictJsonError,
    canonical_json,
    loads_strict,
)

from ._common import (
    PACKET_SCHEMA,
    ClaimPolicyError,
    _exact_keys,
    _json_guard,
    _normalized_id_list,
    _parse_utc,
    _require_hex64,
    _require_id,
    _require_positive_int,
    _statement,
    sha256_text,
)

def validate_packet(value: Any) -> dict[str, Any]:
    _json_guard(value)
    if not isinstance(value, dict):
        raise ClaimPolicyError("packet must be an object")
    _exact_keys(
        value,
        {
            "schema",
            "policy_id",
            "subject_id",
            "decision_id",
            "context",
            "context_sha256",
            "sources",
            "claims",
        },
    )
    if value["schema"] != PACKET_SCHEMA:
        raise ClaimPolicyError("unsupported packet schema")
    policy_id = _require_id(value["policy_id"], "policy_id")
    subject_id = _require_id(value["subject_id"], "subject_id")
    decision_id = _require_id(value["decision_id"], "decision_id")
    _json_guard(value["context"], path="$.context")
    context_sha256 = _require_hex64(value["context_sha256"], "context_sha256")
    if context_sha256 != sha256_text(canonical_json(value["context"])):
        raise ClaimPolicyError("context_sha256 mismatch")

    raw_sources = value["sources"]
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ClaimPolicyError("packet sources must be a non-empty list")
    sources: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for raw in raw_sources:
        if not isinstance(raw, dict):
            raise ClaimPolicyError("packet source must be an object")
        _exact_keys(
            raw,
            {
                "source_id",
                "provider",
                "scope",
                "resource",
                "generation",
                "content_sha256",
                "captured_at",
            },
        )
        source_id = _require_id(raw["source_id"], "source_id")
        if source_id in seen_sources:
            raise ClaimPolicyError(f"duplicate packet source_id: {source_id}")
        seen_sources.add(source_id)
        sources.append(
            {
                "source_id": source_id,
                "provider": _require_id(raw["provider"], "provider"),
                "scope": _require_id(raw["scope"], "scope"),
                "resource": _require_id(raw["resource"], "resource"),
                "generation": _require_positive_int(raw["generation"], "generation"),
                "content_sha256": _require_hex64(raw["content_sha256"], "content_sha256"),
                "captured_at": raw["captured_at"],
            }
        )
        _parse_utc(raw["captured_at"], "captured_at")

    raw_claims = value["claims"]
    if not isinstance(raw_claims, list):
        raise ClaimPolicyError("packet claims must be a list")
    claims: list[dict[str, Any]] = []
    seen_claims: set[str] = set()
    for raw in raw_claims:
        if not isinstance(raw, dict):
            raise ClaimPolicyError("packet claim must be an object")
        _exact_keys(raw, {"claim_id", "statement", "statement_sha256", "source_ids"})
        claim_id = _require_id(raw["claim_id"], "claim_id")
        if claim_id in seen_claims:
            raise ClaimPolicyError(f"duplicate packet claim_id: {claim_id}")
        seen_claims.add(claim_id)
        statement = _statement(raw["statement"], "statement")
        statement_sha256 = _require_hex64(raw["statement_sha256"], "statement_sha256")
        if statement_sha256 != sha256_text(statement):
            raise ClaimPolicyError(f"packet statement_sha256 mismatch: {claim_id}")
        claims.append(
            {
                "claim_id": claim_id,
                "statement": statement,
                "statement_sha256": statement_sha256,
                "source_ids": _normalized_id_list(raw["source_ids"], "source_ids"),
            }
        )

    return {
        "schema": PACKET_SCHEMA,
        "policy_id": policy_id,
        "subject_id": subject_id,
        "decision_id": decision_id,
        "context": value["context"],
        "context_sha256": context_sha256,
        "sources": sorted(sources, key=lambda row: row["source_id"]),
        "claims": sorted(claims, key=lambda row: row["claim_id"]),
    }

def packet_from_text(text: str) -> dict[str, Any]:
    try:
        return validate_packet(loads_strict(text))
    except StrictJsonError as exc:
        raise ClaimPolicyError(str(exc)) from exc

def receipt_from_text(text: str) -> dict[str, Any]:
    try:
        value = loads_strict(text)
    except StrictJsonError as exc:
        raise ClaimPolicyError(str(exc)) from exc
    if not isinstance(value, dict):
        raise ClaimPolicyError("receipt must be an object")
    return value

def make_packet(
    *,
    policy_id: str,
    subject_id: str,
    decision_id: str,
    context: Any,
    sources: Iterable[dict[str, Any]],
    claims: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    _json_guard(context, path="$.context")
    packet = {
        "schema": PACKET_SCHEMA,
        "policy_id": policy_id,
        "subject_id": subject_id,
        "decision_id": decision_id,
        "context": context,
        "context_sha256": sha256_text(canonical_json(context)),
        "sources": list(sources),
        "claims": list(claims),
    }
    return validate_packet(packet)

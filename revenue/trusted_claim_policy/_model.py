from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from revenue.trusted_evidence_authority.strict_json import (
    StrictJsonError,
    canonical_json,
    loads_strict,
)

from ._common import (
    MAX_POLICY_BYTES,
    POLICY_SCHEMA,
    ClaimPolicyError,
    _exact_keys,
    _json_guard,
    _normalized_id_list,
    _optional_utc,
    _parse_utc,
    _require_hex64,
    _require_id,
    _require_nonnegative_int,
    _require_positive_int,
    _statement,
    sha256_bytes,
    sha256_text,
)

_TRUSTED_POLICY_CONSTRUCTION_TOKEN = object()

@dataclass(frozen=True)
class TrustedClaimPolicy:
    """Validated policy snapshot. Construct through :func:`load_trusted_policy`."""

    _raw: dict[str, Any] = field(repr=False)
    canonical_sha256: str
    pin_sha256: str
    _construction_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._construction_token is not _TRUSTED_POLICY_CONSTRUCTION_TOKEN:
            raise ClaimPolicyError("TrustedClaimPolicy must be constructed by load_trusted_policy")

    @property
    def raw(self) -> dict[str, Any]:
        """Return a defensive copy; callers cannot mutate the trusted snapshot in place."""
        return copy.deepcopy(self._raw)

    @property
    def policy_id(self) -> str:
        return self._raw["policy_id"]

    @property
    def sources(self) -> dict[str, dict[str, Any]]:
        return {row["source_id"]: copy.deepcopy(row) for row in self._raw["sources"]}

    @property
    def claims(self) -> dict[str, dict[str, Any]]:
        return {row["claim_id"]: copy.deepcopy(row) for row in self._raw["claims"]}

    @property
    def required_claim_ids(self) -> set[str]:
        return {row["claim_id"] for row in self._raw["claims"] if row["required"]}

def validate_policy(value: Any) -> dict[str, Any]:
    _json_guard(value)
    if not isinstance(value, dict):
        raise ClaimPolicyError("policy must be an object")
    _exact_keys(
        value,
        {
            "schema",
            "policy_id",
            "issued_at",
            "valid_from",
            "valid_before",
            "period_end",
            "sources",
            "claims",
        },
    )
    if value["schema"] != POLICY_SCHEMA:
        raise ClaimPolicyError("unsupported policy schema")
    policy_id = _require_id(value["policy_id"], "policy_id")
    issued_at = _parse_utc(value["issued_at"], "issued_at")
    valid_from = _optional_utc(value["valid_from"], "valid_from")
    valid_before = _optional_utc(value["valid_before"], "valid_before")
    period_end = _optional_utc(value["period_end"], "period_end")
    if valid_from is not None and valid_before is not None and valid_from >= valid_before:
        raise ClaimPolicyError("valid_from must be before valid_before")
    if valid_before is not None and issued_at >= valid_before:
        raise ClaimPolicyError("issued_at must be before valid_before")

    source_rows = value["sources"]
    if not isinstance(source_rows, list) or not source_rows:
        raise ClaimPolicyError("sources must be a non-empty list")
    sources: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    provider_scopes: set[tuple[str, str]] = set()
    for raw in source_rows:
        if not isinstance(raw, dict):
            raise ClaimPolicyError("source commitment must be an object")
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
                "max_age_seconds",
                "complete",
            },
        )
        source_id = _require_id(raw["source_id"], "source_id")
        provider = _require_id(raw["provider"], "provider")
        scope = _require_id(raw["scope"], "scope")
        resource = _require_id(raw["resource"], "resource")
        if source_id in source_ids:
            raise ClaimPolicyError(f"duplicate source_id: {source_id}")
        source_ids.add(source_id)
        provider_scope = (provider, scope)
        if provider_scope in provider_scopes:
            raise ClaimPolicyError(f"ambiguous provider/scope: {provider}/{scope}")
        provider_scopes.add(provider_scope)
        generation = _require_positive_int(raw["generation"], "generation")
        content_sha256 = _require_hex64(raw["content_sha256"], "content_sha256")
        captured_at = _parse_utc(raw["captured_at"], "captured_at")
        if captured_at > issued_at:
            raise ClaimPolicyError(f"source captured after policy issuance: {source_id}")
        max_age_seconds = _require_nonnegative_int(raw["max_age_seconds"], "max_age_seconds")
        if not isinstance(raw["complete"], bool):
            raise ClaimPolicyError("complete must be boolean")
        sources.append(
            {
                "source_id": source_id,
                "provider": provider,
                "scope": scope,
                "resource": resource,
                "generation": generation,
                "content_sha256": content_sha256,
                "captured_at": raw["captured_at"],
                "max_age_seconds": max_age_seconds,
                "complete": raw["complete"],
            }
        )

    claim_rows = value["claims"]
    if not isinstance(claim_rows, list) or not claim_rows:
        raise ClaimPolicyError("claims must be a non-empty list")
    claims: list[dict[str, Any]] = []
    claim_ids: set[str] = set()
    for raw in claim_rows:
        if not isinstance(raw, dict):
            raise ClaimPolicyError("claim commitment must be an object")
        _exact_keys(
            raw,
            {
                "claim_id",
                "statement",
                "statement_sha256",
                "source_ids",
                "required",
                "requires_closed_period",
            },
        )
        claim_id = _require_id(raw["claim_id"], "claim_id")
        if claim_id in claim_ids:
            raise ClaimPolicyError(f"duplicate claim_id: {claim_id}")
        claim_ids.add(claim_id)
        statement = _statement(raw["statement"], "statement")
        statement_sha256 = _require_hex64(raw["statement_sha256"], "statement_sha256")
        if statement_sha256 != sha256_text(statement):
            raise ClaimPolicyError(f"statement_sha256 mismatch: {claim_id}")
        bound_sources = _normalized_id_list(raw["source_ids"], "source_ids")
        unknown = sorted(set(bound_sources) - source_ids)
        if unknown:
            raise ClaimPolicyError(f"claim {claim_id} binds unknown sources: {','.join(unknown)}")
        if not isinstance(raw["required"], bool):
            raise ClaimPolicyError("required must be boolean")
        if not isinstance(raw["requires_closed_period"], bool):
            raise ClaimPolicyError("requires_closed_period must be boolean")
        if raw["requires_closed_period"] and period_end is None:
            raise ClaimPolicyError(f"claim {claim_id} requires period_end")
        claims.append(
            {
                "claim_id": claim_id,
                "statement": statement,
                "statement_sha256": statement_sha256,
                "source_ids": bound_sources,
                "required": raw["required"],
                "requires_closed_period": raw["requires_closed_period"],
            }
        )

    if period_end is not None and valid_before is not None and period_end >= valid_before:
        if any(row["requires_closed_period"] for row in claims):
            raise ClaimPolicyError("period_end must be before valid_before for closed-period claims")

    return {
        "schema": POLICY_SCHEMA,
        "policy_id": policy_id,
        "issued_at": value["issued_at"],
        "valid_from": value["valid_from"],
        "valid_before": value["valid_before"],
        "period_end": value["period_end"],
        "sources": sorted(sources, key=lambda row: row["source_id"]),
        "claims": sorted(claims, key=lambda row: row["claim_id"]),
    }

def load_trusted_policy(path: str | Path, *, expected_file_sha256: str) -> TrustedClaimPolicy:
    expected_file_sha256 = _require_hex64(expected_file_sha256, "expected_file_sha256")
    data = Path(path).read_bytes()
    if len(data) > MAX_POLICY_BYTES:
        raise ClaimPolicyError("trusted policy exceeds size limit")
    observed = sha256_bytes(data)
    if observed != expected_file_sha256:
        raise ClaimPolicyError("trusted policy file digest does not match independently pinned digest")
    try:
        decoded = data.decode("utf-8")
        raw = loads_strict(decoded)
    except (UnicodeDecodeError, StrictJsonError) as exc:
        raise ClaimPolicyError(f"invalid trusted policy: {exc}") from exc
    normalized = validate_policy(raw)
    return TrustedClaimPolicy(
        _raw=copy.deepcopy(normalized),
        canonical_sha256=sha256_text(canonical_json(normalized)),
        pin_sha256=observed,
        _construction_token=_TRUSTED_POLICY_CONSTRUCTION_TOKEN,
    )

def _trusted_policy_snapshot(policy: TrustedClaimPolicy) -> dict[str, Any]:
    """Revalidate the private snapshot so nested mutation cannot survive to a decision."""
    if not isinstance(policy, TrustedClaimPolicy):
        raise ClaimPolicyError("policy must be a TrustedClaimPolicy loaded from pinned bytes")
    _require_hex64(policy.canonical_sha256, "canonical_sha256")
    _require_hex64(policy.pin_sha256, "pin_sha256")
    candidate = copy.deepcopy(policy._raw)
    try:
        observed = sha256_text(canonical_json(candidate))
    except StrictJsonError as exc:
        raise ClaimPolicyError("trusted policy object mutated after pin validation") from exc
    if observed != policy.canonical_sha256:
        raise ClaimPolicyError("trusted policy object mutated after pin validation")
    return validate_policy(candidate)

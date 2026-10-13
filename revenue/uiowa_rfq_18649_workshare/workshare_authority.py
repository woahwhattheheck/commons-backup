#!/usr/bin/env python3
"""Evidence-authority normalization, root binding, and source receipts."""
from __future__ import annotations

from typing import Any

from workshare_constants import (
    AUTHORITY_SCHEMA, DIMENSIONS, EVIDENCE_KINDS, GROUPS, MAX_SOURCES,
    SOLICITATION_ID, _AUTHORITY_KEYS, _SOURCE_KEYS, ContractError,
)
from workshare_core import (
    _format_utc, _parse_utc, _require_exact_keys, _require_id, _require_int,
    _require_sha, _require_str, _sha256_value,
)

def _normalize_source(raw: Any, index: int, *, generation: str, prime: str) -> dict[str, Any]:
    where = f"evidence_authority.sources[{index}]"
    value = _require_exact_keys(raw, _SOURCE_KEYS, where)
    source_id = _require_id(value["source_id"], f"{where}.source_id")
    row_generation = _require_id(value["authority_generation"], f"{where}.authority_generation")
    solicitation_id = _require_str(value["solicitation_id"], f"{where}.solicitation_id", max_len=32)
    row_prime = _require_str(value["prime_candidate"], f"{where}.prime_candidate", max_len=128)
    group = _require_str(value["group"], f"{where}.group", max_len=32)
    dimension = _require_str(value["dimension"], f"{where}.dimension", max_len=32)
    kind = _require_str(value["evidence_kind"], f"{where}.evidence_kind", max_len=32)
    source_ref = _require_str(value["source_ref"], f"{where}.source_ref", max_len=256)
    source_content_sha256 = _require_sha(value["source_content_sha256"], f"{where}.source_content_sha256")
    observed_at = _parse_utc(value["observed_at"], f"{where}.observed_at")
    claim = _require_str(value["claim"], f"{where}.claim", max_len=2000)
    maturity = _require_int(value["maturity"], f"{where}.maturity", low=0, high=4)
    confidence_bp = _require_int(value["confidence_bp"], f"{where}.confidence_bp", low=0, high=10_000)

    if row_generation != generation:
        raise ContractError(f"{where}.authority_generation mismatch")
    if solicitation_id != SOLICITATION_ID:
        raise ContractError(f"{where}.solicitation_id drift")
    if row_prime != prime:
        raise ContractError(f"{where}.prime_candidate mismatch")
    if group not in GROUPS:
        raise ContractError(f"{where}.group unknown: {group}")
    if dimension not in DIMENSIONS:
        raise ContractError(f"{where}.dimension unknown: {dimension}")
    if kind not in EVIDENCE_KINDS:
        raise ContractError(f"{where}.evidence_kind unknown: {kind}")

    return {
        "source_id": source_id,
        "authority_generation": row_generation,
        "solicitation_id": solicitation_id,
        "prime_candidate": row_prime,
        "group": group,
        "dimension": dimension,
        "evidence_kind": kind,
        "source_ref": source_ref,
        "source_content_sha256": source_content_sha256,
        "observed_at": _format_utc(observed_at),
        "claim": claim,
        "maturity": maturity,
        "confidence_bp": confidence_bp,
    }


def normalize_authority(raw: Any) -> dict[str, Any]:
    value = _require_exact_keys(raw, _AUTHORITY_KEYS, "evidence_authority")
    schema = _require_str(value["schema"], "evidence_authority.schema", max_len=96)
    if schema != AUTHORITY_SCHEMA:
        raise ContractError("evidence_authority.schema drift")
    generation = _require_id(value["generation"], "evidence_authority.generation")
    solicitation_id = _require_str(value["solicitation_id"], "evidence_authority.solicitation_id", max_len=32)
    prime = _require_str(value["prime_candidate"], "evidence_authority.prime_candidate", max_len=128)
    if solicitation_id != SOLICITATION_ID:
        raise ContractError("evidence_authority.solicitation_id drift")
    sources_raw = value["sources"]
    if type(sources_raw) is not list:
        raise ContractError("evidence_authority.sources must be array")
    if not 1 <= len(sources_raw) <= MAX_SOURCES:
        raise ContractError(f"evidence_authority.sources length must be 1..{MAX_SOURCES}")
    sources = [
        _normalize_source(item, i, generation=generation, prime=prime)
        for i, item in enumerate(sources_raw)
    ]
    ids = [row["source_id"] for row in sources]
    if len(ids) != len(set(ids)):
        raise ContractError("evidence_authority.sources contains duplicate source_id")
    sources.sort(key=lambda row: row["source_id"])
    return {
        "schema": schema,
        "generation": generation,
        "solicitation_id": solicitation_id,
        "prime_candidate": prime,
        "sources": sources,
    }


def authority_root_sha256(authority: Any) -> str:
    return _sha256_value(normalize_authority(authority))


def _validate_bindings(candidate: dict[str, Any], authority: dict[str, Any]) -> None:
    engagement = candidate["engagement"]
    if candidate["authority_generation"] != authority["generation"]:
        raise ContractError("candidate authority_generation mismatch")
    if engagement["solicitation_id"] != authority["solicitation_id"]:
        raise ContractError("candidate/authority solicitation mismatch")
    if engagement["prime_candidate"] != authority["prime_candidate"]:
        raise ContractError("candidate/authority prime mismatch")
    candidate_ids = candidate["source_ids"]
    authority_ids = [row["source_id"] for row in authority["sources"]]
    if candidate_ids != authority_ids:
        missing = sorted(set(authority_ids) - set(candidate_ids))
        extra = sorted(set(candidate_ids) - set(authority_ids))
        raise ContractError(f"candidate/authority source universe mismatch: missing={missing} extra={extra}")


def _source_receipts(authority: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "source_id": row["source_id"],
            "source_record_sha256": _sha256_value(row),
            "source_content_sha256": row["source_content_sha256"],
        }
        for row in authority["sources"]
    ]


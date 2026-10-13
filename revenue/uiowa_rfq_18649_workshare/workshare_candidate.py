#!/usr/bin/env python3
"""Commercial candidate packet normalization."""
from __future__ import annotations

from typing import Any

from workshare_constants import (
    BASE_FEE_USD, BUYER, CANDIDATE_SCHEMA, MAX_SOURCES, OPTIONAL_READOUT_USD,
    SOLICITATION_ID, SUBCONTRACTOR, _CANDIDATE_KEYS, _ENGAGEMENT_KEYS,
    ContractError,
)
from workshare_core import _require_exact_keys, _require_id, _require_int, _require_str

def _validate_engagement(raw: Any) -> dict[str, Any]:
    value = _require_exact_keys(raw, _ENGAGEMENT_KEYS, "engagement")
    solicitation_id = _require_str(value["solicitation_id"], "engagement.solicitation_id", max_len=32)
    buyer = _require_str(value["buyer"], "engagement.buyer", max_len=128)
    prime = _require_str(value["prime_candidate"], "engagement.prime_candidate", max_len=128)
    subcontractor = _require_str(value["subcontractor"], "engagement.subcontractor", max_len=128)
    base_fee = _require_int(value["base_fee_usd"], "engagement.base_fee_usd", low=0, high=1_000_000)
    option_fee = _require_int(
        value["optional_readout_usd"],
        "engagement.optional_readout_usd",
        low=0,
        high=1_000_000,
    )
    if solicitation_id != SOLICITATION_ID:
        raise ContractError("engagement.solicitation_id drift")
    if buyer != BUYER:
        raise ContractError("engagement.buyer drift")
    if subcontractor != SUBCONTRACTOR:
        raise ContractError("engagement.subcontractor drift")
    if base_fee != BASE_FEE_USD:
        raise ContractError("base fee drift")
    if option_fee != OPTIONAL_READOUT_USD:
        raise ContractError("optional readout fee drift")
    return {
        "solicitation_id": solicitation_id,
        "buyer": buyer,
        "prime_candidate": prime,
        "subcontractor": subcontractor,
        "base_fee_usd": base_fee,
        "optional_readout_usd": option_fee,
    }


def normalize_candidate(raw: Any) -> dict[str, Any]:
    value = _require_exact_keys(raw, _CANDIDATE_KEYS, "candidate")
    schema = _require_str(value["schema"], "candidate.schema", max_len=96)
    if schema != CANDIDATE_SCHEMA:
        raise ContractError("candidate.schema drift")
    engagement = _validate_engagement(value["engagement"])
    generation = _require_id(value["authority_generation"], "candidate.authority_generation")
    source_ids_raw = value["source_ids"]
    if type(source_ids_raw) is not list:
        raise ContractError("candidate.source_ids must be array")
    if not 1 <= len(source_ids_raw) <= MAX_SOURCES:
        raise ContractError(f"candidate.source_ids length must be 1..{MAX_SOURCES}")
    source_ids = [_require_id(item, f"candidate.source_ids[{i}]") for i, item in enumerate(source_ids_raw)]
    if len(source_ids) != len(set(source_ids)):
        raise ContractError("candidate.source_ids contains duplicates")
    source_ids.sort()
    return {
        "schema": schema,
        "engagement": engagement,
        "authority_generation": generation,
        "source_ids": source_ids,
    }



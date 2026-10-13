from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .common import (
    ControlError,
    require_bool,
    require_enum,
    require_exact_keys,
    require_int,
    require_list,
    require_object,
    require_ref,
    require_ref_list,
    require_sha256,
    require_string,
    require_timestamp,
    require_unique,
)

INPUT_SCHEMA = "teaming-conversion-input/v2"
EVIDENCE_SCHEMA = "teaming-conversion-retained-evidence/v2"
ROOTS_SCHEMA = "teaming-conversion-trusted-roots/v2"
RECEIPT_SCHEMA = "teaming-conversion-receipt/v2"

SOURCE_CLASSES = {"GMAIL", "SLACK", "PORTAL", "PHONE_TRANSCRIPT", "OTHER_RETAINED"}
INTERPRETATIONS = {
    "POSITIVE_CONTINUE",
    "CONDITIONAL_INTEREST",
    "REQUESTED_MORE_INFO",
    "DECLINED",
    "AMBIGUOUS",
}
RELEASE_CLASSES = {
    "PROSPECT_SAFE_SUMMARY",
    "PROSPECT_SAFE_PUBLIC_REFERENCE",
    "OWNER_APPROVAL_REQUIRED",
    "INTERNAL_ONLY",
}
PREP_STATES = {"READY", "DRAFT", "MISSING"}
GATE_STATES = {"CLEAR", "CURABLE", "BLOCKED", "UNKNOWN"}

@dataclass(frozen=True)
class ParsedCandidate:
    value: dict[str, Any]
    opportunity_id: str
    counterparty_ref: str
    thread_id: str
    requested_asset_ids: tuple[str, ...]
    required_commitment_ids: tuple[str, ...]

@dataclass(frozen=True)
class ParsedEvidence:
    value: dict[str, Any]
    root_id: str
    generation: int
    captured_at: datetime
    opportunity_id: str
    counterparty_ref: str
    thread_id: str
    counterparty_sender_refs: tuple[str, ...]
    requirements: dict[str, tuple[str, ...]]
    observations: tuple[dict[str, Any], ...]
    interpretations: tuple[dict[str, Any], ...]
    assets: tuple[dict[str, Any], ...]
    releases: tuple[dict[str, Any], ...]
    qualification_gates: tuple[dict[str, Any], ...]
    commitments: tuple[dict[str, Any], ...]

@dataclass(frozen=True)
class ParsedRoot:
    value: dict[str, Any]
    root_id: str
    opportunity_id: str
    counterparty_ref: str
    thread_id: str
    generation: int
    active_from: datetime
    expires_at: datetime

def _parse_opportunity(value: Any, label: str) -> dict[str, str]:
    obj = require_object(value, label)
    require_exact_keys(
        obj,
        required={"opportunity_id", "counterparty_ref", "thread_id"},
        label=label,
    )
    return {
        "opportunity_id": require_ref(obj["opportunity_id"], f"{label}.opportunity_id"),
        "counterparty_ref": require_ref(obj["counterparty_ref"], f"{label}.counterparty_ref"),
        "thread_id": require_ref(obj["thread_id"], f"{label}.thread_id"),
    }

def parse_candidate(value: Any) -> ParsedCandidate:
    obj = require_object(value, "candidate")
    require_exact_keys(
        obj,
        required={
            "schema",
            "opportunity",
            "requested_asset_ids",
            "required_commitment_ids",
        },
        label="candidate",
    )
    if require_string(obj["schema"], "candidate.schema", maximum=128) != INPUT_SCHEMA:
        raise ControlError(f"candidate.schema must be {INPUT_SCHEMA}")
    opportunity = _parse_opportunity(obj["opportunity"], "candidate.opportunity")
    requested_assets = require_ref_list(obj["requested_asset_ids"], "candidate.requested_asset_ids")
    required_commitments = require_ref_list(
        obj["required_commitment_ids"], "candidate.required_commitment_ids"
    )
    normalized = {
        "schema": INPUT_SCHEMA,
        "opportunity": opportunity,
        "requested_asset_ids": requested_assets,
        "required_commitment_ids": required_commitments,
    }
    return ParsedCandidate(
        normalized,
        opportunity["opportunity_id"],
        opportunity["counterparty_ref"],
        opportunity["thread_id"],
        tuple(requested_assets),
        tuple(required_commitments),
    )


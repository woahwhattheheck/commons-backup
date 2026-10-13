from __future__ import annotations

from typing import Any

from ._source_bound_common import _require_keys, _require_sha256, _require_utc_instant
from ._source_bound_constants import ContractError, SCHEMA_FACTS
from ._source_bound_identity import (
    _normalize_commitment,
    _normalize_requirements,
    _normalize_source_binding,
)

def _normalize_intent_receipt(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ContractError("facts.intent_receipt must be object or null")
    _require_keys(value, exact={"provider_event_sha256", "submitted_at"}, where="facts.intent_receipt")
    return {
        "provider_event_sha256": _require_sha256(
            value["provider_event_sha256"], "facts.intent_receipt.provider_event_sha256"
        ),
        "submitted_at": _require_utc_instant(value["submitted_at"], "facts.intent_receipt.submitted_at"),
    }
def _normalize_facts(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ContractError("facts must be object")
    _require_keys(
        obj,
        exact={
            "schema",
            "route",
            "source_binding",
            "requirements",
            "teaming_commitment",
            "intent_receipt",
            "owner_reviewed",
        },
        where="facts",
    )
    if obj["schema"] != SCHEMA_FACTS:
        raise ContractError("facts.schema invalid")
    route = obj["route"]
    if route not in {"UNKNOWN", "TEAMING", "PRIME"}:
        raise ContractError("facts.route invalid")
    if type(obj["owner_reviewed"]) is not bool:
        raise ContractError("facts.owner_reviewed must be bool")

    source_binding = _normalize_source_binding(obj["source_binding"])
    commitment = _normalize_commitment(obj["teaming_commitment"])
    if route != "TEAMING" and commitment["status"] == "CONFIRMED":
        raise ContractError("confirmed teaming commitment requires TEAMING route")
    requirements = _normalize_requirements(obj["requirements"], route=route, commitment=commitment)
    return {
        "schema": SCHEMA_FACTS,
        "route": route,
        "source_binding": source_binding,
        "requirements": requirements,
        "teaming_commitment": commitment,
        "intent_receipt": _normalize_intent_receipt(obj["intent_receipt"]),
        "owner_reviewed": obj["owner_reviewed"],
    }

from __future__ import annotations

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

from ._parse_models import GATE_STATES

def _parse_gate(value: Any, index: int) -> dict[str, Any]:
    label = f"evidence.qualification_gates[{index}]"
    obj = require_object(value, label)
    require_exact_keys(
        obj,
        required={
            "gate_id",
            "mandatory",
            "state",
            "owner_action",
            "decided_at",
            "decision_ref",
            "decision_sha256",
        },
        label=label,
    )
    return {
        "gate_id": require_ref(obj["gate_id"], f"{label}.gate_id"),
        "mandatory": require_bool(obj["mandatory"], f"{label}.mandatory"),
        "state": require_enum(obj["state"], GATE_STATES, f"{label}.state"),
        "owner_action": require_string(
            obj["owner_action"], f"{label}.owner_action", maximum=512
        ),
        "decided_at": require_timestamp(obj["decided_at"], f"{label}.decided_at"),
        "decision_ref": require_ref(obj["decision_ref"], f"{label}.decision_ref"),
        "decision_sha256": require_sha256(
            obj["decision_sha256"], f"{label}.decision_sha256"
        ),
    }

def _parse_commitment(value: Any, index: int) -> dict[str, Any]:
    label = f"evidence.commitments[{index}]"
    obj = require_object(value, label)
    require_exact_keys(
        obj,
        required={
            "commitment_id",
            "mandatory",
            "approved",
            "safe_fact",
            "decided_at",
            "approval_ref",
            "approval_sha256",
        },
        label=label,
    )
    return {
        "commitment_id": require_ref(obj["commitment_id"], f"{label}.commitment_id"),
        "mandatory": require_bool(obj["mandatory"], f"{label}.mandatory"),
        "approved": require_bool(obj["approved"], f"{label}.approved"),
        "safe_fact": require_string(
            obj["safe_fact"], f"{label}.safe_fact", maximum=1024
        ),
        "decided_at": require_timestamp(obj["decided_at"], f"{label}.decided_at"),
        "approval_ref": require_ref(obj["approval_ref"], f"{label}.approval_ref"),
        "approval_sha256": require_sha256(
            obj["approval_sha256"], f"{label}.approval_sha256"
        ),
    }

def _parse_requirements(value: Any) -> dict[str, tuple[str, ...]]:
    obj = require_object(value, "evidence.requirements")
    require_exact_keys(
        obj,
        required={"required_asset_ids", "required_gate_ids", "required_commitment_ids"},
        label="evidence.requirements",
    )
    return {
        "required_asset_ids": tuple(
            require_ref_list(obj["required_asset_ids"], "evidence.requirements.required_asset_ids")
        ),
        "required_gate_ids": tuple(
            require_ref_list(obj["required_gate_ids"], "evidence.requirements.required_gate_ids")
        ),
        "required_commitment_ids": tuple(
            require_ref_list(
                obj["required_commitment_ids"],
                "evidence.requirements.required_commitment_ids",
            )
        ),
    }


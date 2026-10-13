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

from ._parse_models import (
    EVIDENCE_SCHEMA,
    GATE_STATES,
    INPUT_SCHEMA,
    INTERPRETATIONS,
    PREP_STATES,
    RECEIPT_SCHEMA,
    RELEASE_CLASSES,
    ROOTS_SCHEMA,
    SOURCE_CLASSES,
    ParsedCandidate,
    ParsedEvidence,
    ParsedRoot,
    _parse_opportunity,
    parse_candidate,
)
from ._parse_evidence_rows import (
    _parse_asset,
    _parse_interpretation,
    _parse_observation,
    _parse_release,
)
from ._parse_qualification_rows import (
    _parse_commitment,
    _parse_gate,
    _parse_requirements,
)

def parse_evidence(value: Any) -> ParsedEvidence:
    obj = require_object(value, "evidence")
    require_exact_keys(
        obj,
        required={
            "schema",
            "root_id",
            "generation",
            "captured_at",
            "opportunity",
            "counterparty_sender_refs",
            "requirements",
            "observations",
            "interpretations",
            "assets",
            "releases",
            "qualification_gates",
            "commitments",
        },
        label="evidence",
    )
    if require_string(obj["schema"], "evidence.schema", maximum=128) != EVIDENCE_SCHEMA:
        raise ControlError(f"evidence.schema must be {EVIDENCE_SCHEMA}")
    opportunity = _parse_opportunity(obj["opportunity"], "evidence.opportunity")
    senders = require_ref_list(
        obj["counterparty_sender_refs"],
        "evidence.counterparty_sender_refs",
        allow_empty=False,
    )
    observations_raw = require_list(obj["observations"], "evidence.observations")
    interpretations_raw = require_list(obj["interpretations"], "evidence.interpretations")
    assets_raw = require_list(obj["assets"], "evidence.assets")
    releases_raw = require_list(obj["releases"], "evidence.releases")
    gates_raw = require_list(obj["qualification_gates"], "evidence.qualification_gates")
    commitments_raw = require_list(obj["commitments"], "evidence.commitments")
    observations = [_parse_observation(item, index) for index, item in enumerate(observations_raw)]
    interpretations = [
        _parse_interpretation(item, index) for index, item in enumerate(interpretations_raw)
    ]
    assets = [_parse_asset(item, index) for index, item in enumerate(assets_raw)]
    releases = [_parse_release(item, index) for index, item in enumerate(releases_raw)]
    gates = [_parse_gate(item, index) for index, item in enumerate(gates_raw)]
    commitments = [_parse_commitment(item, index) for index, item in enumerate(commitments_raw)]
    require_unique([row["observation_id"] for row in observations], "evidence observation IDs")
    require_unique([row["message_ref"] for row in observations], "evidence message refs")
    require_unique(
        [row["interpretation_id"] for row in interpretations], "evidence interpretation IDs"
    )
    require_unique(
        [row["observation_id"] for row in interpretations],
        "evidence interpretation observation IDs",
    )
    require_unique([row["asset_id"] for row in assets], "evidence asset IDs")
    require_unique([row["release_id"] for row in releases], "evidence release IDs")
    require_unique([row["gate_id"] for row in gates], "evidence gate IDs")
    require_unique([row["commitment_id"] for row in commitments], "evidence commitment IDs")
    requirements = _parse_requirements(obj["requirements"])
    normalized = {
        "schema": EVIDENCE_SCHEMA,
        "root_id": require_ref(obj["root_id"], "evidence.root_id"),
        "generation": require_int(obj["generation"], "evidence.generation", minimum=1),
        "captured_at": require_timestamp(obj["captured_at"], "evidence.captured_at"),
        "opportunity": opportunity,
        "counterparty_sender_refs": senders,
        "requirements": {key: list(value) for key, value in requirements.items()},
        "observations": observations,
        "interpretations": interpretations,
        "assets": assets,
        "releases": releases,
        "qualification_gates": gates,
        "commitments": commitments,
    }
    return ParsedEvidence(
        normalized,
        normalized["root_id"],
        normalized["generation"],
        normalized["captured_at"],
        opportunity["opportunity_id"],
        opportunity["counterparty_ref"],
        opportunity["thread_id"],
        tuple(senders),
        requirements,
        tuple(observations),
        tuple(interpretations),
        tuple(assets),
        tuple(releases),
        tuple(gates),
        tuple(commitments),
    )

def _parse_root(value: Any, index: int) -> ParsedRoot:
    label = f"trusted_roots.roots[{index}]"
    obj = require_object(value, label)
    required = {
        "root_id",
        "opportunity_id",
        "counterparty_ref",
        "thread_id",
        "generation",
        "active_from",
        "expires_at",
        "policy_sha256",
        "evidence_sha256",
        "counterparty_sender_refs_sha256",
        "observations_sha256",
        "interpretations_sha256",
        "assets_sha256",
        "releases_sha256",
        "qualification_gates_sha256",
        "commitments_sha256",
        "requirements_sha256",
    }
    require_exact_keys(obj, required=required, label=label)
    active_from = require_timestamp(obj["active_from"], f"{label}.active_from")
    expires_at = require_timestamp(obj["expires_at"], f"{label}.expires_at")
    if expires_at <= active_from:
        raise ControlError(f"{label}.expires_at must be after active_from")
    normalized = {
        "root_id": require_ref(obj["root_id"], f"{label}.root_id"),
        "opportunity_id": require_ref(obj["opportunity_id"], f"{label}.opportunity_id"),
        "counterparty_ref": require_ref(obj["counterparty_ref"], f"{label}.counterparty_ref"),
        "thread_id": require_ref(obj["thread_id"], f"{label}.thread_id"),
        "generation": require_int(obj["generation"], f"{label}.generation", minimum=1),
        "active_from": active_from,
        "expires_at": expires_at,
        "policy_sha256": require_sha256(obj["policy_sha256"], f"{label}.policy_sha256"),
        "evidence_sha256": require_sha256(obj["evidence_sha256"], f"{label}.evidence_sha256"),
        "counterparty_sender_refs_sha256": require_sha256(
            obj["counterparty_sender_refs_sha256"],
            f"{label}.counterparty_sender_refs_sha256",
        ),
        "observations_sha256": require_sha256(
            obj["observations_sha256"], f"{label}.observations_sha256"
        ),
        "interpretations_sha256": require_sha256(
            obj["interpretations_sha256"], f"{label}.interpretations_sha256"
        ),
        "assets_sha256": require_sha256(obj["assets_sha256"], f"{label}.assets_sha256"),
        "releases_sha256": require_sha256(
            obj["releases_sha256"], f"{label}.releases_sha256"
        ),
        "qualification_gates_sha256": require_sha256(
            obj["qualification_gates_sha256"],
            f"{label}.qualification_gates_sha256",
        ),
        "commitments_sha256": require_sha256(
            obj["commitments_sha256"], f"{label}.commitments_sha256"
        ),
        "requirements_sha256": require_sha256(
            obj["requirements_sha256"], f"{label}.requirements_sha256"
        ),
    }
    return ParsedRoot(
        normalized,
        normalized["root_id"],
        normalized["opportunity_id"],
        normalized["counterparty_ref"],
        normalized["thread_id"],
        normalized["generation"],
        active_from,
        expires_at,
    )

def parse_roots(value: Any) -> tuple[dict[str, Any], tuple[ParsedRoot, ...]]:
    obj = require_object(value, "trusted_roots")
    require_exact_keys(obj, required={"schema", "roots"}, label="trusted_roots")
    if require_string(obj["schema"], "trusted_roots.schema", maximum=128) != ROOTS_SCHEMA:
        raise ControlError(f"trusted_roots.schema must be {ROOTS_SCHEMA}")
    roots_raw = require_list(obj["roots"], "trusted_roots.roots")
    roots = tuple(_parse_root(item, index) for index, item in enumerate(roots_raw))
    require_unique([root.root_id for root in roots], "trusted root IDs")
    require_unique([root.opportunity_id for root in roots], "trusted root opportunity IDs")
    normalized = {"schema": ROOTS_SCHEMA, "roots": [root.value for root in roots]}
    return normalized, roots


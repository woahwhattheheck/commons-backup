from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

POLICY_SCHEMA = "agentic-gxp-lineage-policy/v1"
BATCH_SCHEMA = "agentic-gxp-lineage-batch/v1"
CASE_SCHEMA = "agentic-gxp-lineage-case/v1"
MANIFEST_SCHEMA = "agentic-gxp-lineage-manifest/v1"
RECEIPT_SCHEMA = "agentic-gxp-lineage-receipt/v1"

AUTHORITY = "QA_REVIEW_READY_EVIDENCE_ONLY"
MAX_JSON_BYTES = 2_000_000
MAX_CASES = 2_000
MAX_SOURCES = 16
MAX_TOOLS = 32
MAX_STRING_BYTES = 512
MAX_ID_BYTES = 128
MAX_AGE_SECONDS = 30 * 24 * 3600

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#-]{2,127}$")
_ALLOWED_RISKS = {"LOW", "MEDIUM", "HIGH"}
_ALLOWED_CHANGE_STATES = {"APPROVED", "PENDING", "REJECTED", "SUPERSEDED"}
_ALLOWED_APPROVAL_DECISIONS = {"APPROVE", "REJECT"}


class GateInputError(ValueError):
    """Malformed evidence that cannot safely be interpreted by the gate."""


def _dict(value: Any, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise GateInputError(f"{name} must be an object")
    return value


def _keys(obj: dict[str, Any], expected: set[str], name: str) -> None:
    got = set(obj)
    if got != expected:
        raise GateInputError(
            f"{name} has wrong fields; missing={sorted(expected-got)}, extra={sorted(got-expected)}"
        )


def _string(value: Any, name: str, *, max_bytes: int = MAX_STRING_BYTES) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > max_bytes:
        raise GateInputError(f"{name} must be a non-empty bounded string")
    return value


def _identifier(value: Any, name: str) -> str:
    value = _string(value, name, max_bytes=MAX_ID_BYTES)
    if _ID.fullmatch(value) is None:
        raise GateInputError(f"{name} is not a canonical identifier")
    return value


def _reference(value: Any, name: str) -> str:
    value = _string(value, name, max_bytes=MAX_ID_BYTES)
    if _REF.fullmatch(value) is None:
        raise GateInputError(f"{name} is not a canonical reference")
    return value


def _hex64(value: Any, name: str) -> str:
    value = _string(value, name, max_bytes=64)
    if _HEX64.fullmatch(value) is None:
        raise GateInputError(f"{name} must be lowercase sha256 hex")
    return value


def _bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise GateInputError(f"{name} must be a boolean")
    return value


def _int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise GateInputError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _utc(value: Any, name: str) -> datetime:
    value = _string(value, name, max_bytes=64)
    if not value.endswith("Z"):
        raise GateInputError(f"{name} must end in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise GateInputError(f"{name} is not ISO-8601 UTC") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise GateInputError(f"{name} must be UTC")
    return parsed


def _canonical(value: Any) -> bytes:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GateInputError("value is not canonical JSON") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise GateInputError("canonical JSON exceeds 2 MB gate limit")
    return raw


def digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _catalog(raw: Any, name: str) -> dict[str, dict[str, str]]:
    obj = _dict(raw, name)
    if not 1 <= len(obj) <= 128:
        raise GateInputError(f"{name} cardinality is out of bounds")
    out: dict[str, dict[str, str]] = {}
    for raw_id, raw_spec in sorted(obj.items()):
        ident = _identifier(raw_id, f"{name} id")
        spec = _dict(raw_spec, f"{name}.{ident}")
        _keys(spec, {"version", "sha256"}, f"{name}.{ident}")
        out[ident] = {
            "version": _identifier(spec["version"], f"{name}.{ident}.version"),
            "sha256": _hex64(spec["sha256"], f"{name}.{ident}.sha256"),
        }
    return out


def _string_set(raw: Any, name: str, *, maximum: int = 128) -> tuple[str, ...]:
    if type(raw) is not list or not 1 <= len(raw) <= maximum:
        raise GateInputError(f"{name} must be a non-empty bounded array")
    values = tuple(_identifier(value, f"{name}[]") for value in raw)
    if len(values) != len(set(values)):
        raise GateInputError(f"{name} contains duplicates")
    return tuple(sorted(values))


def _parse_policy(raw: Any) -> dict[str, Any]:
    obj = _dict(raw, "policy")
    _keys(
        obj,
        {
            "schema",
            "max_evidence_age_seconds",
            "allowed_artifact_types",
            "allowed_batch_standards",
            "allowed_risk_classes",
            "allowed_actor_roles",
            "reviewer_roles_by_risk",
            "approved_datasets",
            "approved_models",
            "approved_tools",
            "approved_prompt_policies",
        },
        "policy",
    )
    if obj["schema"] != POLICY_SCHEMA:
        raise GateInputError("unsupported policy schema")
    age = _int(
        obj["max_evidence_age_seconds"],
        "policy.max_evidence_age_seconds",
        0,
        MAX_AGE_SECONDS,
    )
    artifacts = _string_set(obj["allowed_artifact_types"], "policy.allowed_artifact_types")
    standards = _string_set(obj["allowed_batch_standards"], "policy.allowed_batch_standards")
    risks = _string_set(obj["allowed_risk_classes"], "policy.allowed_risk_classes")
    if not set(risks).issubset(_ALLOWED_RISKS):
        raise GateInputError("policy contains unsupported risk class")
    actor_roles = _string_set(obj["allowed_actor_roles"], "policy.allowed_actor_roles")

    reviewers_raw = _dict(obj["reviewer_roles_by_risk"], "policy.reviewer_roles_by_risk")
    if set(reviewers_raw) != set(risks):
        raise GateInputError("reviewer role policy must cover exactly the allowed risk classes")
    reviewer_roles: dict[str, tuple[str, ...]] = {}
    for risk, raw_roles in sorted(reviewers_raw.items()):
        roles = _string_set(raw_roles, f"policy.reviewer_roles_by_risk.{risk}")
        if not set(roles).issubset(set(actor_roles)):
            raise GateInputError("reviewer role is not an allowed actor role")
        reviewer_roles[risk] = roles

    return {
        "age": age,
        "artifacts": artifacts,
        "standards": standards,
        "risks": risks,
        "actor_roles": actor_roles,
        "reviewer_roles": reviewer_roles,
        "datasets": _catalog(obj["approved_datasets"], "policy.approved_datasets"),
        "models": _catalog(obj["approved_models"], "policy.approved_models"),
        "tools": _catalog(obj["approved_tools"], "policy.approved_tools"),
        "prompts": _catalog(obj["approved_prompt_policies"], "policy.approved_prompt_policies"),
    }


def _catalog_binding(raw: Any, name: str) -> dict[str, str]:
    obj = _dict(raw, name)
    _keys(obj, {"id", "version", "sha256"}, name)
    return {
        "id": _identifier(obj["id"], f"{name}.id"),
        "version": _identifier(obj["version"], f"{name}.version"),
        "sha256": _hex64(obj["sha256"], f"{name}.sha256"),
    }


def _catalog_ok(binding: dict[str, str], approved: dict[str, dict[str, str]]) -> bool:
    return approved.get(binding["id"]) == {
        "version": binding["version"],
        "sha256": binding["sha256"],
    }



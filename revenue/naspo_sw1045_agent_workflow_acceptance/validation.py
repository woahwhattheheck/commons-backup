from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

SCHEMA = "naspo-sw1045-agent-workflow-acceptance/v1"
RECEIPT_SCHEMA = "naspo-sw1045-agent-workflow-acceptance-receipt/v1"
HEX64 = frozenset("0123456789abcdef")
ALLOWED_OPERATIONS = frozenset({
    "CREATE", "UPDATE", "DELETE", "APPROVE", "PROVISION", "ASSIGN", "OTHER_STATE_CHANGE"
})
ALLOWED_TRANSPORT = frozenset({"SUCCESS", "FAILURE", "UNKNOWN"})
ALLOWED_RECONCILIATION = frozenset({"NONE", "SUCCEEDED", "FAILED", "NOT_FOUND", "AMBIGUOUS"})


class GateError(ValueError):
    pass


def _strict_dict(value: Any, name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise GateError(f"{name} must be a plain object")
    for key in value:
        if type(key) is not str:
            raise GateError(f"{name} keys must be strings")
    return value


def _strict_list(value: Any, name: str) -> list[Any]:
    if type(value) is not list:
        raise GateError(f"{name} must be an array")
    return value


def _strict_str(value: Any, name: str, *, nonempty: bool = True) -> str:
    if type(value) is not str:
        raise GateError(f"{name} must be a string")
    if nonempty and not value.strip():
        raise GateError(f"{name} must not be empty")
    if len(value) > 512:
        raise GateError(f"{name} too long")
    return value


def _strict_int(value: Any, name: str, *, minimum: int = 0, maximum: int = 86400) -> int:
    if type(value) is not int:
        raise GateError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise GateError(f"{name} outside allowed range")
    return value


def _hex64(value: Any, name: str) -> str:
    text = _strict_str(value, name)
    if len(text) != 64 or any(ch not in HEX64 for ch in text):
        raise GateError(f"{name} must be lowercase sha256 hex")
    return text


def _instant(value: Any, name: str) -> datetime:
    text = _strict_str(value, name)
    if not text.endswith("Z"):
        raise GateError(f"{name} must use explicit UTC Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise GateError(f"{name} is not RFC3339 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise GateError(f"{name} must be UTC")
    return parsed


def _canonical(value: Any) -> bytes:
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise GateError("value is not canonical-JSON encodable") from exc
    return text.encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def load_json_strict(text: str) -> Any:
    def no_dupes(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise GateError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    try:
        return json.loads(text, object_pairs_hook=no_dupes, parse_constant=lambda token: (_ for _ in ()).throw(GateError(f"non-finite JSON number: {token}")))
    except json.JSONDecodeError as exc:
        raise GateError("malformed JSON") from exc


def _exact_keys(obj: Mapping[str, Any], allowed: set[str], required: set[str], name: str) -> None:
    keys = set(obj)
    missing = required - keys
    extra = keys - allowed
    if missing:
        raise GateError(f"{name} missing fields: {','.join(sorted(missing))}")
    if extra:
        raise GateError(f"{name} has unknown fields: {','.join(sorted(extra))}")


def _normalize_packet(packet: Any) -> dict[str, Any]:
    root = _strict_dict(packet, "packet")
    _exact_keys(
        root,
        {"schema", "workflow_id", "request_id", "principal_id", "resource_scope", "action", "policy", "snapshot", "approval", "attempts"},
        {"schema", "workflow_id", "request_id", "principal_id", "resource_scope", "action", "policy", "snapshot", "approval", "attempts"},
        "packet",
    )
    if _strict_str(root["schema"], "schema") != SCHEMA:
        raise GateError("unsupported schema")

    workflow_id = _strict_str(root["workflow_id"], "workflow_id")
    request_id = _strict_str(root["request_id"], "request_id")
    principal_id = _strict_str(root["principal_id"], "principal_id")
    resource_scope = _strict_str(root["resource_scope"], "resource_scope")

    action = _strict_dict(root["action"], "action")
    _exact_keys(action, {"operation", "target", "payload_digest"}, {"operation", "target", "payload_digest"}, "action")
    operation = _strict_str(action["operation"], "action.operation")
    if operation not in ALLOWED_OPERATIONS:
        raise GateError("action.operation is not state-changing allowlist")
    target = _strict_str(action["target"], "action.target")
    payload_digest = _hex64(action["payload_digest"], "action.payload_digest")

    policy = _strict_dict(root["policy"], "policy")
    _exact_keys(policy, {"version", "digest"}, {"version", "digest"}, "policy")
    policy_version = _strict_str(policy["version"], "policy.version")
    policy_digest = _hex64(policy["digest"], "policy.digest")

    snapshot = _strict_dict(root["snapshot"], "snapshot")
    _exact_keys(snapshot, {"digest", "captured_at", "max_age_seconds"}, {"digest", "captured_at", "max_age_seconds"}, "snapshot")
    snapshot_digest = _hex64(snapshot["digest"], "snapshot.digest")
    captured_at = _strict_str(snapshot["captured_at"], "snapshot.captured_at")
    _instant(captured_at, "snapshot.captured_at")
    max_age_seconds = _strict_int(snapshot["max_age_seconds"], "snapshot.max_age_seconds", minimum=1, maximum=86400)

    approval = _strict_dict(root["approval"], "approval")
    _exact_keys(
        approval,
        {"approver_id", "role", "action_digest", "approved_at", "expires_at"},
        {"approver_id", "role", "action_digest", "approved_at", "expires_at"},
        "approval",
    )
    approver_id = _strict_str(approval["approver_id"], "approval.approver_id")
    role = _strict_str(approval["role"], "approval.role")
    approval_action_digest = _hex64(approval["action_digest"], "approval.action_digest")
    approved_at = _strict_str(approval["approved_at"], "approval.approved_at")
    expires_at = _strict_str(approval["expires_at"], "approval.expires_at")
    _instant(approved_at, "approval.approved_at")
    _instant(expires_at, "approval.expires_at")

    attempts_out: list[dict[str, Any]] = []
    for index, raw in enumerate(_strict_list(root["attempts"], "attempts")):
        attempt = _strict_dict(raw, f"attempts[{index}]")
        _exact_keys(
            attempt,
            {"attempt_id", "idempotency_key", "dispatched_at", "transport_result", "provider_effect_id", "provider_state_digest", "reconciled_at", "reconciliation"},
            {"attempt_id", "idempotency_key", "dispatched_at", "transport_result", "provider_effect_id", "provider_state_digest", "reconciled_at", "reconciliation"},
            f"attempts[{index}]",
        )
        attempt_id = _strict_str(attempt["attempt_id"], f"attempts[{index}].attempt_id")
        idem = _hex64(attempt["idempotency_key"], f"attempts[{index}].idempotency_key")
        dispatched_at = _strict_str(attempt["dispatched_at"], f"attempts[{index}].dispatched_at")
        _instant(dispatched_at, f"attempts[{index}].dispatched_at")
        transport = _strict_str(attempt["transport_result"], f"attempts[{index}].transport_result")
        if transport not in ALLOWED_TRANSPORT:
            raise GateError(f"attempts[{index}].transport_result invalid")

        effect = attempt["provider_effect_id"]
        if effect is not None:
            effect = _strict_str(effect, f"attempts[{index}].provider_effect_id")
        state_digest = attempt["provider_state_digest"]
        if state_digest is not None:
            state_digest = _hex64(state_digest, f"attempts[{index}].provider_state_digest")
        reconciled_at = attempt["reconciled_at"]
        if reconciled_at is not None:
            reconciled_at = _strict_str(reconciled_at, f"attempts[{index}].reconciled_at")
            _instant(reconciled_at, f"attempts[{index}].reconciled_at")
        reconciliation = _strict_str(attempt["reconciliation"], f"attempts[{index}].reconciliation")
        if reconciliation not in ALLOWED_RECONCILIATION:
            raise GateError(f"attempts[{index}].reconciliation invalid")

        attempts_out.append({
            "attempt_id": attempt_id,
            "idempotency_key": idem,
            "dispatched_at": dispatched_at,
            "transport_result": transport,
            "provider_effect_id": effect,
            "provider_state_digest": state_digest,
            "reconciled_at": reconciled_at,
            "reconciliation": reconciliation,
        })

    return {
        "schema": SCHEMA,
        "workflow_id": workflow_id,
        "request_id": request_id,
        "principal_id": principal_id,
        "resource_scope": resource_scope,
        "action": {"operation": operation, "target": target, "payload_digest": payload_digest},
        "policy": {"version": policy_version, "digest": policy_digest},
        "snapshot": {"digest": snapshot_digest, "captured_at": captured_at, "max_age_seconds": max_age_seconds},
        "approval": {
            "approver_id": approver_id,
            "role": role,
            "action_digest": approval_action_digest,
            "approved_at": approved_at,
            "expires_at": expires_at,
        },
        "attempts": attempts_out,
    }


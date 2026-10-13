"""Local operation sessions and deterministic replay using the existing engine."""

from __future__ import annotations

import json
import re
from typing import Any, Mapping

from .core import (
    AuditError,
    AuthorizationError,
    BrainError,
    InternalBrain,
    SchemaError,
    canonical_json,
    sha256_hex,
    verify_audit,
)

OPERATIONS_SCHEMA = "internal-brain-operations/v1"
SESSION_SCHEMA = "internal-brain-session/v1"
_HEX_DIGEST = re.compile(r"[0-9a-f]{64}")


def digest(value: Any) -> str:
    return sha256_hex(canonical_json(value))


def _copy(value: Any) -> Any:
    return json.loads(canonical_json(value))


def _keys(value: Any, expected: set[str], where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaError(f"{where} must be an object")
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    if missing or extra:
        raise SchemaError(f"{where} keys mismatch: missing={missing}, unsupported={extra}")
    return value


def operations_from_value(value: Any) -> list[dict[str, Any]]:
    envelope = _keys(value, {"schema", "operations"}, "operations file")
    if envelope["schema"] != OPERATIONS_SCHEMA:
        raise SchemaError(f"operations file.schema must be {OPERATIONS_SCHEMA!r}")
    operations = envelope["operations"]
    if not isinstance(operations, list) or not 1 <= len(operations) <= 1000:
        raise SchemaError("operations must contain 1..1000 operation objects")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(operations):
        operation = _keys(raw, {"operation", "request"}, f"operations[{index}]")
        if operation["operation"] not in ("query", "ingest"):
            raise SchemaError(f"operations[{index}].operation must be 'query' or 'ingest'")
        normalized.append(_copy(operation))
    return normalized


def _run_operation(brain: InternalBrain, operation: Mapping[str, Any], index: int) -> dict[str, Any]:
    outcome: dict[str, Any] = {"index": index, "operation": operation["operation"]}
    try:
        if operation["operation"] == "query":
            receipt = brain.query(operation["request"])
        else:
            request = _keys(
                operation["request"], {"tenant_id", "actor_user_id", "document"}, "ingest request"
            )
            receipt = brain.ingest(
                tenant_id=request["tenant_id"],
                actor_user_id=request["actor_user_id"],
                document=request["document"],
            )
        outcome.update(status="ok", receipt=receipt)
    except AuthorizationError as exc:
        outcome.update(
            status="denied",
            error={"type": "AuthorizationError", "code": exc.code, "message": str(exc)},
        )
    except BrainError as exc:
        outcome.update(status="error", error={"type": type(exc).__name__, "message": str(exc)})
    return outcome


def summarize(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    succeeded = sum(outcome["status"] == "ok" for outcome in outcomes)
    denied = sum(outcome["status"] == "denied" for outcome in outcomes)
    failed = sum(outcome["status"] == "error" for outcome in outcomes)
    no_match = sum(
        outcome.get("receipt", {}).get("decision_code") == "NO_AUTHORIZED_MATCH"
        for outcome in outcomes
    )
    return {
        "operation_count": len(outcomes),
        "successful_count": succeeded,
        "denied_count": denied,
        "failed_count": failed,
        "no_authorized_match_count": no_match,
        "exit_code": 2 if failed else 3 if denied else 0,
    }


def execute_session(
    bundle: Mapping[str, Any], operations_value: Any, *, audit_actor_user_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    operations = operations_from_value(operations_value)
    brain = InternalBrain(bundle)
    initial_bundle = brain.export_bundle()
    # Authorize export before operations. Never inspect private audit storage.
    brain.audit_events(tenant_id=brain.tenant_id, actor_user_id=audit_actor_user_id)
    outcomes = [_run_operation(brain, operation, index) for index, operation in enumerate(operations)]
    events = brain.audit_events(tenant_id=brain.tenant_id, actor_user_id=audit_actor_user_id)
    verification = verify_audit(events)
    final_bundle = brain.export_bundle()
    artifact = {
        "schema": SESSION_SCHEMA,
        "initial_bundle": initial_bundle,
        "initial_bundle_sha256": digest(initial_bundle),
        "audit_actor_user_id": audit_actor_user_id,
        "operations": operations,
        "outcomes": outcomes,
        "audit": {"events": events, "verification": verification},
        "final_bundle_sha256": digest(final_bundle),
        "summary": summarize(outcomes),
    }
    artifact["artifact_sha256"] = digest(artifact)
    return artifact, final_bundle


def artifact_summary(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_sha256": artifact["artifact_sha256"],
        "initial_bundle_sha256": artifact["initial_bundle_sha256"],
        "final_bundle_sha256": artifact["final_bundle_sha256"],
        "audit_head_digest": artifact["audit"]["verification"]["head_digest"],
        "audit_event_count": artifact["audit"]["verification"]["event_count"],
        "summary": artifact["summary"],
    }


def replay_session(
    value: Any, *, audit_actor_user_id: str, expected_artifact_sha256: str | None = None
) -> dict[str, Any]:
    artifact = _keys(
        value,
        {
            "schema", "initial_bundle", "initial_bundle_sha256", "audit_actor_user_id",
            "operations", "outcomes", "audit", "final_bundle_sha256", "summary", "artifact_sha256",
        },
        "session artifact",
    )
    if artifact["schema"] != SESSION_SCHEMA:
        raise SchemaError(f"session artifact.schema must be {SESSION_SCHEMA!r}")
    supplied_digest = artifact["artifact_sha256"]
    if not isinstance(supplied_digest, str) or not _HEX_DIGEST.fullmatch(supplied_digest):
        raise SchemaError("session artifact.artifact_sha256 must be 64 lowercase hex characters")
    unsigned = {key: item for key, item in artifact.items() if key != "artifact_sha256"}
    if digest(unsigned) != supplied_digest:
        raise AuditError("session artifact digest mismatch")
    if expected_artifact_sha256 is not None:
        if not _HEX_DIGEST.fullmatch(expected_artifact_sha256):
            raise SchemaError("expected artifact digest must be 64 lowercase hex characters")
        if supplied_digest != expected_artifact_sha256:
            raise AuditError("session artifact does not match the independently retained expected digest")
    if artifact["audit_actor_user_id"] != audit_actor_user_id:
        raise AuthorizationError("AUDIT_ACTOR_MISMATCH", "declared audit reader differs from the recorded session")
    audit = _keys(artifact["audit"], {"events", "verification"}, "session artifact.audit")
    if not isinstance(audit["events"], list):
        raise SchemaError("session artifact.audit.events must be a list")
    verified = verify_audit(audit["events"])
    if canonical_json(verified) != canonical_json(audit["verification"]):
        raise AuditError("retained audit verification does not match the event chain")
    if digest(artifact["initial_bundle"]) != artifact["initial_bundle_sha256"]:
        raise AuditError("initial bundle digest mismatch")
    replayed, _ = execute_session(
        artifact["initial_bundle"],
        {"schema": OPERATIONS_SCHEMA, "operations": artifact["operations"]},
        audit_actor_user_id=audit_actor_user_id,
    )
    for field in (
        "initial_bundle", "initial_bundle_sha256", "operations", "outcomes", "audit",
        "final_bundle_sha256", "summary", "artifact_sha256",
    ):
        if canonical_json(replayed[field]) != canonical_json(artifact[field]):
            raise AuditError(f"session replay mismatch: {field}")
    return {"replay_verified": True, **artifact_summary(replayed)}

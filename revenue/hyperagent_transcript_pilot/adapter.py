"""Deterministic, offline agent-event -> Slack transcript projection.

This module has no provider I/O. It accepts synthetic/provider-neutral event
documents, normalizes three supported backend schemas, and emits deterministic
logical transcript artifacts suitable for a later buyer-owned Slack sender.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


class ProjectionError(ValueError):
    """Base class for deterministic projection failures."""


class SchemaError(ProjectionError):
    """Raised when an input event does not satisfy a supported backend schema."""


class EventConflict(ProjectionError):
    """Raised when a source event id is replayed with changed semantics."""


@dataclass(frozen=True)
class CanonicalEvent:
    backend: str
    source_event_id: str
    run_id: str
    sequence: int
    kind: str
    text: str
    action_id: str | None = None
    generation: int | None = None
    approval: Mapping[str, Any] | None = None

    @property
    def source_key(self) -> str:
        return f"{self.backend}:{self.source_event_id}"

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "source_event_id": self.source_event_id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "kind": self.kind,
            "text": self.text,
            "action_id": self.action_id,
            "generation": self.generation,
            "approval": _canonical_json_value(self.approval),
        }

    def semantic_digest(self) -> str:
        return _sha256_json(self.semantic_payload())


@dataclass(frozen=True)
class RejectedEvent:
    source_key: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"source_key": self.source_key, "reason": self.reason}


@dataclass(frozen=True)
class ProjectionResult:
    new_messages: tuple[dict[str, Any], ...]
    duplicate_event_count: int
    rejected: tuple[RejectedEvent, ...]


def _canonical_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_json_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(item) for item in value]
    raise SchemaError(f"unsupported JSON value type: {type(value).__name__}")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        _canonical_json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaError(f"{field} must be an object")
    return value


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{field} must be a non-empty string")
    return value.strip()


def _require_sequence(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SchemaError(f"{field} must be a non-negative integer")
    return value


def _optional_generation(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _require_sequence(value, field)


def _optional_approval(value: Any, field: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    # Detach the semantic generation from caller-owned nested containers before
    # any digest or authorization decision.
    approval = _require_mapping(value, field)
    detached = _canonical_json_value(approval)
    assert isinstance(detached, dict)
    return detached


def _normalize_alpha(raw: Mapping[str, Any]) -> CanonicalEvent:
    return CanonicalEvent(
        backend="alpha",
        source_event_id=_require_str(raw.get("id"), "alpha.id"),
        run_id=_require_str(raw.get("run_id"), "alpha.run_id"),
        sequence=_require_sequence(raw.get("seq"), "alpha.seq"),
        kind=_require_str(raw.get("kind"), "alpha.kind"),
        text=_require_str(raw.get("text"), "alpha.text"),
        action_id=(
            _require_str(raw.get("action_id"), "alpha.action_id")
            if raw.get("action_id") is not None
            else None
        ),
        generation=_optional_generation(raw.get("generation"), "alpha.generation"),
        approval=_optional_approval(raw.get("approval"), "alpha.approval"),
    )


def _normalize_beta(raw: Mapping[str, Any]) -> CanonicalEvent:
    execution = _require_mapping(raw.get("execution"), "beta.execution")
    payload = _require_mapping(raw.get("payload"), "beta.payload")
    approval = payload.get("approval")
    return CanonicalEvent(
        backend="beta",
        source_event_id=_require_str(raw.get("event_id"), "beta.event_id"),
        run_id=_require_str(execution.get("id"), "beta.execution.id"),
        sequence=_require_sequence(raw.get("ordinal"), "beta.ordinal"),
        kind=_require_str(raw.get("type"), "beta.type"),
        text=_require_str(payload.get("text"), "beta.payload.text"),
        action_id=(
            _require_str(payload.get("action"), "beta.payload.action")
            if payload.get("action") is not None
            else None
        ),
        generation=_optional_generation(payload.get("generation"), "beta.payload.generation"),
        approval=_optional_approval(approval, "beta.payload.approval"),
    )


def _normalize_gamma(raw: Mapping[str, Any]) -> CanonicalEvent:
    data = _require_mapping(raw.get("data"), "gamma.data")
    approval = data.get("approval")
    return CanonicalEvent(
        backend="gamma",
        source_event_id=_require_str(raw.get("uid"), "gamma.uid"),
        run_id=_require_str(raw.get("session"), "gamma.session"),
        sequence=_require_sequence(raw.get("index"), "gamma.index"),
        kind=_require_str(raw.get("event"), "gamma.event"),
        text=_require_str(data.get("body"), "gamma.data.body"),
        action_id=(
            _require_str(data.get("action_key"), "gamma.data.action_key")
            if data.get("action_key") is not None
            else None
        ),
        generation=_optional_generation(data.get("rev"), "gamma.data.rev"),
        approval=_optional_approval(approval, "gamma.data.approval"),
    )


def normalize_event(raw: Mapping[str, Any]) -> CanonicalEvent:
    """Normalize one supported backend event into the canonical form."""
    document = _require_mapping(raw, "event")
    backend = _require_str(document.get("backend"), "backend")
    if backend == "alpha":
        event = _normalize_alpha(document)
    elif backend == "beta":
        event = _normalize_beta(document)
    elif backend == "gamma":
        event = _normalize_gamma(document)
    else:
        raise SchemaError(f"unsupported backend: {backend}")

    if event.kind == "action":
        if event.action_id is None:
            raise SchemaError("action event requires action_id")
        if event.generation is None:
            raise SchemaError("action event requires generation")
    elif event.action_id is not None or event.generation is not None or event.approval is not None:
        raise SchemaError("non-action event cannot carry action approval fields")
    return event


def _approval_reason(event: CanonicalEvent) -> str | None:
    """Return None only when approval exactly authorizes this action generation."""
    if event.kind != "action":
        return None
    approval = event.approval
    if not isinstance(approval, Mapping):
        return "approval_missing"
    required = {
        "run_id": event.run_id,
        "action_id": event.action_id,
        "generation": event.generation,
        "decision": "approved",
    }
    for field, expected in required.items():
        if field not in approval:
            return f"approval_missing_{field}"
        if approval[field] != expected:
            return f"approval_mismatch_{field}"
    if set(approval) != set(required):
        return "approval_unrecognized_fields"
    return None


def _message_for(event: CanonicalEvent) -> dict[str, Any]:
    message_id = hashlib.sha256(
        f"{event.run_id}\0{event.source_key}\0{event.semantic_digest()}".encode("utf-8")
    ).hexdigest()[:24]
    return {
        "logical_message_id": message_id,
        "run_id": event.run_id,
        "sequence": event.sequence,
        "kind": event.kind,
        "text": event.text,
        "source": {"backend": event.backend, "event_id": event.source_event_id},
        "action": (
            {
                "action_id": event.action_id,
                "generation": event.generation,
                "approval": "approved",
            }
            if event.kind == "action"
            else None
        ),
    }


class ProjectionLedger:
    """In-memory exactly-once semantic ledger for offline transcript projection."""

    def __init__(self) -> None:
        self._event_digests: dict[str, str] = {}
        self._messages: dict[str, dict[str, Any]] = {}

    def project_batch(self, raw_events: Sequence[Mapping[str, Any]]) -> ProjectionResult:
        """Validate a batch atomically, then add newly accepted logical messages.

        Source replays with identical semantics are no-ops. Reuse of a source id
        with different semantics raises EventConflict before any batch mutation.
        Approval-invalid action events are rejected and emit no message.
        """
        events = [normalize_event(raw) for raw in raw_events]

        batch_digests: dict[str, str] = {}
        for event in events:
            digest = event.semantic_digest()
            existing_batch = batch_digests.get(event.source_key)
            if existing_batch is not None and existing_batch != digest:
                raise EventConflict(f"source event changed inside batch: {event.source_key}")
            batch_digests[event.source_key] = digest
            existing = self._event_digests.get(event.source_key)
            if existing is not None and existing != digest:
                raise EventConflict(f"source event changed after acceptance: {event.source_key}")

        first_by_source: dict[str, CanonicalEvent] = {}
        for event in events:
            first_by_source.setdefault(event.source_key, event)

        new_events: list[CanonicalEvent] = []
        duplicate_count = 0
        rejected: list[RejectedEvent] = []
        for source_key in sorted(first_by_source):
            event = first_by_source[source_key]
            copies = sum(1 for candidate in events if candidate.source_key == source_key)
            if source_key in self._event_digests:
                duplicate_count += copies
                continue
            duplicate_count += max(0, copies - 1)
            reason = _approval_reason(event)
            if reason is not None:
                rejected.append(RejectedEvent(source_key, reason))
                continue
            new_events.append(event)

        # Rejected source generations are still consumed into the semantic ledger.
        # This prevents a caller from reusing the same source id with changed
        # approval semantics after an initial fail-closed decision.
        for item in rejected:
            event = first_by_source[item.source_key]
            self._event_digests[event.source_key] = event.semantic_digest()

        new_messages: list[dict[str, Any]] = []
        for event in sorted(new_events, key=lambda item: (item.run_id, item.sequence, item.source_key)):
            digest = event.semantic_digest()
            message = _message_for(event)
            self._event_digests[event.source_key] = digest
            self._messages[message["logical_message_id"]] = message
            new_messages.append(message)

        return ProjectionResult(
            new_messages=tuple(new_messages),
            duplicate_event_count=duplicate_count,
            rejected=tuple(sorted(rejected, key=lambda item: item.source_key)),
        )

    def snapshot(self) -> dict[str, Any]:
        """Return a deterministic logical-transcript snapshot."""
        by_run: dict[str, list[dict[str, Any]]] = {}
        for message in self._messages.values():
            by_run.setdefault(message["run_id"], []).append(message)

        transcripts: list[dict[str, Any]] = []
        for run_id in sorted(by_run):
            messages = sorted(
                by_run[run_id],
                key=lambda item: (
                    item["sequence"],
                    item["source"]["backend"],
                    item["source"]["event_id"],
                    item["logical_message_id"],
                ),
            )
            transcripts.append(
                {
                    "thread_key": hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:20],
                    "run_id": run_id,
                    "messages": messages,
                }
            )

        return {
            "schema": "hyperagent-transcript-pilot/v1",
            "transcript_count": len(transcripts),
            "message_count": sum(len(item["messages"]) for item in transcripts),
            "transcripts": transcripts,
        }

    def snapshot_bytes(self) -> bytes:
        return _json_bytes(self.snapshot()) + b"\n"


def load_fixture(path: str | Path) -> list[dict[str, Any]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise SchemaError("fixture root must be an array")
    return [dict(_require_mapping(item, f"fixture[{index}]")) for index, item in enumerate(value)]

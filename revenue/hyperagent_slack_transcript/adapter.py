"""Hardened public authority surface for the Hyperagent transcript pilot.

The normalization and deterministic projection primitives landed in #15057 are
preserved byte-for-byte in ``_legacy_adapter``.  This module owns the public
approval boundary: approval data cannot self-authorize, and caller data cannot
supply the clock used to decide whether an approval is current.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
from typing import Any, Iterable, Mapping

from . import _legacy_adapter as _legacy

SCHEMA = _legacy.SCHEMA
STATE_SCHEMA = _legacy.STATE_SCHEMA
ALLOWED_BACKENDS = _legacy.ALLOWED_BACKENDS
ALLOWED_KINDS = _legacy.ALLOWED_KINDS

ValidationError = _legacy.ValidationError
ConflictError = _legacy.ConflictError
ApprovalError = _legacy.ApprovalError
NormalizedEvent = _legacy.NormalizedEvent

load_strict_json = _legacy.load_strict_json
canonical_bytes = _legacy.canonical_bytes
normalize_event = _legacy.normalize_event

_APPROVAL_KEYS = {
    "approval_id",
    "run_id",
    "action_id",
    "generation",
    "event_semantics_sha256",
    "decision",
    "issued_at",
    "expires_at",
    "evidence_sha256",
    "authority_tag",
}
_SIGNED_APPROVAL_KEYS = _APPROVAL_KEYS - {"authority_tag"}


@dataclass(frozen=True)
class Approval:
    approval_id: str
    run_id: str
    action_id: str
    generation: int
    event_semantics_sha256: str
    decision: str
    issued_at: datetime
    expires_at: datetime
    evidence_sha256: str
    authority_tag: str
    receipt_sha256: str


def _approval_key(value: Any) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise ApprovalError("approval authority key must be bytes")
    key = bytes(value)
    if not 32 <= len(key) <= 128:
        raise ApprovalError("approval authority key must be 32..128 bytes")
    return key


def _signed_approval_fields(obj: Mapping[str, Any]) -> tuple[dict[str, Any], datetime, datetime]:
    approval_id = _legacy._opaque_id(obj["approval_id"], "approval_id")
    run_id = _legacy._text(obj["run_id"], "run_id", max_len=64)
    action_id = _legacy._opaque_id(obj["action_id"], "action_id")
    generation = _legacy._int(obj["generation"], "generation", minimum=1, maximum=1_000_000)
    event_semantics_sha256 = _legacy._sha256(
        obj["event_semantics_sha256"], "event_semantics_sha256"
    )
    decision = _legacy._text(obj["decision"], "decision", max_len=16)
    if decision not in {"APPROVE", "DENY"}:
        raise ApprovalError("approval decision must be APPROVE or DENY")
    issued = _legacy._utc(obj["issued_at"], "issued_at")
    expires = _legacy._utc(obj["expires_at"], "expires_at")
    if expires <= issued:
        raise ApprovalError("approval expiry must be after issue time")
    evidence = _legacy._sha256(obj["evidence_sha256"], "evidence_sha256")
    signed = {
        "approval_id": approval_id,
        "run_id": run_id,
        "action_id": action_id,
        "generation": generation,
        "event_semantics_sha256": event_semantics_sha256,
        "decision": decision,
        "issued_at": issued.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence_sha256": evidence,
    }
    if set(signed) != _SIGNED_APPROVAL_KEYS:
        raise AssertionError("internal approval field mismatch")
    return signed, issued, expires


def normalize_approval(raw: Any, *, approval_auth_key: bytes) -> Approval:
    """Validate one approval and authenticate one exact event generation.

    ``authority_tag`` is lowercase HMAC-SHA256 over the canonical JSON bytes of
    all other approval fields.  The signed event-semantics digest binds source
    identity, thread, sequence, text, action and generation.  The key is
    retained runtime authority supplied outside this repository.  Possessing an
    approval object is therefore not sufficient to mint, alter or amplify
    authority across distinct events.
    """

    obj = _legacy._plain_dict(raw, "approval")
    _legacy._exact_keys(obj, _APPROVAL_KEYS, "approval")
    key = _approval_key(approval_auth_key)
    signed, issued, expires = _signed_approval_fields(obj)
    tag = _legacy._sha256(obj["authority_tag"], "authority_tag")
    expected = hmac.new(key, canonical_bytes(signed), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(tag, expected):
        raise ApprovalError("approval authority authentication failed")
    receipt = _legacy._sha({**signed, "authority_tag": tag})
    return Approval(
        approval_id=signed["approval_id"],
        run_id=signed["run_id"],
        action_id=signed["action_id"],
        generation=signed["generation"],
        event_semantics_sha256=signed["event_semantics_sha256"],
        decision=signed["decision"],
        issued_at=issued,
        expires_at=expires,
        evidence_sha256=signed["evidence_sha256"],
        authority_tag=tag,
        receipt_sha256=receipt,
    )


def _trusted_now() -> datetime:
    """Process UTC used for approval freshness; never supplied by event data."""

    return datetime.now(timezone.utc).replace(microsecond=0)


class TranscriptProjector:
    """Stateful deterministic projector with a retained approval-authority key.

    Text-only projection works without a key.  Mutating-action approvals are
    ignored unless the trusted runtime instantiated the projector with a key.
    The public ``ingest`` API intentionally has no caller-supplied ``as_of``.
    """

    def __init__(self, *, approval_auth_key: bytes | None = None) -> None:
        self._approval_auth_key = None if approval_auth_key is None else _approval_key(approval_auth_key)
        self._source_semantics: dict[str, str] = {}
        self._approval_semantics: dict[str, str] = {}
        self._messages: dict[str, dict[str, dict[str, Any]]] = {}
        self._thread_meta: dict[str, tuple[str, str]] = {}

    def _approval_for(
        self,
        event: NormalizedEvent,
        approvals: Iterable[Approval],
        now: datetime,
    ) -> Approval | None:
        event_semantics_sha256 = _legacy._sha(event.semantics())
        matches = [
            approval
            for approval in approvals
            if approval.run_id == event.run_id
            and approval.action_id == event.action_id
            and approval.generation == event.generation
            and approval.event_semantics_sha256 == event_semantics_sha256
        ]
        if len(matches) != 1:
            return None
        approval = matches[0]
        if approval.decision != "APPROVE":
            return None
        if not (approval.issued_at <= now < approval.expires_at):
            return None
        return approval

    def _ingest_at(
        self,
        raw_events: Iterable[Any],
        raw_approvals: Iterable[Any],
        *,
        now: datetime,
    ) -> dict[str, Any]:
        if now.tzinfo != timezone.utc or now.microsecond:
            raise ValidationError("internal approval clock must be whole-second UTC")

        raw_approval_list = list(raw_approvals)
        if len(raw_approval_list) > 10_000:
            raise ApprovalError("too many approvals")

        approvals: list[Approval] = []
        if self._approval_auth_key is not None:
            approvals = [
                normalize_approval(raw, approval_auth_key=self._approval_auth_key)
                for raw in raw_approval_list
            ]

        for approval in approvals:
            semantics = _legacy._sha({
                "run_id": approval.run_id,
                "action_id": approval.action_id,
                "generation": approval.generation,
                "event_semantics_sha256": approval.event_semantics_sha256,
                "decision": approval.decision,
                "issued_at": approval.issued_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "expires_at": approval.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "evidence_sha256": approval.evidence_sha256,
                "authority_tag": approval.authority_tag,
            })
            previous = self._approval_semantics.get(approval.approval_id)
            if previous is not None and previous != semantics:
                raise ConflictError("approval id replayed with changed semantics")
            self._approval_semantics.setdefault(approval.approval_id, semantics)

        events = [normalize_event(raw) for raw in raw_events]
        if len(events) > 100_000:
            raise ValidationError("too many events")
        events.sort(key=lambda event: (event.thread_id, event.sequence, event.source_key))

        newly_emitted: list[str] = []
        held: list[dict[str, str]] = []
        for event in events:
            semantic_digest = _legacy._sha(event.semantics())
            previous = self._source_semantics.get(event.source_key)
            if previous is not None and previous != semantic_digest:
                raise ConflictError(f"source event changed semantics: {event.source_key}")
            self._source_semantics.setdefault(event.source_key, semantic_digest)

            existing = self._messages.get(event.thread_id, {})
            if event.event_id in existing:
                continue

            approval_id: str | None = None
            approval_receipt: str | None = None
            if event.kind == "MUTATING_ACTION":
                approval = self._approval_for(event, approvals, now)
                if approval is None:
                    reason = (
                        "APPROVAL_AUTHORITY_UNAVAILABLE"
                        if self._approval_auth_key is None and raw_approval_list
                        else "APPROVAL_NOT_CURRENT_FOR_EXACT_EVENT_GENERATION"
                    )
                    held.append({"event_id": event.event_id, "reason": reason})
                    continue
                approval_id = approval.approval_id
                approval_receipt = approval.receipt_sha256

            message = {
                "message_id": event.event_id,
                "sequence": event.sequence,
                "kind": event.kind,
                "text": event.text,
                "approval_id": approval_id,
                "approval_receipt_sha256": approval_receipt,
                "source": {
                    "backend": event.backend,
                    "source_event_id": event.source_event_id,
                    "semantic_sha256": semantic_digest,
                },
            }
            bucket = self._messages.setdefault(event.thread_id, {})
            if event.event_id in bucket:
                raise ConflictError("normalized event id collision")
            bucket[event.event_id] = message
            self._thread_meta[event.thread_id] = (event.run_id, event.thread_ref)
            newly_emitted.append(event.event_id)

        artifacts = self.artifacts()
        return {
            "schema": STATE_SCHEMA,
            "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "artifact_count": len(artifacts),
            "message_count": sum(len(artifact["messages"]) for artifact in artifacts),
            "new_message_ids": sorted(newly_emitted),
            "held": sorted(held, key=lambda item: (item["reason"], item["event_id"])),
            "artifacts": artifacts,
            "state_sha256": _legacy._sha({
                "artifacts": artifacts,
                "source_semantics": self._source_semantics,
                "approval_semantics": self._approval_semantics,
            }),
        }

    def ingest(self, raw_events: Iterable[Any], raw_approvals: Iterable[Any]) -> dict[str, Any]:
        return self._ingest_at(raw_events, raw_approvals, now=_trusted_now())

    def artifacts(self) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        for thread_id in sorted(self._messages):
            messages = sorted(
                self._messages[thread_id].values(),
                key=lambda message: (message["sequence"], message["message_id"]),
            )
            if not messages:
                continue
            run_id, thread_ref = self._thread_meta[thread_id]
            body = {
                "schema": SCHEMA,
                "thread_id": thread_id,
                "run_id": run_id,
                "thread_ref": thread_ref,
                "messages": messages,
                "external_send_authorized": False,
            }
            artifacts.append({**body, "artifact_sha256": _legacy._sha(body)})
        return artifacts


def project_fixture(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Project the checked synthetic text-only fixture deterministically.

    The fixture may carry a deterministic ``as_of`` only because this surface
    refuses approvals and mutating actions.  It therefore cannot be used to
    backdate or mint action authority.
    """

    obj = _legacy._plain_dict(dict(fixture), "fixture")
    _legacy._exact_keys(obj, {"as_of", "events", "approvals"}, "fixture")
    if type(obj["events"]) is not list or type(obj["approvals"]) is not list:
        raise ValidationError("fixture events/approvals must be arrays")
    if obj["approvals"]:
        raise ApprovalError("synthetic fixture surface cannot carry approvals")
    normalized = [normalize_event(raw) for raw in obj["events"]]
    if any(event.kind != "TEXT" for event in normalized):
        raise ApprovalError("synthetic fixture surface cannot carry mutating actions")
    projector = TranscriptProjector()
    return projector._ingest_at(obj["events"], [], now=_legacy._utc(obj["as_of"], "as_of"))


__all__ = [
    "Approval",
    "ApprovalError",
    "ConflictError",
    "NormalizedEvent",
    "TranscriptProjector",
    "ValidationError",
    "canonical_bytes",
    "load_strict_json",
    "normalize_approval",
    "normalize_event",
    "project_fixture",
]

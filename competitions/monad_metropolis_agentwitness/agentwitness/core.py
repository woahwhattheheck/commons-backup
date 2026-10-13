"""Deterministic reference model for AgentWitness.

No network, wallet, or provider side effects. The module models the contract's
claim/finalize/reconcile state machine and the canonical off-chain event key.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import IntEnum
import hashlib
import json
import re
import threading
from typing import Any, Mapping

EVENT_VERSION = "agentwitness-event-v1"
RECEIPT_VERSION = "agentwitness-receipt-v1"
EVENT_DOMAIN = b"agentwitness:event:v1\x00"
INTENT_DOMAIN = b"agentwitness:intent:v1\x00"
OUTCOME_DOMAIN = b"agentwitness:outcome:v1\x00"
RECEIPT_DOMAIN = b"agentwitness:receipt:v1\x00"
MAX_JSON_BYTES = 16_384
TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,95}$")
EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,191}$")
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
HEX32_RE = re.compile(r"^0x[0-9a-f]{64}$")


class AgentWitnessError(ValueError):
    pass


class DuplicateKeyError(AgentWitnessError):
    pass


class AlreadyClaimed(AgentWitnessError):
    pass


class NotClaimed(AgentWitnessError):
    pass


class NotClaimant(AgentWitnessError):
    pass


class AlreadyFinalized(AgentWitnessError):
    pass


class NotReconcilable(AgentWitnessError):
    pass


class Outcome(IntEnum):
    NONE = 0
    COMPLETED = 1
    REJECTED = 2
    OUTCOME_UNKNOWN = 3
    HELD = 4


class Resolution(IntEnum):
    NONE = 0
    COMPLETED = 1
    REJECTED = 2
    HELD = 3


@dataclass(frozen=True)
class EventDescriptor:
    version: str
    network: str
    namespace: str
    provider: str
    event_id: str


@dataclass
class Claim:
    claimant: str
    intent_hash: str
    outcome: Outcome = Outcome.NONE
    outcome_hash: str | None = None
    resolution: Resolution = Resolution.NONE
    resolution_hash: str | None = None


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_loads(raw: bytes | str) -> Any:
    if isinstance(raw, str):
        raw_b = raw.encode("utf-8")
    elif isinstance(raw, (bytes, bytearray)):
        raw_b = bytes(raw)
    else:
        raise TypeError("raw JSON must be bytes or str")
    if len(raw_b) > MAX_JSON_BYTES:
        raise AgentWitnessError("JSON exceeds size limit")
    try:
        text = raw_b.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AgentWitnessError("JSON must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                AgentWitnessError(f"non-finite JSON number: {value}")
            ),
        )
    except DuplicateKeyError:
        raise
    except AgentWitnessError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AgentWitnessError("invalid JSON") from exc


def canonical_json(value: Any) -> bytes:
    # allow_json_nan=False is the default behavior we want to make explicit.
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AgentWitnessError("value is not canonical JSON") from exc


def _exact_object(obj: Mapping[str, Any], required: set[str]) -> None:
    if set(obj) != required:
        missing = sorted(required - set(obj))
        extra = sorted(set(obj) - required)
        raise AgentWitnessError(f"schema mismatch missing={missing} extra={extra}")


def _strict_str(value: Any, field: str) -> str:
    if type(value) is not str:
        raise AgentWitnessError(f"{field} must be a string")
    return value


def validate_event(value: Mapping[str, Any]) -> EventDescriptor:
    if type(value) is not dict:
        raise AgentWitnessError("event must be an object")
    _exact_object(value, {"version", "network", "namespace", "provider", "event_id"})
    version = _strict_str(value["version"], "version")
    network = _strict_str(value["network"], "network")
    namespace = _strict_str(value["namespace"], "namespace")
    provider = _strict_str(value["provider"], "provider")
    event_id = _strict_str(value["event_id"], "event_id")
    if version != EVENT_VERSION:
        raise AgentWitnessError("unsupported event version")
    for field_name, token in (("network", network), ("namespace", namespace), ("provider", provider)):
        if not TOKEN_RE.fullmatch(token):
            raise AgentWitnessError(f"invalid {field_name}")
    if not EVENT_ID_RE.fullmatch(event_id):
        raise AgentWitnessError("invalid event_id")
    return EventDescriptor(version, network, namespace, provider, event_id)


def canonical_event_bytes(value: Mapping[str, Any] | EventDescriptor) -> bytes:
    if isinstance(value, EventDescriptor):
        descriptor = value
    else:
        descriptor = validate_event(value)
    return canonical_json(asdict(descriptor))


def _hash(domain: bytes, payload: bytes) -> str:
    return "0x" + hashlib.sha256(domain + payload).hexdigest()


def event_key(value: Mapping[str, Any] | EventDescriptor) -> str:
    return _hash(EVENT_DOMAIN, canonical_event_bytes(value))


def intent_hash(private_intent: bytes) -> str:
    if not isinstance(private_intent, bytes):
        raise TypeError("private_intent must be bytes")
    return _hash(INTENT_DOMAIN, private_intent)


def outcome_hash(private_outcome: bytes) -> str:
    if not isinstance(private_outcome, bytes):
        raise TypeError("private_outcome must be bytes")
    return _hash(OUTCOME_DOMAIN, private_outcome)


def _validate_hex32(value: str, field: str) -> str:
    if type(value) is not str or not HEX32_RE.fullmatch(value) or value == "0x" + "0" * 64:
        raise AgentWitnessError(f"{field} must be a nonzero lowercase bytes32 hex string")
    return value


def _validate_address(value: str) -> str:
    if type(value) is not str or not ADDRESS_RE.fullmatch(value) or int(value[2:], 16) == 0:
        raise AgentWitnessError("claimant must be a nonzero EVM address")
    return value.lower()


class InMemoryRegistry:
    """Thread-safe executable model of AgentWitnessRegistry.sol."""

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}
        self._lock = threading.Lock()

    def claim(self, key: str, claimant: str, intent: str) -> Claim:
        key = _validate_hex32(key, "event_key")
        claimant = _validate_address(claimant)
        intent = _validate_hex32(intent, "intent_hash")
        with self._lock:
            if key in self._claims:
                raise AlreadyClaimed(key)
            record = Claim(claimant=claimant, intent_hash=intent)
            self._claims[key] = record
            return Claim(**record.__dict__)

    def finalize(self, key: str, claimant: str, outcome: Outcome, outcome_digest: str) -> Claim:
        key = _validate_hex32(key, "event_key")
        claimant = _validate_address(claimant)
        outcome_digest = _validate_hex32(outcome_digest, "outcome_hash")
        if type(outcome) is not Outcome or outcome not in {
            Outcome.COMPLETED,
            Outcome.REJECTED,
            Outcome.OUTCOME_UNKNOWN,
            Outcome.HELD,
        }:
            raise AgentWitnessError("invalid outcome")
        with self._lock:
            record = self._claims.get(key)
            if record is None:
                raise NotClaimed(key)
            if record.claimant != claimant:
                raise NotClaimant(claimant)
            if record.outcome != Outcome.NONE:
                raise AlreadyFinalized(key)
            record.outcome = outcome
            record.outcome_hash = outcome_digest
            return Claim(**record.__dict__)

    def reconcile(self, key: str, claimant: str, resolution: Resolution, resolution_digest: str) -> Claim:
        key = _validate_hex32(key, "event_key")
        claimant = _validate_address(claimant)
        resolution_digest = _validate_hex32(resolution_digest, "resolution_hash")
        if type(resolution) is not Resolution or resolution not in {
            Resolution.COMPLETED,
            Resolution.REJECTED,
            Resolution.HELD,
        }:
            raise AgentWitnessError("invalid resolution")
        with self._lock:
            record = self._claims.get(key)
            if record is None:
                raise NotClaimed(key)
            if record.claimant != claimant:
                raise NotClaimant(claimant)
            if record.outcome != Outcome.OUTCOME_UNKNOWN or record.resolution != Resolution.NONE:
                raise NotReconcilable(key)
            record.resolution = resolution
            record.resolution_hash = resolution_digest
            return Claim(**record.__dict__)

    def read(self, key: str) -> Claim | None:
        key = _validate_hex32(key, "event_key")
        with self._lock:
            record = self._claims.get(key)
            return None if record is None else Claim(**record.__dict__)

    def effective_outcome(self, key: str) -> str:
        record = self.read(key)
        if record is None:
            return "UNCLAIMED"
        if record.outcome == Outcome.NONE:
            return "CLAIMED"
        if record.outcome == Outcome.OUTCOME_UNKNOWN and record.resolution != Resolution.NONE:
            return f"RECONCILED_{record.resolution.name}"
        return record.outcome.name


def make_receipt(key: str, claim: Claim) -> dict[str, Any]:
    key = _validate_hex32(key, "event_key")
    claimant = _validate_address(claim.claimant)
    intent = _validate_hex32(claim.intent_hash, "intent_hash")
    if claim.outcome == Outcome.NONE:
        outcome_digest = None
    else:
        outcome_digest = _validate_hex32(claim.outcome_hash or "", "outcome_hash")
    if claim.resolution == Resolution.NONE:
        resolution_digest = None
    else:
        resolution_digest = _validate_hex32(claim.resolution_hash or "", "resolution_hash")
    return {
        "version": RECEIPT_VERSION,
        "event_key": key,
        "claimant": claimant,
        "intent_hash": intent,
        "outcome": claim.outcome.name,
        "outcome_hash": outcome_digest,
        "resolution": claim.resolution.name,
        "resolution_hash": resolution_digest,
    }


def receipt_digest(receipt: Mapping[str, Any]) -> str:
    return _hash(RECEIPT_DOMAIN, canonical_json(dict(receipt)))

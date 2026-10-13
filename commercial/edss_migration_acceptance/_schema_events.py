"""Expectation, interface-event, and cutover schema normalization."""
from typing import Any
from ._core import *

def _validate_expected_event(raw: Any, *, where: str, policy: dict[str, Any]) -> dict[str, Any]:
    obj = _exact_object(raw, {"interface_id", "message_id", "logical_record_id", "source_sequence", "event_at", "payload_sha256"}, where=where)
    return {
        "interface_id": _safe_id(obj["interface_id"], where=f"{where}.interface_id", maximum=policy["max_id_chars"]),
        "message_id": _safe_id(obj["message_id"], where=f"{where}.message_id", maximum=policy["max_id_chars"]),
        "logical_record_id": _safe_id(obj["logical_record_id"], where=f"{where}.logical_record_id", maximum=policy["max_id_chars"]),
        "source_sequence": _integer(obj["source_sequence"], where=f"{where}.source_sequence", minimum=0, maximum=2**63 - 1),
        "event_at": _utc_text(_parse_utc(obj["event_at"], where=f"{where}.event_at")),
        "payload_sha256": _sha(obj["payload_sha256"], where=f"{where}.payload_sha256"),
    }


def _event_key(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        event["interface_id"],
        event["message_id"],
        event["logical_record_id"],
        event["source_sequence"],
        event["event_at"],
        event["payload_sha256"],
    )


def expected_events_digest(events: list[dict[str, Any]]) -> str:
    return sha256_hex(canonical_json_bytes(sorted(events, key=_event_key)))


def expected_record_ids_digest(ids: list[str]) -> str:
    return sha256_hex(canonical_json_bytes(sorted(ids)))


def _validate_expectation(raw: Any, *, policy: dict[str, Any]) -> dict[str, Any]:
    obj = _exact_object(raw, {"observation_id", "captured_at", "source_snapshot_id", "source_rows_sha256", "expected_record_ids", "expected_record_ids_sha256", "expected_events", "expected_events_sha256"}, where="packet.expectation")
    ids_raw = obj["expected_record_ids"]
    if type(ids_raw) is not list or not ids_raw or len(ids_raw) > policy["max_rows"]:
        raise EdssAcceptanceError("packet.expectation.expected_record_ids must be a nonempty bounded list")
    ids = [_safe_id(value, where=f"packet.expectation.expected_record_ids[{i}]", maximum=policy["max_id_chars"]) for i, value in enumerate(ids_raw)]
    if len(set(ids)) != len(ids):
        raise EdssAcceptanceError("duplicate expectation record id")
    ids = sorted(ids)
    ids_sha = _sha(obj["expected_record_ids_sha256"], where="packet.expectation.expected_record_ids_sha256")
    if ids_sha != expected_record_ids_digest(ids):
        raise EdssAcceptanceError("packet.expectation.expected_record_ids_sha256 mismatch")

    events_raw = obj["expected_events"]
    if type(events_raw) is not list or not events_raw or len(events_raw) > policy["max_events"]:
        raise EdssAcceptanceError("packet.expectation.expected_events must be a nonempty bounded list")
    events = [_validate_expected_event(value, where=f"packet.expectation.expected_events[{i}]", policy=policy) for i, value in enumerate(events_raw)]
    if len({_event_key(event) for event in events}) != len(events):
        raise EdssAcceptanceError("duplicate exact expected event")
    events = sorted(events, key=_event_key)
    events_sha = _sha(obj["expected_events_sha256"], where="packet.expectation.expected_events_sha256")
    if events_sha != expected_events_digest(events):
        raise EdssAcceptanceError("packet.expectation.expected_events_sha256 mismatch")
    return {
        "observation_id": _safe_id(obj["observation_id"], where="packet.expectation.observation_id", maximum=policy["max_id_chars"]),
        "captured_at": _utc_text(_parse_utc(obj["captured_at"], where="packet.expectation.captured_at")),
        "source_snapshot_id": _safe_id(obj["source_snapshot_id"], where="packet.expectation.source_snapshot_id", maximum=policy["max_id_chars"]),
        "source_rows_sha256": _sha(obj["source_rows_sha256"], where="packet.expectation.source_rows_sha256"),
        "expected_record_ids": ids,
        "expected_record_ids_sha256": ids_sha,
        "expected_events": events,
        "expected_events_sha256": events_sha,
    }


def _validate_ack(raw: Any, *, where: str, policy: dict[str, Any]) -> dict[str, str]:
    obj = _exact_object(raw, {"ack_id", "ack_at", "outcome"}, where=where)
    outcome = _string(obj["outcome"], where=f"{where}.outcome", maximum=16)
    if outcome not in {"ACKED", "REJECTED"}:
        raise EdssAcceptanceError(f"{where}.outcome invalid")
    return {
        "ack_id": _safe_id(obj["ack_id"], where=f"{where}.ack_id", maximum=policy["max_id_chars"]),
        "ack_at": _utc_text(_parse_utc(obj["ack_at"], where=f"{where}.ack_at")),
        "outcome": outcome,
    }


def _validate_observed_event(raw: Any, *, where: str, policy: dict[str, Any]) -> dict[str, Any]:
    obj = _exact_object(raw, {"interface_id", "message_id", "logical_record_id", "source_sequence", "event_at", "received_at", "payload_sha256", "acknowledgements"}, where=where)
    acks_raw = obj["acknowledgements"]
    if type(acks_raw) is not list or len(acks_raw) > policy["max_acks_per_event"]:
        raise EdssAcceptanceError(f"{where}.acknowledgements must be a bounded list")
    acks = [_validate_ack(value, where=f"{where}.acknowledgements[{i}]", policy=policy) for i, value in enumerate(acks_raw)]
    return {
        "interface_id": _safe_id(obj["interface_id"], where=f"{where}.interface_id", maximum=policy["max_id_chars"]),
        "message_id": _safe_id(obj["message_id"], where=f"{where}.message_id", maximum=policy["max_id_chars"]),
        "logical_record_id": _safe_id(obj["logical_record_id"], where=f"{where}.logical_record_id", maximum=policy["max_id_chars"]),
        "source_sequence": _integer(obj["source_sequence"], where=f"{where}.source_sequence", minimum=0, maximum=2**63 - 1),
        "event_at": _utc_text(_parse_utc(obj["event_at"], where=f"{where}.event_at")),
        "received_at": _utc_text(_parse_utc(obj["received_at"], where=f"{where}.received_at")),
        "payload_sha256": _sha(obj["payload_sha256"], where=f"{where}.payload_sha256"),
        "acknowledgements": sorted(acks, key=lambda ack: (ack["ack_at"], ack["ack_id"], ack["outcome"])),
    }


def _validate_cutover(raw: Any, *, policy: dict[str, Any]) -> dict[str, str]:
    obj = _exact_object(raw, {"window_id", "start", "end"}, where="packet.cutover")
    start = _parse_utc(obj["start"], where="packet.cutover.start")
    end = _parse_utc(obj["end"], where="packet.cutover.end")
    if end <= start:
        raise EdssAcceptanceError("packet.cutover end must be after start")
    if (end - start).total_seconds() > policy["max_cutover_seconds"]:
        raise EdssAcceptanceError("packet.cutover exceeds policy maximum")
    return {
        "window_id": _safe_id(obj["window_id"], where="packet.cutover.window_id", maximum=policy["max_id_chars"]),
        "start": _utc_text(start),
        "end": _utc_text(end),
    }



__all__ = ["expected_events_digest", "expected_record_ids_digest", "_event_key", "_validate_expectation", "_validate_observed_event", "_validate_cutover"]

"""Top-level EDSS acceptance packet normalization."""
from typing import Any
from ._core import *
from ._schema_records import _validate_snapshot, rows_digest
from ._schema_events import (
    _event_key, _validate_cutover, _validate_expectation, _validate_observed_event,
    expected_events_digest, expected_record_ids_digest,
)

def _validate_packet(raw: Any, policy: dict[str, Any]) -> dict[str, Any]:
    obj = _exact_object(raw, {"schema", "engagement_ref", "source_snapshot", "target_snapshot", "expectation", "interface_events", "cutover"}, where="packet")
    if obj["schema"] != PACKET_SCHEMA:
        raise EdssAcceptanceError("unsupported packet schema")
    source = _validate_snapshot(obj["source_snapshot"], role="SOURCE", where="packet.source_snapshot", policy=policy)
    target = _validate_snapshot(obj["target_snapshot"], role="TARGET", where="packet.target_snapshot", policy=policy)
    if source["snapshot_id"] == target["snapshot_id"]:
        raise EdssAcceptanceError("source and target snapshot IDs must differ")
    expectation = _validate_expectation(obj["expectation"], policy=policy)
    events_raw = obj["interface_events"]
    if type(events_raw) is not list or not events_raw or len(events_raw) > policy["max_events"]:
        raise EdssAcceptanceError("packet.interface_events must be a nonempty bounded list")
    events = [_validate_observed_event(value, where=f"packet.interface_events[{i}]", policy=policy) for i, value in enumerate(events_raw)]
    events = sorted(events, key=lambda event: (event["received_at"], event["interface_id"], event["message_id"], event["payload_sha256"]))
    return {
        "schema": PACKET_SCHEMA,
        "engagement_ref": _safe_id(obj["engagement_ref"], where="packet.engagement_ref", maximum=policy["max_id_chars"]),
        "source_snapshot": source,
        "target_snapshot": target,
        "expectation": expectation,
        "interface_events": events,
        "cutover": _validate_cutover(obj["cutover"], policy=policy),
    }


__all__ = ["rows_digest", "expected_events_digest", "expected_record_ids_digest", "_event_key", "_validate_packet"]

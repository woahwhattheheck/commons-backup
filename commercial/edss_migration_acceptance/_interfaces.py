"""Opaque interface-envelope acceptance reconciliation."""
from datetime import datetime
from typing import Any
from ._core import _parse_utc
from ._schema import _event_key

def _interface_results(events: list[dict[str, Any]], expected_events: list[dict[str, Any]], expected_record_ids: list[str], cutover: dict[str, str], *, as_of: datetime, policy: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    expected_by_key = {_event_key(event): event for event in expected_events}
    expected_keys = set(expected_by_key)
    seen_exact: dict[tuple[Any, ...], int] = {}
    by_message: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for event in events:
        key = _event_key(event)
        seen_exact[key] = seen_exact.get(key, 0) + 1
        by_message.setdefault((event["interface_id"], event["message_id"]), []).append(event)

    start = _parse_utc(cutover["start"], where="normalized.cutover.start")
    end = _parse_utc(cutover["end"], where="normalized.cutover.end")
    expected_records = set(expected_record_ids)
    results: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    contradictions: list[str] = []
    observed_expected: set[tuple[Any, ...]] = set()

    # Out-of-order is based on receive order per interface, ignoring exact replay copies.
    unique_for_sequence: list[dict[str, Any]] = []
    unique_keys: set[tuple[Any, ...]] = set()
    for event in events:
        key = _event_key(event)
        if key not in unique_keys:
            unique_keys.add(key)
            unique_for_sequence.append(event)
    last_sequence: dict[str, int] = {}
    last_received: dict[str, str] = {}
    out_of_order_keys: set[tuple[Any, ...]] = set()
    receive_tie_keys: set[tuple[Any, ...]] = set()
    for event in unique_for_sequence:
        interface_id = event["interface_id"]
        sequence = event["source_sequence"]
        received_at = event["received_at"]
        if interface_id in last_received and received_at == last_received[interface_id]:
            receive_tie_keys.add(_event_key(event))
            contradictions.append(f"{interface_id}: equal received_at leaves receive order unmeasured")
        last_received[interface_id] = received_at
        if interface_id in last_sequence and sequence <= last_sequence[interface_id]:
            out_of_order_keys.add(_event_key(event))
        last_sequence[interface_id] = max(sequence, last_sequence.get(interface_id, sequence))

    ack_owners: dict[str, set[tuple[Any, ...]]] = {}
    for event in events:
        for ack in event["acknowledgements"]:
            ack_owners.setdefault(ack["ack_id"], set()).add(_event_key(event))
    conflicting_ack_keys: set[tuple[Any, ...]] = set()
    for owners in ack_owners.values():
        if len(owners) > 1:
            conflicting_ack_keys.update(owners)

    for event in events:
        key = _event_key(event)
        if key in expected_keys:
            observed_expected.add(key)
        event_at = _parse_utc(event["event_at"], where="normalized.event.event_at")
        received_at = _parse_utc(event["received_at"], where="normalized.event.received_at")
        message_group = by_message[(event["interface_id"], event["message_id"])]
        message_variants = {_event_key(item) for item in message_group}
        ack_ids = [ack["ack_id"] for ack in event["acknowledgements"]]
        if event_at > received_at:
            contradictions.append(f"{event['interface_id']}/{event['message_id']}: received_at precedes event_at")
        if received_at > as_of:
            contradictions.append(f"{event['interface_id']}/{event['message_id']}: received_at is in the future")
        if (as_of - received_at).total_seconds() > policy["max_event_age_seconds"]:
            status = "STALE_EVENT"
        elif not (start <= event_at < end):
            status = "OUTSIDE_CUTOVER"
        elif len(message_variants) > 1:
            status = "MESSAGE_ID_CONFLICT"
        elif seen_exact[key] > 1:
            status = "REPLAY_DUPLICATE"
        elif event["logical_record_id"] not in expected_records:
            status = "UNEXPECTED_LOGICAL_RECORD"
        elif key not in expected_keys:
            status = "UNEXPECTED_EVENT"
        elif key in receive_tie_keys:
            status = "RECEIVE_TIME_AMBIGUOUS"
        elif key in out_of_order_keys:
            status = "OUT_OF_ORDER"
        elif len(set(ack_ids)) != len(ack_ids) or key in conflicting_ack_keys:
            status = "DUPLICATE_ACK_ID"
        elif len(event["acknowledgements"]) == 0:
            status = "MISSING_ACK"
        elif len(event["acknowledgements"]) > 1:
            status = "MULTIPLE_ACKS"
        else:
            ack = event["acknowledgements"][0]
            ack_at = _parse_utc(ack["ack_at"], where="normalized.ack.ack_at")
            if ack_at < received_at:
                contradictions.append(f"{event['interface_id']}/{event['message_id']}: ack_at precedes received_at")
                status = "ACK_CHRONOLOGY_INVALID"
            elif ack_at > as_of:
                contradictions.append(f"{event['interface_id']}/{event['message_id']}: ack_at is in the future")
                status = "ACK_CHRONOLOGY_INVALID"
            elif ack["outcome"] == "REJECTED":
                status = "REJECTED"
            else:
                status = "INTERFACE_OK"
        counts[status] = counts.get(status, 0) + 1
        results.append({
            "interface_id": event["interface_id"],
            "message_id": event["message_id"],
            "logical_record_id": event["logical_record_id"],
            "source_sequence": event["source_sequence"],
            "status": status,
        })

    for key in sorted(expected_keys - observed_expected):
        event = expected_by_key[key]
        status = "MISSING_EVENT"
        counts[status] = counts.get(status, 0) + 1
        results.append({
            "interface_id": event["interface_id"],
            "message_id": event["message_id"],
            "logical_record_id": event["logical_record_id"],
            "source_sequence": event["source_sequence"],
            "status": status,
        })
    results.sort(key=lambda item: (item["interface_id"], item["source_sequence"], item["message_id"], item["status"]))
    return results, dict(sorted(counts.items())), sorted(set(contradictions))



__all__ = ["_interface_results"]

"""Deterministic EDSS acceptance disposition evaluation."""
from datetime import datetime
from typing import Any
from ._core import *
from ._migration import _record_results
from ._interfaces import _interface_results

def _evaluate(packet: dict[str, Any], *, as_of: datetime, policy: dict[str, Any]) -> tuple[str, list[str], list[dict[str, Any]], dict[str, int], list[dict[str, Any]], dict[str, int]]:
    reasons: list[str] = []
    source = packet["source_snapshot"]
    target = packet["target_snapshot"]
    expectation = packet["expectation"]

    source_at = _parse_utc(source["captured_at"], where="normalized.source.captured_at")
    target_at = _parse_utc(target["captured_at"], where="normalized.target.captured_at")
    expectation_at = _parse_utc(expectation["captured_at"], where="normalized.expectation.captured_at")
    future = []
    for label, dt in (("source snapshot", source_at), ("target snapshot", target_at), ("expectation", expectation_at)):
        if dt > as_of:
            future.append(f"{label} is in the future")
    if future:
        return HOLD, future, [], {}, [], {}
    if target_at < source_at:
        return HOLD, ["target snapshot predates source snapshot"], [], {}, [], {}

    if expectation["source_snapshot_id"] != source["snapshot_id"]:
        reasons.append("expectation source snapshot binding mismatch")
    if expectation["source_rows_sha256"] != source["rows_sha256"]:
        reasons.append("expectation source rows digest mismatch")
    source_ids = sorted(row["record_id"] for row in source["rows"])
    if len(source_ids) == len(set(source_ids)) and expectation["expected_record_ids"] != source_ids:
        reasons.append("expected record set does not equal complete source record set")
    if reasons:
        return HOLD, reasons, [], {}, [], {}

    record_results, record_counts = _record_results(source["rows"], target["rows"], expectation["expected_record_ids"])
    interface_results, interface_counts, contradictions = _interface_results(
        packet["interface_events"], expectation["expected_events"], expectation["expected_record_ids"], packet["cutover"], as_of=as_of, policy=policy
    )
    if contradictions:
        return HOLD, contradictions, record_results, record_counts, interface_results, interface_counts

    if not source["complete_export"] or not target["complete_export"]:
        if not source["complete_export"]:
            reasons.append("source export is not declared complete")
        if not target["complete_export"]:
            reasons.append("target export is not declared complete")
        return EVIDENCE_INCOMPLETE, reasons, record_results, record_counts, interface_results, interface_counts

    stale_items = []
    if (as_of - source_at).total_seconds() > policy["max_snapshot_age_seconds"]:
        stale_items.append("source snapshot is stale")
    if (as_of - target_at).total_seconds() > policy["max_snapshot_age_seconds"]:
        stale_items.append("target snapshot is stale")
    if (as_of - expectation_at).total_seconds() > policy["max_expectation_age_seconds"]:
        stale_items.append("expectation evidence is stale")
    if stale_items or interface_counts.get("STALE_EVENT", 0):
        if interface_counts.get("STALE_EVENT", 0):
            stale_items.append("one or more interface events are stale")
        return EVIDENCE_STALE, stale_items, record_results, record_counts, interface_results, interface_counts

    bad_record_count = sum(count for status, count in record_counts.items() if status != "PARITY_OK")
    if bad_record_count:
        return MIGRATION_MISMATCH, [f"{bad_record_count} record acceptance finding(s) require resolution"], record_results, record_counts, interface_results, interface_counts

    bad_interface_count = sum(count for status, count in interface_counts.items() if status != "INTERFACE_OK")
    if bad_interface_count:
        return INTERFACE_MISMATCH, [f"{bad_interface_count} interface acceptance finding(s) require resolution"], record_results, record_counts, interface_results, interface_counts

    return ACCEPTANCE_READY, ["complete migration parity and interface acceptance evidence reconcile under policy"], record_results, record_counts, interface_results, interface_counts


__all__ = ["_evaluate"]

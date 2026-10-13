from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from commercial.edss_migration_acceptance.acceptance import (
    ACCEPTANCE_READY,
    DEFAULT_POLICY,
    EVIDENCE_INCOMPLETE,
    EVIDENCE_STALE,
    HOLD,
    INTERFACE_MISMATCH,
    MIGRATION_MISMATCH,
    EdssAcceptanceError,
    canonical_json_bytes,
    compile_acceptance,
    expected_events_digest,
    expected_record_ids_digest,
    load_json_strict,
    render_markdown,
    rows_digest,
    verify_receipt,
)

AS_OF = datetime(2026, 9, 13, 16, 32, 0, tzinfo=timezone.utc)


def h(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


def oid(label: str) -> str:
    """Durable identifier token: SHA-256 of a local synthetic label. Label stays out of packets."""
    return h(f"edss-opaque:{label}")


def row(record_id: str, **fields: str):
    return {
        "record_id": oid(record_id),
        "fields": [{"field_id": oid(key), "value_sha256": h(value)} for key, value in sorted(fields.items())],
    }


def expected_event(interface_id: str, message_id: str, record_id: str, seq: int, event_at: str, payload: str):
    return {
        "interface_id": interface_id,
        "message_id": message_id,
        "logical_record_id": record_id,
        "source_sequence": seq,
        "event_at": event_at,
        "payload_sha256": h(payload),
    }


def observed_from_expected(event, *, received_at=None, ack=True, rejected=False):
    received_at = received_at or event["event_at"]
    acks = []
    if ack:
        acks = [{
            "ack_id": oid(f"ack.{event['message_id']}"),
            "ack_at": received_at,
            "outcome": "REJECTED" if rejected else "ACKED",
        }]
    return {**event, "received_at": received_at, "acknowledgements": acks}


def snapshot(snapshot_id: str, role: str, rows, *, captured_at="2026-09-13T16:20:00Z", complete=True, revision="schema.synthetic.v1"):
    normalized = sorted(deepcopy(rows), key=lambda item: (item["record_id"], canonical_json_bytes(item["fields"])))
    return {
        "snapshot_id": snapshot_id,
        "system_role": role,
        "schema_revision": revision,
        "captured_at": captured_at,
        "complete_export": complete,
        "record_count": len(normalized),
        "rows_sha256": rows_digest(normalized),
        "rows": normalized,
    }


def ready_packet():
    source_rows = [
        row("rec.001", status="open", jurisdiction="north", revision="r1"),
        row("rec.002", status="closed", jurisdiction="south", revision="r4"),
        row("rec.003", status="open", jurisdiction="east", revision="r2"),
    ]
    target_rows = deepcopy(source_rows)
    expected = [
        expected_event(oid("iface.lab.synthetic"), oid("msg.001"), oid("rec.001"), 1, "2026-09-13T16:05:00Z", "payload-001"),
        expected_event(oid("iface.lab.synthetic"), oid("msg.002"), oid("rec.002"), 2, "2026-09-13T16:06:00Z", "payload-002"),
        expected_event(oid("iface.case.synthetic"), oid("msg.003"), oid("rec.003"), 1, "2026-09-13T16:07:00Z", "payload-003"),
    ]
    source = snapshot(oid("snap.source.synthetic.001"), "SOURCE", source_rows, revision=oid("schema.synthetic.v1"))
    target = snapshot(oid("snap.target.synthetic.001"), "TARGET", target_rows, captured_at="2026-09-13T16:30:00Z", revision=oid("schema.synthetic.v1"))
    ids = sorted(r["record_id"] for r in source_rows)
    expectation = {
        "observation_id": oid("expectation.synthetic.001"),
        "captured_at": "2026-09-13T16:21:00Z",
        "source_snapshot_id": source["snapshot_id"],
        "source_rows_sha256": source["rows_sha256"],
        "expected_record_ids": ids,
        "expected_record_ids_sha256": expected_record_ids_digest(ids),
        "expected_events": expected,
        "expected_events_sha256": expected_events_digest(expected),
    }
    return {
        "schema": "edss-migration-acceptance/v1",
        "engagement_ref": oid("engagement.synthetic.edss.001"),
        "source_snapshot": source,
        "target_snapshot": target,
        "expectation": expectation,
        "interface_events": [observed_from_expected(event, received_at=f"2026-09-13T16:{10+i:02d}:00Z") for i, event in enumerate(expected)],
        "cutover": {"window_id": oid("cutover.synthetic.001"), "start": "2026-09-13T16:00:00Z", "end": "2026-09-13T16:30:00Z"},
    }


def refresh_snapshot(packet, role: str):
    key = "source_snapshot" if role == "SOURCE" else "target_snapshot"
    packet[key]["rows"] = sorted(packet[key]["rows"], key=lambda item: (item["record_id"], canonical_json_bytes(item["fields"])))
    packet[key]["record_count"] = len(packet[key]["rows"])
    packet[key]["rows_sha256"] = rows_digest(packet[key]["rows"])
    if role == "SOURCE":
        packet["expectation"]["source_rows_sha256"] = packet[key]["rows_sha256"]
        ids = sorted({r["record_id"] for r in packet[key]["rows"]})
        packet["expectation"]["expected_record_ids"] = ids
        packet["expectation"]["expected_record_ids_sha256"] = expected_record_ids_digest(ids)


def refresh_expected_events(packet):
    packet["expectation"]["expected_events"] = sorted(packet["expectation"]["expected_events"], key=lambda e: (e["interface_id"], e["message_id"], e["logical_record_id"], e["source_sequence"], e["event_at"], e["payload_sha256"]))
    packet["expectation"]["expected_events_sha256"] = expected_events_digest(packet["expectation"]["expected_events"])



class AcceptanceTestBase(unittest.TestCase):
    def compile(self, packet=None, *, as_of=AS_OF, policy=DEFAULT_POLICY):
        return compile_acceptance(packet or ready_packet(), as_of=as_of, policy=policy)


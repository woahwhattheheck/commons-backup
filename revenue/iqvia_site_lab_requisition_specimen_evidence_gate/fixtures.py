"""Frozen synthetic acceptance fixtures for the v2 IQVIA Site Lab evidence gate."""
from __future__ import annotations

import copy
import hashlib
from typing import Any

from .gate import CODES, SCHEMA, compute_source_refs


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _refresh(packet: dict[str, Any], *source_names: str) -> None:
    refs = compute_source_refs(packet["sources"])
    for name in source_names:
        packet["source_refs"][name] = refs[name]


def _base(index: int) -> dict[str, Any]:
    packet_id = f"SLR-{index:04d}"
    lot = f"KIT-{(index % 7) + 1:02d}"
    sources = {
        "protocol": {
            "protocol_id": "PROTO-ALPHA",
            "visit_id": "VISIT-02",
        },
        "requisition": {
            "protocol_id": "PROTO-ALPHA",
            "visit_id": "VISIT-02",
            "version": "REQ-v3",
            "collection_window_start": "2026-09-13T08:00:00Z",
            "collection_window_end": "2026-09-13T16:00:00Z",
            "required_sample_type": "SERUM",
        },
        "kit": {
            "lot": lot,
            "expires_at": "2026-10-01T00:00:00Z",
            "transport_min_c": 2.0,
            "transport_max_c": 8.0,
        },
        "collection": {
            "collected_at": "2026-09-13T12:00:00Z",
            "sample_type": "SERUM",
            "kit_lot": lot,
            "requisition_version": "REQ-v3",
        },
        "courier": {
            "scan_id": f"COURIER-{index:04d}",
            "temperature_c": 4.0,
            "kit_lot": lot,
        },
        "accession": {
            "accession_id": f"ACC-{index:04d}",
            "sample_type": "SERUM",
            "method_id": "METHOD-CHEM-7",
            "requisition_version": "REQ-v3",
        },
        "method": {
            "method_id": "METHOD-CHEM-7",
            "allowed_sample_types": ["PLASMA", "SERUM"],
        },
        "queries": {
            "requisition_version": "REQ-v3",
            "items": [
                {
                    "query_id": f"Q-{index:04d}-1",
                    "status": "RESOLVED",
                    "resolution_evidence_hash": _h(f"{packet_id}:query-resolution"),
                }
            ],
        },
    }
    return {
        "schema": SCHEMA,
        "packet_id": packet_id,
        "sources": sources,
        "source_refs": compute_source_refs(sources),
    }


def frozen_packets() -> list[dict[str, Any]]:
    packets = [_base(i) for i in range(1, 181)]

    for packet in packets[145:150]:
        packet["sources"]["requisition"]["visit_id"] = "VISIT-03"
        _refresh(packet, "requisition")

    for packet in packets[150:155]:
        packet["sources"]["collection"]["requisition_version"] = "REQ-v2"
        _refresh(packet, "collection")

    for packet in packets[155:160]:
        packet["sources"]["kit"]["expires_at"] = "2026-09-12T23:59:59Z"
        _refresh(packet, "kit")

    for packet in packets[160:165]:
        packet["sources"]["collection"]["collected_at"] = "2026-09-13T17:00:00Z"
        _refresh(packet, "collection")

    for packet in packets[165:170]:
        packet["sources"]["courier"]["scan_id"] = None
        packet["sources"]["courier"]["temperature_c"] = None
        _refresh(packet, "courier")

    for packet in packets[170:175]:
        packet["sources"]["collection"]["sample_type"] = "WHOLE_BLOOD"
        _refresh(packet, "collection")

    for packet in packets[175:180]:
        packet["sources"]["queries"]["items"][0]["status"] = "OPEN"
        packet["sources"]["queries"]["items"][0]["resolution_evidence_hash"] = None
        _refresh(packet, "queries")

    return copy.deepcopy(packets)


def expected_holds() -> dict[str, list[str]]:
    return {
        code: [f"SLR-{i:04d}" for i in range(start, start + 5)]
        for code, start in zip(CODES, (146, 151, 156, 161, 166, 171, 176))
    }

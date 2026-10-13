#!/usr/bin/env python3
"""Build the journaled titan MOVE packet from public excerpt sidecars.

Claimed append offsets were dest FROM FILE (titan.gguf size
103803350291). This generator does not write titan.gguf. A first apply may
allocate from live EOF; APPLYING keeps fixed offsets; WRITTEN is read-only.

  python3 muhl_titan_move_packet.py          # write packet JSON
  python3 muhl_titan_move_packet.py --dry    # print, write nothing
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "host"))
from titan_move_offsets import (
    CLAIMED_APPEND_BASE,
    CLAIMED_APPEND_SOURCE,
    allocate_rows,
)

EXCERPT_DIR = os.path.join(REPO_ROOT, "excerpts", "20260823")
PACKET_PATH = os.path.join(EXCERPT_DIR, "titan_move_packet.json")
EXCERPT_REL = "excerpts/20260823"
CANONICAL_ORGAN_COUNT = 31
CLOSED_WRITE_RECEIPT = "p/claudelocal-titan-move-go-20260825-01.md"
CLOSED_WRITE_COMMIT = "b3fe1449560a359c87963d113c022ae3b8f86f73"
CLOSED_RECEIPT_MARKERS = (
    "id: claudelocal-titan-move-go-20260825-01",
    "state INTEGRATED, wrote=true, reread=true",
    "31/31 organs journaled, 31/31 reread true, 31/31 past_eof",
    "titan.gguf after: 103812669582 bytes (+9319291",
)
INCIDENT_SOURCE = "Slack 1787638151.184599"
INCIDENT_SPAN_SHA256 = (
    "3754028086cd42e00131bea88f0e7fcf6dba2f84ad31cb70b88e655bbdd84e8c"
)
INCIDENT_LIVE_SIZE = 103831308164


def _incident_measurement_matches(existing, structural):
    """Require the non-Claude live-byte calibration before preservation."""
    incident = (existing or {}).get("duplicate_append_incident") or {}
    base = int((structural or {}).get("claimed_append_base") or -1)
    end = int((structural or {}).get("claimed_append_end") or -1)
    span_bytes = end - base
    digest = hashlib.sha256()
    measured_bytes = 0
    for row in (structural or {}).get("organs") or []:
        path = os.path.join(EXCERPT_DIR, str(row.get("container") or ""))
        if not os.path.isfile(path):
            return False
        with open(path, "rb") as handle:
            raw = handle.read()
        digest.update(raw)
        measured_bytes += len(raw)
    expected_ranges = [
        [base + index * span_bytes, base + (index + 1) * span_bytes]
        for index in range(3)
    ]
    return bool(
        str(incident.get("state") or "").upper()
        == "PAUSED_DUPLICATE_APPENDS"
        and incident.get("source") == INCIDENT_SOURCE
        and incident.get("measured_by") == "DEMON / OpenAI Codex GPT-5.6 Sol"
        and int(incident.get("artifact_size") or 0) == INCIDENT_LIVE_SIZE
        and int(incident.get("span_bytes") or 0)
        == span_bytes == measured_bytes == 9319291
        and int(incident.get("span_count") or 0) == 3
        and int(incident.get("duplicate_span_count") or 0) == 2
        and incident.get("span_ranges") == expected_ranges
        and str(incident.get("span_sha256") or "").lower()
        == digest.hexdigest() == INCIDENT_SPAN_SHA256
        and incident.get("canonical_span") == "UNRESOLVED"
        and incident.get("mutation") == "PAUSED"
        and incident.get("repair_apply") is False
    )


def _structural_signature(packet):
    return [
        (
            str(row.get("name") or ""),
            str(row.get("container") or ""),
            str(row.get("path") or ""),
            int(row.get("len") or 0),
            str(row.get("sha256") or ""),
        )
        for row in (packet or {}).get("organs") or []
    ]


def _canonical_membership(packet, excerpt_dir=None):
    """Validate the closed MOVE's content-derived source identity."""
    excerpt_dir = EXCERPT_DIR if excerpt_dir is None else excerpt_dir
    rows = list((packet or {}).get("organs") or [])
    try:
        count = int((packet or {}).get("count") or 0)
    except (TypeError, ValueError):
        return False, "invalid organ count"
    inventory = {
        entry
        for entry in os.listdir(excerpt_dir)
        if entry.endswith(".mno")
        and os.path.isfile(os.path.join(excerpt_dir, entry))
    }
    if not (
        count == len(rows) == CANONICAL_ORGAN_COUNT
        and len(inventory) == CANONICAL_ORGAN_COUNT
    ):
        return False, "canonical 31-row/.mno inventory mismatch"
    names = set()
    containers = set()
    paths = set()
    for row in rows:
        name = str(row.get("name") or "")
        declared_container = str(row.get("container") or "")
        container = os.path.basename(declared_container)
        path = str(row.get("path") or "")
        expected_path = EXCERPT_REL + "/" + container
        if (
            not name
            or name in names
            or not container
            or container in containers
            or declared_container != container
            or container != name + ".mno"
            or path in paths
            or path != expected_path
        ):
            return False, "invalid/duplicate organ name, container, or path"
        names.add(name)
        containers.add(container)
        paths.add(path)
    if containers != inventory:
        return False, "packet containers do not equal canonical .mno inventory"
    return True, "canonical 31-entry source membership"


def complete_written_matches(existing, structural):
    """Validate a landed packet before preserving it over regeneration."""
    existing = existing or {}
    count = int(existing.get("count") or 0)
    organs = list(existing.get("organs") or [])
    before = int(existing.get("titan_size_before") or 0)
    after = int(existing.get("titan_size_after") or 0)
    written_bytes = int(existing.get("written_bytes") or 0)
    commit = str(existing.get("integrated_commit") or "").lower()
    receipt = str(existing.get("write_receipt") or "")
    receipt_path = os.path.join(REPO_ROOT, CLOSED_WRITE_RECEIPT)
    receipt_body = ""
    if receipt == CLOSED_WRITE_RECEIPT and os.path.isfile(receipt_path):
        with open(receipt_path, encoding="utf-8") as handle:
            receipt_body = handle.read()
    receipt_ok = receipt == CLOSED_WRITE_RECEIPT and all(
        marker in receipt_body for marker in CLOSED_RECEIPT_MARKERS
    )
    base = int(existing.get("claimed_append_base") or -1)
    end = int(existing.get("claimed_append_end") or -1)
    structural_base = int(structural.get("claimed_append_base") or -1)
    structural_end = int(structural.get("claimed_append_end") or -1)
    declared_bytes = sum(int(row.get("len") or 0) for row in organs)
    structural_membership_ok, structural_membership_note = _canonical_membership(
        structural
    )
    if not structural_membership_ok:
        return False, "structural packet: %s" % structural_membership_note
    existing_membership_ok, existing_membership_note = _canonical_membership(existing)
    if not existing_membership_ok:
        return False, "landed packet: %s" % existing_membership_note
    if _structural_signature(existing) != _structural_signature(structural):
        return False, "excerpt structure/hash differs from landed packet"
    if not (
        str(existing.get("titan") or "").upper() == "WRITTEN"
        and str(existing.get("state") or "").upper() == "INTEGRATED"
        and existing.get("wrote") is True
        and existing.get("reread") is True
        and count == len(organs) == int(structural.get("count") or 0)
        and int(existing.get("write_count") or 0) == count
        and int(existing.get("reread_count") or 0) == count
        and int(existing.get("past_eof_count") or 0) == count
        and base == structural_base
        and end == structural_end
        and before == base
        and after == end
        and int(existing.get("live_size_before") or 0) == before
        and int(existing.get("live_size_after") or 0) == after
        and written_bytes == end - base == declared_bytes
        and written_bytes > 0
        and receipt_ok
        and commit == CLOSED_WRITE_COMMIT
        and _incident_measurement_matches(existing, structural)
    ):
        return False, "incomplete receipt or non-Claude incident calibration"
    expected = base
    names = set()
    for row in organs:
        name = str(row.get("name") or "")
        offset = int(row.get("offset") or -1)
        length = int(row.get("len") or 0)
        if (
            not name
            or name in names
            or offset != expected
            or length <= 0
            or str(row.get("titan") or "").upper() != "WRITTEN"
        ):
            return False, "invalid landed organ geometry/state"
        names.add(name)
        expected += length
    if expected != end:
        return False, "landed claimed_append_end mismatch"
    return True, "WRITTEN packet matches sources and non-Claude incident calibration"


def build_packet():
    rows = []
    for name in sorted(os.listdir(EXCERPT_DIR)):
        if not name.endswith("_circuits.json"):
            continue
        path = os.path.join(EXCERPT_DIR, name)
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        for key, row in data.items():
            container = row.get("container")
            excerpt = os.path.join(EXCERPT_DIR, container)
            if not os.path.isfile(excerpt):
                raise RuntimeError("sidecar %s names missing %s" % (name, container))
            with open(excerpt, "rb") as raw_handle:
                raw = raw_handle.read()
            digest = hashlib.sha256(raw).hexdigest()
            expected = row.get("sha256")
            if expected and expected != digest:
                raise RuntimeError("sha mismatch %s" % excerpt)
            rows.append({
                "name": row.get("name") or key,
                "magic": row.get("magic"),
                "container": container,
                "path": "excerpts/20260823/" + container,
                "n_gate": row.get("n_gate"),
                "n_wires": row.get("n_wires"),
                "n_in": row.get("n_in"),
                "n_out": row.get("n_out"),
                "depth": row.get("depth"),
                "len": len(raw),
                "sha256": digest,
                "titan": "NOT_WRITTEN",
            })
    rows.sort(key=lambda row: row["name"])
    allocated, end = allocate_rows(rows, base=CLAIMED_APPEND_BASE)
    packet = {
        "kind": "TITAN_MOVE_PACKET",
        "computer": "titan.gguf is the computer. This packet is not.",
        "titan": "NOT_WRITTEN",
        "rule": (
            "claimed append offsets dest FROM FILE titan_size="
            "%d. Apply reallocates if live size differs."
            % CLAIMED_APPEND_BASE
        ),
        "journal": "every pre-image. new = old | mask. ones only rise.",
        "claimed_append_base": CLAIMED_APPEND_BASE,
        "claimed_append_end": end,
        "claimed_append_source": CLAIMED_APPEND_SOURCE,
        "count": len(allocated),
        "organs": allocated,
    }
    membership_ok, membership_note = _canonical_membership(packet)
    if not membership_ok:
        raise RuntimeError("canonical source membership: %s" % membership_note)
    return packet


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry" in argv
    packet = build_packet()
    print("TITAN_MOVE_PACKET structural receipt")
    print(
        "  structural_candidate count=%d titan=NOT_WRITTEN base=%s end=%s"
        % (packet["count"], packet["claimed_append_base"], packet["claimed_append_end"])
    )
    for row in packet["organs"]:
        print(
            "  %s %s g off=%s sha256=%s"
            % (row["name"], row["n_gate"], row["offset"], row["sha256"][:12])
        )
    if dry:
        print("  --dry: no files written")
        return 0
    os.makedirs(os.path.dirname(PACKET_PATH), exist_ok=True)
    if os.path.isfile(PACKET_PATH):
        with open(PACKET_PATH, encoding="utf-8") as handle:
            existing = json.load(handle)
        existing_state = str(existing.get("state") or "").upper()
        existing_titan = str(existing.get("titan") or "").upper()
        if existing_state == "APPLYING":
            print("  REFUSE: canonical packet is APPLYING; resume host/titan_move_apply.py --go at its fixed offsets")
            return 2
        if existing_titan == "WRITTEN":
            ok, note = complete_written_matches(existing, packet)
            if not ok:
                print("  REFUSE: WRITTEN packet is inconsistent: %s" % note)
                return 2
            print("  preserved canonical WRITTEN packet: %s" % note)
            return 0
        row_execution_evidence = any(
            str(row.get("titan") or "").upper() == "WRITTEN"
            or row.get("reread") is True
            or row.get("past_eof") is True
            or bool(row.get("written_sha256"))
            for row in (existing.get("organs") or [])
        )
        top_execution_evidence = (
            existing_state in {"APPLYING", "WRITTEN", "INTEGRATED"}
            or existing.get("wrote") is True
            or existing.get("reread") is True
            or bool(existing.get("write_receipt"))
            or bool(existing.get("integrated_commit"))
            or any(
                int(existing.get(key) or 0) > 0
                for key in (
                    "reread_count",
                    "past_eof_count",
                    "write_count",
                    "titan_size_before",
                    "titan_size_after",
                    "live_size_before",
                    "live_size_after",
                    "written_bytes",
                )
            )
        )
        if top_execution_evidence or row_execution_evidence:
            print("  REFUSE: canonical packet has execution evidence but lost/inconsistent titan marker")
            return 2
    with open(PACKET_PATH, "w", encoding="utf-8") as handle:
        json.dump(packet, handle, indent=2)
        handle.write("\n")
    print("  wrote %s" % PACKET_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

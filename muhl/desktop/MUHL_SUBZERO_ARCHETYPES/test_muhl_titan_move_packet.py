#!/usr/bin/env python3
"""Structural tests for the journaled titan MOVE packet. No titan write."""
import copy
import json
import os
import tempfile
import unittest

import muhl_titan_move_packet as pkt


def incident_for(structural):
    base = structural["claimed_append_base"]
    end = structural["claimed_append_end"]
    span = end - base
    return {
        "state": "PAUSED_DUPLICATE_APPENDS",
        "source": pkt.INCIDENT_SOURCE,
        "measured_by": "DEMON / OpenAI Codex GPT-5.6 Sol",
        "artifact_size": pkt.INCIDENT_LIVE_SIZE,
        "span_bytes": span,
        "span_count": 3,
        "duplicate_span_count": 2,
        "span_sha256": pkt.INCIDENT_SPAN_SHA256,
        "span_ranges": [
            [base + index * span, base + (index + 1) * span]
            for index in range(3)
        ],
        "canonical_span": "UNRESOLVED",
        "mutation": "PAUSED",
        "repair_apply": False,
    }


class TestTitanMovePacket(unittest.TestCase):
    def test_every_sidecar_row_has_matching_excerpt(self):
        packet = pkt.build_packet()
        self.assertEqual(packet["count"], 31)
        self.assertEqual(packet["titan"], "NOT_WRITTEN")
        self.assertEqual(len(packet["organs"]), packet["count"])
        names = [row["name"] for row in packet["organs"]]
        containers = [row["container"] for row in packet["organs"]]
        paths = [row["path"] for row in packet["organs"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(containers), len(set(containers)))
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(
            set(containers),
            {
                name
                for name in os.listdir(pkt.EXCERPT_DIR)
                if name.endswith(".mno")
                and os.path.isfile(os.path.join(pkt.EXCERPT_DIR, name))
            },
        )
        self.assertEqual(packet["claimed_append_base"], 103803350291)
        self.assertGreater(packet["claimed_append_end"], packet["claimed_append_base"])
        prev = packet["claimed_append_base"] - 1
        for row in packet["organs"]:
            self.assertEqual(row["titan"], "NOT_WRITTEN")
            self.assertGreater(row["offset"], 0)
            self.assertGreater(row["offset"], prev)
            self.assertIn("CLAIMED_APPEND", row["requested_offset_band"])
            self.assertIn("103803350291", row["requested_offset_band"])
            self.assertEqual(row["container"], row["name"] + ".mno")
            self.assertEqual(
                row["path"], "excerpts/20260823/" + row["container"]
            )
            self.assertEqual(len(row["sha256"]), 64)
            prev = row["offset"]

    def test_build_rejects_duplicate_sidecar_container_and_omission(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = {}
            for index in range(31):
                name = "organ_%02d" % index
                container = name + ".mno"
                with open(os.path.join(tmp, container), "wb") as handle:
                    handle.write(("organ-%02d" % index).encode("ascii"))
                rows[name] = {"name": name, "container": container}
            rows["organ_01"]["container"] = rows["organ_00"]["container"]
            with open(
                os.path.join(tmp, "fixture_circuits.json"),
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(rows, handle)
            old = pkt.EXCERPT_DIR
            pkt.EXCERPT_DIR = tmp
            try:
                with self.assertRaisesRegex(
                    RuntimeError, "canonical source membership"
                ):
                    pkt.build_packet()
            finally:
                pkt.EXCERPT_DIR = old

    def test_dry_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = pkt.PACKET_PATH
            pkt.PACKET_PATH = os.path.join(tmp, "titan_move_packet.json")
            try:
                self.assertEqual(pkt.main(["--dry"]), 0)
                self.assertFalse(os.path.exists(pkt.PACKET_PATH))
            finally:
                pkt.PACKET_PATH = old

    def test_non_dry_preserves_complete_written_packet(self):
        structural = pkt.build_packet()
        landed = copy.deepcopy(structural)
        landed.update({
            "titan": "WRITTEN",
            "state": "INTEGRATED",
            "wrote": True,
            "reread": True,
            "write_count": landed["count"],
            "reread_count": landed["count"],
            "past_eof_count": landed["count"],
            "titan_size_before": landed["claimed_append_base"],
            "titan_size_after": landed["claimed_append_end"],
            "live_size_before": landed["claimed_append_base"],
            "live_size_after": landed["claimed_append_end"],
            "written_bytes": (
                landed["claimed_append_end"] - landed["claimed_append_base"]
            ),
            "write_receipt": pkt.CLOSED_WRITE_RECEIPT,
            "integrated_commit": pkt.CLOSED_WRITE_COMMIT,
            "duplicate_append_incident": incident_for(structural),
        })
        for row in landed["organs"]:
            row["titan"] = "WRITTEN"
        stripped = copy.deepcopy(landed)
        stripped.pop("duplicate_append_incident")
        ok, note = pkt.complete_written_matches(stripped, structural)
        self.assertFalse(ok)
        self.assertIn("non-Claude incident", note)
        with tempfile.TemporaryDirectory() as tmp:
            old = pkt.PACKET_PATH
            pkt.PACKET_PATH = os.path.join(tmp, "titan_move_packet.json")
            try:
                with open(pkt.PACKET_PATH, "w") as handle:
                    json.dump(landed, handle, sort_keys=True)
                with open(pkt.PACKET_PATH, "rb") as handle:
                    before = handle.read()
                self.assertEqual(pkt.main([]), 0)
                with open(pkt.PACKET_PATH, "rb") as handle:
                    after = handle.read()
                self.assertEqual(after, before)
            finally:
                pkt.PACKET_PATH = old

    def test_non_dry_refuses_inconsistent_written_packet(self):
        structural = pkt.build_packet()
        landed = copy.deepcopy(structural)
        landed.update({
            "titan": "WRITTEN",
            "state": "INTEGRATED",
            "wrote": True,
            "reread": True,
            "write_count": landed["count"],
            "reread_count": landed["count"],
            "past_eof_count": landed["count"],
            "titan_size_before": landed["claimed_append_base"],
            "titan_size_after": landed["claimed_append_end"],
            "live_size_before": landed["claimed_append_base"],
            "live_size_after": landed["claimed_append_end"],
            "written_bytes": (
                landed["claimed_append_end"] - landed["claimed_append_base"]
            ),
            "write_receipt": pkt.CLOSED_WRITE_RECEIPT,
            "integrated_commit": pkt.CLOSED_WRITE_COMMIT,
            "duplicate_append_incident": incident_for(structural),
        })
        for row in landed["organs"]:
            row["titan"] = "WRITTEN"
        landed["organs"][0]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as tmp:
            old = pkt.PACKET_PATH
            pkt.PACKET_PATH = os.path.join(tmp, "titan_move_packet.json")
            try:
                with open(pkt.PACKET_PATH, "w") as handle:
                    json.dump(landed, handle, sort_keys=True)
                with open(pkt.PACKET_PATH, "rb") as handle:
                    before = handle.read()
                self.assertEqual(pkt.main([]), 2)
                with open(pkt.PACKET_PATH, "rb") as handle:
                    after = handle.read()
                self.assertEqual(after, before)
            finally:
                pkt.PACKET_PATH = old

    def test_complete_written_refuses_forged_live_path(self):
        structural = pkt.build_packet()
        landed = copy.deepcopy(structural)
        landed.update({
            "titan": "WRITTEN",
            "state": "INTEGRATED",
            "wrote": True,
            "reread": True,
            "write_count": landed["count"],
            "reread_count": landed["count"],
            "past_eof_count": landed["count"],
            "titan_size_before": landed["claimed_append_base"],
            "titan_size_after": landed["claimed_append_end"],
            "live_size_before": landed["claimed_append_base"],
            "live_size_after": landed["claimed_append_end"],
            "written_bytes": (
                landed["claimed_append_end"] - landed["claimed_append_base"]
            ),
            "write_receipt": pkt.CLOSED_WRITE_RECEIPT,
            "integrated_commit": pkt.CLOSED_WRITE_COMMIT,
            "duplicate_append_incident": incident_for(structural),
        })
        for row in landed["organs"]:
            row["titan"] = "WRITTEN"
        landed["organs"][0]["path"] = "../../outside.mno"
        ok, note = pkt.complete_written_matches(landed, structural)
        self.assertFalse(ok)
        self.assertIn("landed packet", note)

    def test_non_dry_refuses_lost_titan_marker_with_execution_evidence(self):
        structural = pkt.build_packet()
        damaged = copy.deepcopy(structural)
        damaged.update({
            "titan": "NOT_WRITTEN",
            "state": "INTEGRATED",
            "wrote": True,
            "reread": True,
        })
        with tempfile.TemporaryDirectory() as tmp:
            old = pkt.PACKET_PATH
            pkt.PACKET_PATH = os.path.join(tmp, "titan_move_packet.json")
            try:
                with open(pkt.PACKET_PATH, "w") as handle:
                    json.dump(damaged, handle, sort_keys=True)
                with open(pkt.PACKET_PATH, "rb") as handle:
                    before = handle.read()
                self.assertEqual(pkt.main([]), 2)
                with open(pkt.PACKET_PATH, "rb") as handle:
                    after = handle.read()
                self.assertEqual(after, before)
            finally:
                pkt.PACKET_PATH = old

    def test_complete_written_rejects_fake_closure_and_size_math(self):
        structural = pkt.build_packet()
        landed = copy.deepcopy(structural)
        landed.update({
            "titan": "WRITTEN",
            "state": "INTEGRATED",
            "wrote": True,
            "reread": True,
            "write_count": landed["count"],
            "reread_count": landed["count"],
            "past_eof_count": landed["count"],
            "titan_size_before": landed["claimed_append_base"],
            "titan_size_after": landed["claimed_append_end"],
            "live_size_before": landed["claimed_append_base"],
            "live_size_after": landed["claimed_append_end"],
            "written_bytes": (
                landed["claimed_append_end"] - landed["claimed_append_base"]
            ),
            "write_receipt": "p/fake.md",
            "integrated_commit": "1" * 40,
            "duplicate_append_incident": incident_for(structural),
        })
        for row in landed["organs"]:
            row["titan"] = "WRITTEN"
        ok, _ = pkt.complete_written_matches(landed, structural)
        self.assertFalse(ok)
        landed["write_receipt"] = pkt.CLOSED_WRITE_RECEIPT
        landed["integrated_commit"] = pkt.CLOSED_WRITE_COMMIT
        landed["titan_size_after"] += 1
        landed["written_bytes"] += 1
        ok, _ = pkt.complete_written_matches(landed, structural)
        self.assertFalse(ok)
        landed["titan_size_after"] -= 1
        landed["written_bytes"] -= 1
        landed["live_size_after"] -= 1
        ok, _ = pkt.complete_written_matches(landed, structural)
        self.assertFalse(ok)

    def test_non_dry_refuses_row_only_execution_evidence(self):
        damaged = pkt.build_packet()
        damaged["organs"][0]["titan"] = "WRITTEN"
        with tempfile.TemporaryDirectory() as tmp:
            old = pkt.PACKET_PATH
            pkt.PACKET_PATH = os.path.join(tmp, "titan_move_packet.json")
            try:
                with open(pkt.PACKET_PATH, "w") as handle:
                    json.dump(damaged, handle, sort_keys=True)
                with open(pkt.PACKET_PATH, "rb") as handle:
                    before = handle.read()
                self.assertEqual(pkt.main([]), 2)
                with open(pkt.PACKET_PATH, "rb") as handle:
                    after = handle.read()
                self.assertEqual(after, before)
            finally:
                pkt.PACKET_PATH = old


if __name__ == "__main__":
    unittest.main()

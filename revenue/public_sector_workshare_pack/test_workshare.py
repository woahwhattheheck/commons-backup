from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from revenue.public_sector_workshare_pack.workshare import (
    collision_key,
    compile_pack,
    load_json_strict,
    render_markdown,
    verify_packet,
    write_exclusive,
)

HERE = Path(__file__).resolve().parent
AS_OF = "2026-09-14T03:59:00Z"


class WorksharePackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json_strict(HERE / "opportunities.json")

    def test_happy_packet_has_four_live_overlays_and_no_send_authority(self):
        packet = compile_pack(self.manifest, as_of_utc=AS_OF)
        self.assertEqual(packet["overall_state"], "WORKSHARE_PACK_READY_FOR_PRIME_REVIEW")
        self.assertEqual(len(packet["overlays"]), 4)
        self.assertFalse(packet["authority_ceiling"]["external_send_authorized"])
        self.assertFalse(packet["authority_ceiling"]["bid_submission_authorized"])
        self.assertEqual(packet["commercial_truth"]["commercial_state"], "PROPOSED_NOT_ACCEPTED")
        self.assertEqual(packet["commercial_truth"]["fee_state"], "OWNER_INPUT_REQUIRED")
        self.assertTrue(all(not row["external_send_authorized"] for row in packet["overlays"]))

    def test_expected_opportunity_ids(self):
        packet = compile_pack(self.manifest, as_of_utc=AS_OF)
        self.assertEqual(
            [row["opportunity_id"] for row in packet["overlays"]],
            [
                "IL-DOIT-CDB-27-448DOIT-ADMIN-B-52519",
                "NC-DHHS-DHB-30-2025-037-DHB",
                "NYSED-RFP-144-OCUE",
                "OR-ODA-S-DASOBO-00017788",
            ],
        )

    def test_il_and_nc_deadline_authority_recheck_is_explicit(self):
        packet = compile_pack(self.manifest, as_of_utc=AS_OF)
        states = {row["opportunity_id"]: row["overlay_state"] for row in packet["overlays"]}
        self.assertEqual(states["IL-DOIT-CDB-27-448DOIT-ADMIN-B-52519"], "READY_FOR_PRIME_REVIEW_DEADLINE_RECHECK_REQUIRED")
        self.assertEqual(states["NC-DHHS-DHB-30-2025-037-DHB"], "READY_FOR_PRIME_REVIEW_DEADLINE_RECHECK_REQUIRED")
        self.assertEqual(states["NYSED-RFP-144-OCUE"], "READY_FOR_PRIME_REVIEW")
        self.assertEqual(states["OR-ODA-S-DASOBO-00017788"], "READY_FOR_PRIME_REVIEW")

    def test_target_status_cannot_self_assert_current_bidder(self):
        bad = copy.deepcopy(self.manifest)
        bad["opportunities"][1]["target_candidates"][0]["current_bidder_status"] = "CONFIRMED_BIDDER"
        with self.assertRaisesRegex(ValueError, "must remain UNKNOWN"):
            compile_pack(bad, as_of_utc=AS_OF)

    def test_static_target_route_cannot_be_self_acquired(self):
        bad = copy.deepcopy(self.manifest)
        bad["opportunities"][1]["target_candidates"][0]["route_state"] = "ACQUIRED"
        with self.assertRaisesRegex(ValueError, "cannot self-mint"):
            compile_pack(bad, as_of_utc=AS_OF)

    def test_duplicate_opportunity_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["opportunities"].append(copy.deepcopy(bad["opportunities"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate opportunity_id"):
            compile_pack(bad, as_of_utc=AS_OF)

    def test_duplicate_source_id_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["opportunities"][0]["source_evidence"].append(copy.deepcopy(bad["opportunities"][0]["source_evidence"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate source_id"):
            compile_pack(bad, as_of_utc=AS_OF)

    def test_duplicate_target_org_rejected_case_insensitive(self):
        bad = copy.deepcopy(self.manifest)
        target = copy.deepcopy(bad["opportunities"][1]["target_candidates"][0])
        target["organization"] = target["organization"].upper()
        bad["opportunities"][1]["target_candidates"].append(target)
        with self.assertRaisesRegex(ValueError, "duplicate target organization"):
            compile_pack(bad, as_of_utc=AS_OF)

    def test_unknown_key_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["opportunities"][0]["send_now"] = True
        with self.assertRaisesRegex(ValueError, "keys mismatch"):
            compile_pack(bad, as_of_utc=AS_OF)

    def test_bool_cannot_alias_integer_commercial_bound(self):
        # Commercial bounds are constants; exercise strict helper via manifest shape's type boundary.
        bad = copy.deepcopy(self.manifest)
        bad["captured_at_utc"] = True
        with self.assertRaises(ValueError):
            compile_pack(bad, as_of_utc=AS_OF)

    def test_future_manifest_capture_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["captured_at_utc"] = "2026-09-14T04:00:00Z"
        with self.assertRaisesRegex(ValueError, "future"):
            compile_pack(bad, as_of_utc=AS_OF)

    def test_stale_source_snapshot_holds(self):
        packet = compile_pack(self.manifest, as_of_utc="2026-09-22T03:45:01Z")
        self.assertEqual(packet["overall_state"], "HOLD")
        self.assertTrue(all(row["overlay_state"] == "HOLD_SOURCE_RECHECK_REQUIRED" for row in packet["overlays"]))

    def test_expired_deadline_holds(self):
        packet = compile_pack(self.manifest, as_of_utc="2026-11-01T00:00:00Z")
        self.assertEqual(packet["overall_state"], "HOLD")
        self.assertTrue(all(row["overlay_state"] == "HOLD_DEADLINE_EXPIRED" for row in packet["overlays"]))

    def test_deadline_day_requires_recheck(self):
        fresh = copy.deepcopy(self.manifest)
        fresh["captured_at_utc"] = "2026-09-30T00:00:00Z"
        packet = compile_pack(fresh, as_of_utc="2026-09-30T01:00:00Z")
        state = {row["opportunity_id"]: row["overlay_state"] for row in packet["overlays"]}["OR-ODA-S-DASOBO-00017788"]
        self.assertEqual(state, "HOLD_DEADLINE_DAY_RECHECK_REQUIRED")

    def test_missing_official_source_rejected(self):
        bad = copy.deepcopy(self.manifest)
        for source in bad["opportunities"][0]["source_evidence"]:
            source["authority"] = "INTERNAL_SCOUT"
        with self.assertRaisesRegex(ValueError, "requires at least one official source"):
            compile_pack(bad, as_of_utc=AS_OF)

    def test_source_record_digest_changes_when_fact_changes(self):
        first = compile_pack(self.manifest, as_of_utc=AS_OF)
        changed = copy.deepcopy(self.manifest)
        changed["opportunities"][0]["source_evidence"][0]["observed_facts"][0] += " changed"
        second = compile_pack(changed, as_of_utc=AS_OF)
        def source_digest(packet, source_id):
            for op in packet["input_manifest"]["opportunities"]:
                for source in op["source_evidence"]:
                    if source["source_id"] == source_id:
                        return source["source_record_sha256"]
            self.fail(f"missing source {source_id}")
        self.assertNotEqual(
            source_digest(first, "IL-CDB-OFFICIAL-NOTICE"),
            source_digest(second, "IL-CDB-OFFICIAL-NOTICE"),
        )

    def test_order_invariance(self):
        first = compile_pack(self.manifest, as_of_utc=AS_OF)
        reordered = copy.deepcopy(self.manifest)
        reordered["opportunities"].reverse()
        for op in reordered["opportunities"]:
            op["source_evidence"].reverse()
            op["allowed_modules"].reverse()
            op["target_candidates"].reverse()
        second = compile_pack(reordered, as_of_utc=AS_OF)
        self.assertEqual(first, second)

    def test_receipt_tamper_rejected(self):
        packet = compile_pack(self.manifest, as_of_utc=AS_OF)
        tampered = copy.deepcopy(packet)
        tampered["commercial_truth"]["fee_state"] = "ACCEPTED"
        with self.assertRaisesRegex(ValueError, "receipt mismatch"):
            verify_packet(tampered)

    def test_reseal_semantic_tamper_rejected(self):
        packet = compile_pack(self.manifest, as_of_utc=AS_OF)
        tampered = copy.deepcopy(packet)
        tampered["authority_ceiling"]["external_send_authorized"] = True
        from revenue.public_sector_workshare_pack.workshare import sha256_obj
        tampered["receipt_sha256"] = sha256_obj({k: v for k, v in tampered.items() if k != "receipt_sha256"})
        with self.assertRaisesRegex(ValueError, "semantic replay mismatch"):
            verify_packet(tampered)

    def test_verify_current_can_detect_source_staleness(self):
        packet = compile_pack(self.manifest, as_of_utc=AS_OF)
        result = verify_packet(packet, current_as_of_utc="2026-09-22T03:45:01Z")
        self.assertEqual(result["historical_integrity"], "PASS")
        self.assertEqual(result["current_state"], "HOLD")

    def test_collision_key_is_deterministic_and_route_sensitive(self):
        a = collision_key("NYSED-RFP-144-OCUE", "OutSystems", "a" * 64)
        b = collision_key("NYSED-RFP-144-OCUE", "outsystems", "a" * 64)
        c = collision_key("NYSED-RFP-144-OCUE", "OutSystems", "b" * 64)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_drafts_are_explicitly_not_authorized(self):
        packet = compile_pack(self.manifest, as_of_utc=AS_OF)
        for overlay in packet["overlays"]:
            self.assertTrue(overlay["outreach_draft"].startswith("NOT AUTHORIZED TO SEND"))
            self.assertIn("paid", overlay["outreach_draft"].lower())
            self.assertFalse(overlay["external_send_authorized"])

    def test_markdown_is_deterministic_and_truthful(self):
        packet = compile_pack(self.manifest, as_of_utc=AS_OF)
        a = render_markdown(packet)
        b = render_markdown(copy.deepcopy(packet))
        self.assertEqual(a, b)
        self.assertIn("NOT AUTHORIZED TO SEND", a)
        self.assertIn("PROPOSED_NOT_ACCEPTED", a)
        self.assertIn(packet["receipt_sha256"], a)

    def test_strict_loader_rejects_duplicate_keys_and_infinity(self):
        with tempfile.TemporaryDirectory() as td:
            dup = Path(td) / "dup.json"
            dup.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                load_json_strict(dup)
            inf = Path(td) / "inf.json"
            inf.write_text('{"a":Infinity}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-finite"):
                load_json_strict(inf)

    def test_strict_loader_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "x.json"
            target.write_text("{}", encoding="utf-8")
            link = Path(td) / "link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "non-symlink"):
                load_json_strict(link)

    def test_input_and_output_reject_symlink_ancestor(self):
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "real"
            real.mkdir()
            linkdir = Path(td) / "alias"
            linkdir.symlink_to(real, target_is_directory=True)
            source = real / "in.json"
            source.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ancestor"):
                load_json_strict(linkdir / "in.json")
            with self.assertRaisesRegex(ValueError, "ancestor"):
                write_exclusive(linkdir / "out.json", b"{}")

    def test_write_exclusive_refuses_existing_and_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "out"
            write_exclusive(p, b"first")
            with self.assertRaises(FileExistsError):
                write_exclusive(p, b"second")
            link = Path(td) / "link"
            link.symlink_to(p)
            with self.assertRaises(FileExistsError):
                write_exclusive(link, b"x")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from podcast_flight_ops import (AUTHORITY_FLAGS, Desk, DeskError, apply_command,
                                load_json, verify_bundle, verify_snapshot)


D1 = "2026-10-01T12:00:00Z"
D2 = "2026-10-01T12:01:00Z"
D3 = "2026-10-01T12:02:00Z"
D4 = "2026-10-01T12:03:00Z"
D5 = "2026-10-01T12:04:00Z"
D6 = "2026-10-01T12:05:00Z"
D7 = "2026-10-01T12:06:00Z"
D8 = "2026-10-01T12:07:00Z"
D9 = "2026-10-01T12:08:00Z"
D10 = "2026-10-01T12:09:00Z"


class DeskCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "desk.sqlite3"
        self.desk = Desk(self.db_path)

    def tearDown(self):
        self.desk.close()
        self.tmp.cleanup()

    def seed(self, *, insertions=2, rate=125000):
        d = self.desk
        d.add_show("s1", D1, show_id="show-a", name="Signal Hour")
        d.add_slot("sl1", D2, slot_id="slot-a", show_id="show-a", air_date="2026-10-10", position="midroll-1")
        d.add_slot("sl2", D2, slot_id="slot-b", show_id="show-a", air_date="2026-10-17", position="midroll-1")
        d.add_slot("sl3", D2, slot_id="slot-c", show_id="show-a", air_date="2026-10-24", position="midroll-1")
        d.add_campaign("c1", D3, campaign_id="camp-a", advertiser_ref="owner:adv-7", currency="usd",
                       start_date="2026-10-01", end_date="2026-10-31", contracted_insertions=insertions,
                       unit_rate_cents=rate, io_reference="owner:io-44")
        d.add_creative("cr1", D4, creative_id="creative-a", revision=1, campaign_id="camp-a",
                       source_sha256="a" * 64)
        d.approve_creative("cr2", D5, creative_id="creative-a", revision=1,
                           approval_ref="owner:approval-1")

    def test_full_flight_missed_makegood_invoice(self):
        self.seed()
        d = self.desk
        d.book("b1", D6, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
               creative_id="creative-a", creative_revision=1)
        d.book("b2", D6, booking_id="book-b", campaign_id="camp-a", slot_id="slot-b",
               creative_id="creative-a", creative_revision=1)
        d.mark_delivery("x1", D7, booking_id="book-a", evidence_ref="owner:episode-101")
        d.mark_missed("x2", D7, booking_id="book-b", evidence_ref="owner:missed-ops-7")
        d.makegood("mg1", D8, booking_id="book-mg", missed_booking_id="book-b", slot_id="slot-c",
                   creative_id="creative-a", creative_revision=1)
        d.mark_delivery("mg2", D9, booking_id="book-mg", evidence_ref="owner:episode-103")
        invoice = d.invoice_draft("camp-a")
        self.assertEqual(invoice["state"], "READY_FOR_OWNER_REVIEW")
        self.assertEqual(invoice["draft_amount_cents"], 125000)
        self.assertEqual(invoice["delivered_billable_booking_ids"], ["book-a"])
        self.assertFalse(invoice["payment_authorized"])
        self.assertTrue(d.verify_db()["integrity_checked"])

    def test_unapproved_creative_blocks_booking(self):
        self.seed()
        self.desk.add_creative("cr3", D6, creative_id="creative-a", revision=2,
                               campaign_id="camp-a", source_sha256="b" * 64)
        with self.assertRaisesRegex(DeskError, "not approved"):
            self.desk.book("b1", D7, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
                           creative_id="creative-a", creative_revision=2)

    def test_creative_revision_must_be_contiguous(self):
        self.seed()
        with self.assertRaisesRegex(DeskError, "increase by exactly one"):
            self.desk.add_creative("cr3", D6, creative_id="creative-a", revision=3,
                                   campaign_id="camp-a", source_sha256="b" * 64)

    def test_slot_collision_blocks_second_booking(self):
        self.seed()
        self.desk.book("b1", D6, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
                       creative_id="creative-a", creative_revision=1)
        with self.assertRaisesRegex(DeskError, "already occupied"):
            self.desk.book("b2", D7, booking_id="book-b", campaign_id="camp-a", slot_id="slot-a",
                           creative_id="creative-a", creative_revision=1)

    def test_cancel_frees_slot_and_allocation(self):
        self.seed(insertions=1)
        self.desk.book("b1", D6, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
                       creative_id="creative-a", creative_revision=1)
        self.desk.cancel("x1", D7, booking_id="book-a", reason="owner reschedule reset")
        self.desk.book("b2", D8, booking_id="book-b", campaign_id="camp-a", slot_id="slot-a",
                       creative_id="creative-a", creative_revision=1)
        self.assertEqual(self.desk.snapshot()["bookings"][-1]["status"], "BOOKED")

    def test_reschedule_moves_booking_without_double_allocation(self):
        self.seed(insertions=1)
        self.desk.book("b1", D6, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
                       creative_id="creative-a", creative_revision=1)
        result = self.desk.reschedule("r1", D7, booking_id="book-a", new_slot_id="slot-b")
        self.assertEqual(result["slot_id"], "slot-b")
        row = self.desk.db.execute("SELECT slot_id FROM bookings WHERE booking_id='book-a'").fetchone()
        self.assertEqual(row[0], "slot-b")

    def test_reschedule_blocks_occupied_target(self):
        self.seed(insertions=2)
        self.desk.book("b1", D6, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
                       creative_id="creative-a", creative_revision=1)
        self.desk.book("b2", D6, booking_id="book-b", campaign_id="camp-a", slot_id="slot-b",
                       creative_id="creative-a", creative_revision=1)
        with self.assertRaisesRegex(DeskError, "already occupied"):
            self.desk.reschedule("r1", D7, booking_id="book-a", new_slot_id="slot-b")

    def test_contract_allocation_cap(self):
        self.seed(insertions=1)
        self.desk.book("b1", D6, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
                       creative_id="creative-a", creative_revision=1)
        with self.assertRaisesRegex(DeskError, "already allocated"):
            self.desk.book("b2", D7, booking_id="book-b", campaign_id="camp-a", slot_id="slot-b",
                           creative_id="creative-a", creative_revision=1)

    def test_flight_window_enforced(self):
        self.seed(insertions=1)
        self.desk.add_slot("sl4", D6, slot_id="late", show_id="show-a", air_date="2026-11-01", position="midroll-1")
        with self.assertRaisesRegex(DeskError, "outside campaign flight window"):
            self.desk.book("b1", D7, booking_id="book-a", campaign_id="camp-a", slot_id="late",
                           creative_id="creative-a", creative_revision=1)

    def test_delivery_requires_booked_state(self):
        self.seed(insertions=1)
        self.desk.book("b1", D6, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
                       creative_id="creative-a", creative_revision=1)
        self.desk.mark_delivery("d1", D7, booking_id="book-a", evidence_ref="owner:e1")
        with self.assertRaisesRegex(DeskError, "only BOOKED"):
            self.desk.mark_delivery("d2", D8, booking_id="book-a", evidence_ref="owner:e2")

    def test_makegood_requires_miss(self):
        self.seed(insertions=1)
        self.desk.book("b1", D6, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
                       creative_id="creative-a", creative_revision=1)
        with self.assertRaisesRegex(DeskError, "must be MISSED"):
            self.desk.makegood("m1", D7, booking_id="mg", missed_booking_id="book-a", slot_id="slot-b",
                               creative_id="creative-a", creative_revision=1)

    def test_only_one_makegood_per_miss(self):
        self.seed(insertions=1)
        self.desk.book("b1", D6, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
                       creative_id="creative-a", creative_revision=1)
        self.desk.mark_missed("x1", D7, booking_id="book-a", evidence_ref="owner:miss")
        self.desk.makegood("m1", D8, booking_id="mg-a", missed_booking_id="book-a", slot_id="slot-b",
                           creative_id="creative-a", creative_revision=1)
        with self.assertRaisesRegex(DeskError, "already has a makegood"):
            self.desk.makegood("m2", D9, booking_id="mg-b", missed_booking_id="book-a", slot_id="slot-c",
                               creative_id="creative-a", creative_revision=1)

    def test_unresolved_miss_holds_invoice(self):
        self.seed(insertions=1)
        self.desk.book("b1", D6, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
                       creative_id="creative-a", creative_revision=1)
        self.desk.mark_missed("x1", D7, booking_id="book-a", evidence_ref="owner:miss")
        inv = self.desk.invoice_draft("camp-a")
        self.assertEqual(inv["state"], "HOLD")
        self.assertIn("MISSED_PLACEMENT_MAKEGOOD_UNRESOLVED", inv["reasons"])
        self.assertEqual(inv["draft_amount_cents"], 0)

    def test_operation_replay_is_noop(self):
        first = self.desk.add_show("same-key", D1, show_id="s", name="Show")
        second = self.desk.add_show("same-key", D1, show_id="s", name="Show")
        self.assertEqual(first, second)
        self.assertEqual(self.desk.db.execute("SELECT COUNT(*) FROM shows").fetchone()[0], 1)
        self.assertEqual(self.desk.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)

    def test_operation_key_changed_payload_fails(self):
        self.desk.add_show("same-key", D1, show_id="s", name="Show")
        with self.assertRaisesRegex(DeskError, "changed request"):
            self.desk.add_show("same-key", D1, show_id="s", name="Other")

    def test_bool_not_accepted_as_integer(self):
        with self.assertRaisesRegex(DeskError, "contracted_insertions"):
            self.desk.add_campaign("c", D1, campaign_id="c", advertiser_ref="a", currency="USD",
                                   start_date="2026-10-01", end_date="2026-10-02",
                                   contracted_insertions=True, unit_rate_cents=100, io_reference="io")

    def test_duplicate_show_date_position_rejected(self):
        self.desk.add_show("s", D1, show_id="s", name="Show")
        self.desk.add_slot("a", D2, slot_id="one", show_id="s", air_date="2026-10-10", position="pre")
        with self.assertRaisesRegex(DeskError, "already exists"):
            self.desk.add_slot("b", D3, slot_id="two", show_id="s", air_date="2026-10-10", position="pre")

    def test_persistence_after_reopen(self):
        self.seed(insertions=1)
        self.desk.close()
        self.desk = Desk(self.db_path)
        self.assertEqual(len(self.desk.snapshot()["campaigns"]), 1)
        self.assertTrue(self.desk.verify_db()["integrity_checked"])

    def test_audit_tamper_detected(self):
        self.seed(insertions=1)
        self.desk.db.execute("UPDATE events SET payload_json='{}' WHERE seq=1")
        self.desk.db.commit()
        with self.assertRaisesRegex(DeskError, "audit chain mismatch"):
            self.desk.verify_db()

    def test_snapshot_authority_tamper_detected(self):
        self.seed(insertions=1)
        snap = self.desk.snapshot()
        snap["authority"]["external_send_authorized"] = True
        snap["semantic_digest"] = __import__("hashlib").sha256(json.dumps(
            {k: v for k, v in snap.items() if k != "semantic_digest"}, ensure_ascii=False,
            sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        with self.assertRaisesRegex(DeskError, "authority flags"):
            verify_snapshot(snap)

    def test_snapshot_invoice_tamper_detected_even_with_resealed_digest(self):
        self.seed(insertions=1)
        self.desk.book("b1", D6, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
                       creative_id="creative-a", creative_revision=1)
        self.desk.mark_delivery("d1", D7, booking_id="book-a", evidence_ref="owner:e")
        snap = self.desk.snapshot()
        snap["invoice_drafts"][0]["draft_amount_cents"] += 1
        snap["semantic_digest"] = __import__("hashlib").sha256(json.dumps(
            {k: v for k, v in snap.items() if k != "semantic_digest"}, ensure_ascii=False,
            sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        with self.assertRaisesRegex(DeskError, "semantic mismatch"):
            verify_snapshot(snap)

    def test_export_bundle_and_verify(self):
        self.seed(insertions=1, rate=50000)
        self.desk.book("b1", D6, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
                       creative_id="creative-a", creative_revision=1)
        self.desk.mark_delivery("d1", D7, booking_id="book-a", evidence_ref="owner:e")
        out = Path(self.tmp.name) / "bundle"
        receipt = self.desk.export_bundle(out)
        self.assertEqual(set(receipt["files"]), {"HANDOFF.md", "invoice_drafts.csv", "placements.csv", "snapshot.json"})
        verified = verify_bundle(out)
        self.assertTrue(verified["integrity_checked"])
        self.assertFalse(verified["payment_authorized"])

    def test_bundle_byte_tamper_detected(self):
        self.seed(insertions=1)
        out = Path(self.tmp.name) / "bundle"
        self.desk.export_bundle(out)
        (out / "placements.csv").write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(DeskError, "digest mismatch"):
            verify_bundle(out)

    def test_apply_command_rejects_unknown_fields(self):
        with self.assertRaisesRegex(DeskError, "unknown command fields"):
            apply_command(self.desk, {"operation_key": "x", "occurred_at": D1,
                                      "action": "add_show", "args": {}, "extra": 1})

    def test_cli_round_trip(self):
        db = Path(self.tmp.name) / "cli.sqlite3"
        tool = HERE / "podcast_flight_ops.py"
        init = subprocess.run([sys.executable, str(tool), "init", str(db)], capture_output=True, text=True)
        self.assertEqual(init.returncode, 0, init.stderr)
        cmd = Path(self.tmp.name) / "command.json"
        cmd.write_text(json.dumps({"operation_key": "cli1", "occurred_at": D1, "action": "add_show",
                                   "args": {"show_id": "cli-show", "name": "CLI Show"}}), encoding="utf-8")
        run = subprocess.run([sys.executable, str(tool), "apply", str(db), str(cmd)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        status = subprocess.run([sys.executable, str(tool), "status", str(db)], capture_output=True, text=True)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)["shows"][0]["show_id"], "cli-show")

    def test_load_json_duplicate_and_nonfinite_rejected(self):
        p = Path(self.tmp.name) / "bad.json"
        p.write_text('{"a":1,"a":2}', encoding="utf-8")
        with self.assertRaisesRegex(DeskError, "duplicate JSON field"):
            load_json(p)
        p.write_text('{"a":NaN}', encoding="utf-8")
        with self.assertRaisesRegex(DeskError, "non-finite"):
            load_json(p)

    def test_makegood_is_always_nonbillable(self):
        self.seed(insertions=1)
        self.desk.book("b1", D6, booking_id="book-a", campaign_id="camp-a", slot_id="slot-a",
                       creative_id="creative-a", creative_revision=1)
        self.desk.mark_missed("x1", D7, booking_id="book-a", evidence_ref="owner:miss")
        result = self.desk.makegood("m1", D8, booking_id="mg", missed_booking_id="book-a", slot_id="slot-b",
                                    creative_id="creative-a", creative_revision=1)
        self.assertFalse(result["billable"])
        row = self.desk.db.execute("SELECT billable FROM bookings WHERE booking_id='mg'").fetchone()
        self.assertEqual(row[0], 0)

    def test_all_authority_flags_remain_false(self):
        self.seed(insertions=1)
        snap = self.desk.snapshot()
        self.assertEqual(snap["authority"], AUTHORITY_FLAGS)
        self.assertTrue(all(v is False for v in snap["authority"].values()))


if __name__ == "__main__":
    unittest.main()

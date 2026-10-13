#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import desk


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "desk.sqlite3"
        self.desk = desk.OutboundDesk(self.db)
        self.addCleanup(self.desk.close)
        self.desk.create_campaign(
            campaign_id="campaign", customer_name="Example Seller", offer="a bounded scheduling workflow",
            source_policy="customer-provided lawful source only", operation_id="op-campaign",
        )

    def add(self, prospect_id="p1", route="route-1"):
        return self.desk.add_prospect(
            campaign_id="campaign", prospect_id=prospect_id, organization="Synthetic Buyer",
            contact_name="Sample Contact", route_ref=route, source_ref="example://lawful-source/1",
            lawful_source_note="synthetic fixture from a customer-provided business directory",
            relevance_note="the sample business manually coordinates appointments",
            operation_id=f"op-add-{prospect_id}",
        )

    def interested(self, prospect_id="p1"):
        return self.desk.record_reply(
            prospect_id=prospect_id, reply_id=f"reply-{prospect_id}", kind="interested",
            note="Synthetic contact asked for a slot.", received_at="2026-09-08T12:00:00Z",
            operation_id=f"op-reply-{prospect_id}",
        )

    def slot(self, slot_id="slot-1"):
        return self.desk.add_slot(
            slot_id=slot_id, starts_at="2026-09-09T15:00:00Z", ends_at="2026-09-09T15:30:00Z",
            operation_id=f"op-{slot_id}",
        )

    def test_customer_specific_unsent_draft_and_no_transport(self):
        self.add()
        result = self.desk.create_draft(prospect_id="p1", operation_id="op-draft")
        self.assertEqual(result["state"], "UNSENT")
        self.assertEqual(result["transport"], "NONE")
        self.assertIn("Example Seller", result["body"])
        self.assertIn("bounded scheduling workflow", result["body"])
        self.assertIn("manually coordinates appointments", result["body"])

    def test_lawful_source_metadata_is_required(self):
        with self.assertRaises(desk.DeskError):
            self.desk.add_prospect(
                campaign_id="campaign", prospect_id="p1", organization="Synthetic Buyer", contact_name="Sample",
                route_ref="route-1", source_ref="", lawful_source_note="synthetic", relevance_note="relevant",
                operation_id="op-bad",
            )
        self.assertEqual(self.desk.status()["counts"]["prospects"], 0)

    def test_opt_out_durably_blocks_future_drafts_after_reopen(self):
        self.add()
        self.desk.create_draft(prospect_id="p1", operation_id="op-draft")
        self.desk.record_reply(
            prospect_id="p1", reply_id="reply-optout", kind="opt_out", note="Synthetic opt-out",
            received_at="2026-09-08T12:00:00Z", operation_id="op-optout",
        )
        self.assertTrue(self.desk.is_suppressed("route-1"))
        with self.assertRaisesRegex(desk.DeskError, "suppressed"):
            self.desk.create_draft(prospect_id="p1", operation_id="op-draft-after")
        self.desk.close()
        self.desk = desk.OutboundDesk(self.db)
        self.assertTrue(self.desk.is_suppressed("route-1"))
        with self.assertRaisesRegex(desk.DeskError, "suppressed"):
            self.desk.create_draft(prospect_id="p1", operation_id="op-draft-reopen")

    def test_opt_out_blocks_booking_even_with_available_slot(self):
        self.add()
        self.desk.record_reply(
            prospect_id="p1", reply_id="reply-optout", kind="opt_out", note="Synthetic opt-out",
            received_at="2026-09-08T12:00:00Z", operation_id="op-optout",
        )
        self.slot()
        with self.assertRaisesRegex(desk.DeskError, "suppressed"):
            self.desk.book_slot(prospect_id="p1", slot_id="slot-1", operation_id="op-book")
        self.assertEqual(self.desk.status()["counts"]["bookings"], 0)

    def test_interested_reply_books_available_slot(self):
        self.add()
        self.interested()
        self.slot()
        result = self.desk.book_slot(prospect_id="p1", slot_id="slot-1", operation_id="op-book")
        self.assertEqual(result["transport"], "LOCAL_HANDOFF_ONLY")
        self.assertFalse(result["calendar_provider_mutation"])
        self.assertEqual(self.desk.crm_rows("campaign")[0]["status"], "BOOKED")

    def test_booking_requires_interested_latest_reply(self):
        self.add()
        self.slot()
        with self.assertRaisesRegex(desk.DeskError, "interested"):
            self.desk.book_slot(prospect_id="p1", slot_id="slot-1", operation_id="op-book")
        self.desk.record_reply(
            prospect_id="p1", reply_id="reply-question", kind="question", note="Synthetic question",
            received_at="2026-09-08T12:00:00Z", operation_id="op-question",
        )
        with self.assertRaisesRegex(desk.DeskError, "interested"):
            self.desk.book_slot(prospect_id="p1", slot_id="slot-1", operation_id="op-book-2")

    def test_slot_cannot_be_double_booked(self):
        self.add("p1", "route-1")
        self.add("p2", "route-2")
        self.interested("p1")
        self.interested("p2")
        self.slot()
        self.desk.book_slot(prospect_id="p1", slot_id="slot-1", operation_id="op-book-1")
        with self.assertRaisesRegex(desk.DeskError, "unavailable"):
            self.desk.book_slot(prospect_id="p2", slot_id="slot-1", operation_id="op-book-2")

    def test_operation_retry_is_idempotent_and_conflicting_reuse_fails(self):
        self.add()
        first = self.desk.create_draft(prospect_id="p1", operation_id="op-draft")
        second = self.desk.create_draft(prospect_id="p1", operation_id="op-draft")
        self.assertEqual(first, second)
        self.assertEqual(self.desk.status()["counts"]["drafts"], 1)
        with self.assertRaisesRegex(desk.DeskError, "different input"):
            self.desk.book_slot(prospect_id="p1", slot_id="slot-x", operation_id="op-draft")

    def test_ics_handoff_contains_time_and_local_only_note(self):
        self.add()
        self.interested()
        self.slot()
        booking = self.desk.book_slot(prospect_id="p1", slot_id="slot-1", operation_id="op-book")
        ics = self.desk.booking_ics(booking["booking_id"])
        self.assertIn("BEGIN:VCALENDAR\r\n", ics)
        self.assertIn("DTSTART:20260909T150000Z", ics)
        self.assertIn("DTEND:20260909T153000Z", ics)
        self.assertIn("Local handoff only", ics)

    def test_export_contains_json_csv_and_ics(self):
        self.add()
        self.interested()
        self.slot()
        booking = self.desk.book_slot(prospect_id="p1", slot_id="slot-1", operation_id="op-book")
        target = self.root / "export"
        result = self.desk.export_campaign("campaign", target)
        self.assertEqual(result["files"], [f"{booking['booking_id']}.ics", "crm.csv", "handoff.json"])
        payload = json.loads((target / "handoff.json").read_text())
        self.assertEqual(payload["transport"], "NONE")
        self.assertFalse(payload["calendar_provider_mutation"])
        with (target / "crm.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["status"], "BOOKED")
        self.assertEqual(rows[0]["latest_reply"], "interested")

    def test_suppressed_route_cannot_be_reintroduced_under_new_prospect_id(self):
        self.add()
        self.desk.record_reply(
            prospect_id="p1", reply_id="reply-optout", kind="opt_out", note="Synthetic opt-out",
            received_at="2026-09-08T12:00:00Z", operation_id="op-optout",
        )
        with self.assertRaisesRegex(desk.DeskError, "suppressed"):
            self.desk.add_prospect(
                campaign_id="campaign", prospect_id="p2", organization="Synthetic Buyer Again", contact_name="Sample",
                route_ref="route-1", source_ref="example://lawful-source/2",
                lawful_source_note="synthetic", relevance_note="relevant", operation_id="op-add-p2",
            )

    def test_invalid_or_naive_slot_times_fail_closed(self):
        for start, end in (
            ("bad", "2026-09-09T15:30:00Z"),
            ("2026-09-09T15:00:00", "2026-09-09T15:30:00Z"),
            ("2026-09-09T16:00:00Z", "2026-09-09T15:30:00Z"),
        ):
            with self.subTest(start=start, end=end):
                with self.assertRaises(desk.DeskError):
                    self.desk.add_slot(slot_id=f"slot-{start}", starts_at=start, ends_at=end, operation_id=f"op-{start}")
        self.assertEqual(self.desk.status()["counts"]["slots"], 0)


class CliTests(unittest.TestCase):
    def test_demo_is_runnable_and_persists_synthetic_booking_and_suppression(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "demo.sqlite3"
            export = root / "export"
            result = subprocess.run(
                [sys.executable, "-B", str(HERE / "desk.py"), "--db", str(db), "demo", "--export", str(export)],
                cwd=root, text=True, capture_output=True, check=False, timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"]["counts"]["bookings"], 1)
            self.assertEqual(payload["status"]["counts"]["suppressions"], 1)
            self.assertTrue((export / "handoff.json").is_file())
            with desk.OutboundDesk(db) as reopened:
                self.assertTrue(reopened.is_suppressed("synthetic-route-2"))
                self.assertEqual(reopened.crm_rows("demo-campaign")[0]["status"], "BOOKED")

    def test_no_send_subcommand_exists(self):
        result = subprocess.run(
            [sys.executable, "-B", str(HERE / "desk.py"), "send"],
            text=True, capture_output=True, check=False, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()

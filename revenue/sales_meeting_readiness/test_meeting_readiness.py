from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from revenue.sales_meeting_readiness.meeting_readiness import (
    CALENDAR_REQUIRED,
    DEFAULT_POLICY,
    HOLD,
    PREP_REQUIRED,
    READY,
    REQUEST_STALE,
    SLOT_CONFLICT,
    MeetingReadinessError,
    busy_digest,
    canonical_json_bytes,
    compile_meeting_readiness,
    load_json_strict,
    render_markdown,
    request_digest,
    verify_receipt,
)

AS_OF = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)


def ready_packet():
    packet = {
        "schema": "sales-meeting-readiness/v1",
        "opportunity_id": "op.uiowa.18649",
        "owner_ref": "owner.bryce",
        "counterparty_ref": "counterparty.clarks-consulting",
        "thread_ref": "thread.uiowa.18649.1",
        "inbound": {
            "observation_id": "inbound.20260913.001",
            "content_sha256": "1" * 64,
            "received_at": "2026-09-13T13:30:00Z",
        },
        "request": {
            "duration_minutes": 30,
            "timezone": "America/New_York",
            "windows": [
                {"start": "2026-09-14T18:00:00Z", "end": "2026-09-14T20:00:00Z"},
                {"start": "2026-09-15T14:00:00Z", "end": "2026-09-15T16:00:00Z"},
            ],
        },
        "prep": {
            "context": [
                {"text": "Prime expressed interest and requested our information.", "source_ref": "inbound.20260913.001"},
                {"text": "Our role is bounded technical production and evidence support.", "source_ref": "artifact.team-split.v1"},
            ],
            "objective": "Confirm fit, workshare, decision path, and the next concrete commercial step.",
            "key_questions": [
                "Which technical workstream would they want us to own if the pursuit advances?",
                "What evidence, staffing, and commercial inputs do they need from us next?",
            ],
            "likely_asks": ["A concise capability summary", "Scope, staffing assumptions, and commercial terms after fit is confirmed"],
            "risks_commitments_to_avoid": [
                "Do not claim prime authority or buyer acceptance.",
                "Do not commit price, staffing, schedule, references, or exclusivity without owner approval.",
            ],
            "recommended_opening": "Thanks for making time. I want to confirm the work split and what would make us useful to your response.",
            "recommended_closing": "If the fit is real, let us leave with one owned next step, the exact inputs needed, and who is making the decision.",
            "owner_actions": ["Decide whether to authorize commercial terms only after the workshare is concrete."],
        },
    }
    req_digest = request_digest(packet["opportunity_id"], packet["thread_ref"], packet["request"])
    busy = [
        {"start": "2026-09-14T17:00:00Z", "end": "2026-09-14T18:00:00Z"},
        {"start": "2026-09-14T18:30:00Z", "end": "2026-09-14T19:00:00Z"},
    ]
    packet["availability"] = {
        "observation_id": "calendar.20260913.001",
        "provider_ref": "calendar.primary",
        "captured_at": "2026-09-13T15:55:00Z",
        "owner_ref": packet["owner_ref"],
        "opportunity_id": packet["opportunity_id"],
        "thread_ref": packet["thread_ref"],
        "timezone": packet["request"]["timezone"],
        "duration_minutes": packet["request"]["duration_minutes"],
        "request_digest": req_digest,
        "busy_windows": busy,
        "busy_digest": busy_digest(busy),
        "result": "FREE",
        "proposed_slot": {"start": "2026-09-14T18:00:00Z", "end": "2026-09-14T18:30:00Z"},
    }
    return packet


class MeetingReadinessTests(unittest.TestCase):
    def compile(self, packet=None, *, as_of=AS_OF, policy=DEFAULT_POLICY):
        return compile_meeting_readiness(packet or ready_packet(), as_of=as_of, policy=policy)

    def test_ready(self):
        receipt = self.compile()
        self.assertEqual(receipt["state"], READY)
        self.assertTrue(receipt["authority"]["owner_review_only"])
        self.assertFalse(receipt["authority"]["calendar_mutation"])
        self.assertFalse(receipt["authority"]["send_or_reply"])
        self.assertTrue(verify_receipt(ready_packet(), receipt))

    def test_synthetic_fixture_ready(self):
        fixture = Path("revenue/sales_meeting_readiness/fixtures/synthetic_ready.json")
        packet = load_json_strict(fixture.read_bytes())
        receipt = self.compile(packet)
        self.assertEqual(receipt["state"], READY)
        self.assertTrue(verify_receipt(packet, receipt))

    def test_deterministic(self):
        a = self.compile()
        b = self.compile(deepcopy(ready_packet()))
        self.assertEqual(canonical_json_bytes(a), canonical_json_bytes(b))
        self.assertEqual(render_markdown(a), render_markdown(b))

    def test_missing_availability(self):
        p = ready_packet(); p.pop("availability")
        self.assertEqual(self.compile(p)["state"], CALENDAR_REQUIRED)

    def test_stale_availability(self):
        p = ready_packet(); p["availability"]["captured_at"] = "2026-09-13T15:00:00Z"
        self.assertEqual(self.compile(p)["state"], CALENDAR_REQUIRED)

    def test_future_availability(self):
        p = ready_packet(); p["availability"]["captured_at"] = "2026-09-13T16:01:00Z"
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_stale_request(self):
        p = ready_packet(); p["inbound"]["received_at"] = "2026-09-01T00:00:00Z"
        self.assertEqual(self.compile(p)["state"], REQUEST_STALE)

    def test_future_inbound(self):
        p = ready_packet(); p["inbound"]["received_at"] = "2026-09-13T16:01:00Z"
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_wrong_request_digest(self):
        p = ready_packet(); p["availability"]["request_digest"] = "f" * 64
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_wrong_busy_digest(self):
        p = ready_packet(); p["availability"]["busy_digest"] = "e" * 64
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_cross_thread_transplant(self):
        p = ready_packet(); p["availability"]["thread_ref"] = "thread.other"
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_cross_opportunity_transplant(self):
        p = ready_packet(); p["availability"]["opportunity_id"] = "op.other"
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_missing_owner_binding_fails_closed(self):
        p = ready_packet(); p["availability"].pop("owner_ref")
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_cross_owner_transplant(self):
        p = ready_packet(); p["owner_ref"] = "owner.other"
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_wrong_duration_binding(self):
        p = ready_packet(); p["availability"]["duration_minutes"] = 45
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_wrong_timezone_binding(self):
        p = ready_packet(); p["availability"]["timezone"] = "UTC"
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_slot_wrong_duration(self):
        p = ready_packet(); p["availability"]["proposed_slot"]["end"] = "2026-09-14T18:45:00Z"
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_slot_already_started_is_stale(self):
        p = ready_packet()
        p["request"]["windows"] = [
            {"start": "2026-09-13T15:30:00Z", "end": "2026-09-13T16:30:00Z"}
        ]
        p["availability"]["proposed_slot"] = {
            "start": "2026-09-13T15:45:00Z",
            "end": "2026-09-13T16:15:00Z",
        }
        p["availability"]["request_digest"] = request_digest(
            p["opportunity_id"], p["thread_ref"], p["request"]
        )
        self.assertEqual(self.compile(p)["state"], REQUEST_STALE)

    def test_slot_outside_requested_window(self):
        p = ready_packet(); p["availability"]["proposed_slot"] = {"start": "2026-09-14T20:00:00Z", "end": "2026-09-14T20:30:00Z"}
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_overlap_is_conflict(self):
        p = ready_packet(); p["availability"]["proposed_slot"] = {"start": "2026-09-14T18:15:00Z", "end": "2026-09-14T18:45:00Z"}
        p["availability"]["result"] = "BUSY"
        self.assertEqual(self.compile(p)["state"], SLOT_CONFLICT)

    def test_free_claim_with_overlap_holds(self):
        p = ready_packet(); p["availability"]["proposed_slot"] = {"start": "2026-09-14T18:15:00Z", "end": "2026-09-14T18:45:00Z"}
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_exact_boundary_non_overlap(self):
        self.assertEqual(self.compile()["state"], READY)

    def test_busy_claim_without_busy_evidence_holds(self):
        p = ready_packet(); p["availability"]["result"] = "BUSY"
        self.assertEqual(self.compile(p)["state"], HOLD)

    def test_unknown_calendar_requires_check(self):
        p = ready_packet(); p["availability"]["result"] = "UNKNOWN"
        self.assertEqual(self.compile(p)["state"], CALENDAR_REQUIRED)

    def test_each_missing_prep_field(self):
        fields = ["context", "objective", "key_questions", "likely_asks", "risks_commitments_to_avoid", "recommended_opening", "recommended_closing", "owner_actions"]
        for field in fields:
            with self.subTest(field=field):
                p = ready_packet()
                p["prep"][field] = [] if field in {"context", "key_questions", "likely_asks", "risks_commitments_to_avoid", "owner_actions"} else ""
                self.assertEqual(self.compile(p)["state"], PREP_REQUIRED)

    def test_email_in_prep_rejected(self):
        p = ready_packet(); p["prep"]["objective"] = "Email person@example.com after the meeting"
        with self.assertRaises(MeetingReadinessError): self.compile(p)

    def test_phone_in_prep_rejected(self):
        p = ready_packet(); p["prep"]["objective"] = "Call 555-123-4567"
        with self.assertRaises(MeetingReadinessError): self.compile(p)

    def test_bool_duration_rejected(self):
        p = ready_packet(); p["request"]["duration_minutes"] = True
        with self.assertRaises(MeetingReadinessError): self.compile(p)

    def test_bad_timezone_rejected(self):
        p = ready_packet(); p["request"]["timezone"] = "Moon/SeaOfTranquility"
        with self.assertRaises(MeetingReadinessError): self.compile(p)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(MeetingReadinessError): load_json_strict('{"a":1,"a":2}')

    def test_changed_inbound_bytes_changes_receipt(self):
        p = ready_packet(); a = self.compile(p)
        p["inbound"]["content_sha256"] = "2" * 64
        b = self.compile(p)
        self.assertNotEqual(a["packet_sha256"], b["packet_sha256"])

    def test_receipt_tamper_fails(self):
        p = ready_packet(); receipt = self.compile(p); receipt["state"] = SLOT_CONFLICT
        with self.assertRaises(MeetingReadinessError): verify_receipt(p, receipt)

    def test_policy_drift_fails(self):
        p = ready_packet(); receipt = self.compile(p)
        policy = deepcopy(DEFAULT_POLICY); policy["max_availability_age_seconds"] = 3600
        with self.assertRaises(MeetingReadinessError): verify_receipt(p, receipt, policy=policy)

    def test_window_order_invariance(self):
        p = ready_packet(); a = self.compile(p)
        p["request"]["windows"].reverse()
        p["availability"]["request_digest"] = request_digest(p["opportunity_id"], p["thread_ref"], p["request"])
        b = self.compile(p)
        self.assertEqual(a["packet_sha256"], b["packet_sha256"])

    def test_busy_order_invariance(self):
        p = ready_packet(); a = self.compile(p)
        p["availability"]["busy_windows"].reverse()
        p["availability"]["busy_digest"] = busy_digest(sorted(p["availability"]["busy_windows"], key=lambda x: (x["start"], x["end"])))
        b = self.compile(p)
        self.assertEqual(a["packet_sha256"], b["packet_sha256"])

    def test_cli_create_exclusive_and_verify(self):
        p = ready_packet()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            inp = td / "packet.json"; jout = td / "receipt.json"; mout = td / "brief.md"
            inp.write_bytes(canonical_json_bytes(p))
            cmd = [sys.executable, "-m", "revenue.sales_meeting_readiness.cli", "compile", "--input", str(inp), "--json-out", str(jout), "--md-out", str(mout)]
            env = dict(os.environ); env["PYTHONPATH"] = os.getcwd()
            run = subprocess.run(cmd, cwd=os.getcwd(), env=env, text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue(jout.exists()); self.assertTrue(mout.exists())
            second = subprocess.run(cmd, cwd=os.getcwd(), env=env, text=True, capture_output=True)
            self.assertEqual(second.returncode, 2)
            verify = subprocess.run([sys.executable, "-m", "revenue.sales_meeting_readiness.cli", "verify", "--input", str(inp), "--receipt", str(jout)], cwd=os.getcwd(), env=env, text=True, capture_output=True)
            self.assertEqual(verify.returncode, 0, verify.stderr)
            self.assertIn("VERIFIED", verify.stdout)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_cli_refuses_symlink_output(self):
        p = ready_packet()
        with tempfile.TemporaryDirectory() as td:
            td = Path(td); inp = td / "packet.json"; target = td / "real.json"; link = td / "receipt.json"; md = td / "brief.md"
            inp.write_bytes(canonical_json_bytes(p)); target.write_text("sentinel")
            os.symlink(target, link)
            env = dict(os.environ); env["PYTHONPATH"] = os.getcwd()
            run = subprocess.run([sys.executable, "-m", "revenue.sales_meeting_readiness.cli", "compile", "--input", str(inp), "--json-out", str(link), "--md-out", str(md)], cwd=os.getcwd(), env=env, text=True, capture_output=True)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(target.read_text(), "sentinel")


if __name__ == "__main__":
    unittest.main()

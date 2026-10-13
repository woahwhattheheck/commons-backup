from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("reply_to_revenue", ROOT / "host" / "reply_to_revenue.py")
assert SPEC and SPEC.loader
r2r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r2r)


class ReplyToRevenueTests(unittest.TestCase):
    def test_auto_ack_is_never_buyer_interest(self) -> None:
        verdict = r2r.classify_signals(
            ["thank you for reaching out", "ticket has been created", "delivered by zendesk"],
            "POSITIVE_SCOPE",
        )
        self.assertEqual(verdict["classification"], "AUTO_RESPONSE")
        self.assertFalse(verdict["buyer_interest"])
        self.assertTrue(verdict["auto_ack"])
        self.assertFalse(verdict["delivery_failure"])
        self.assertEqual(verdict["next_action"], "WAIT_FOR_HUMAN_REPLY")

    def test_vendor_ai_assistant_is_auto_ack(self) -> None:
        verdict = r2r.classify_signals(
            ["ai assistant", "a human will respond", "this answer was composed by", "ai agent"]
        )
        self.assertEqual(verdict["classification"], "AUTO_RESPONSE")
        self.assertFalse(verdict["buyer_interest"])
        self.assertFalse(verdict["delivery_failure"])

    def test_csat_survey_is_auto_ack(self) -> None:
        verdict = r2r.classify_signals(["how would you rate", "rate the support you received"])
        self.assertEqual(verdict["classification"], "AUTO_RESPONSE")
        self.assertFalse(verdict["buyer_interest"])
        self.assertFalse(verdict["delivery_failure"])

    def test_vacation_reply_stays_auto_response(self) -> None:
        verdict = r2r.classify_signals(["automatic reply", "out of office", "vacation responder"])
        self.assertEqual(verdict["classification"], "AUTO_RESPONSE")
        self.assertTrue(verdict["auto_ack"])
        self.assertFalse(verdict["delivery_failure"])
        self.assertEqual(verdict["next_action"], "WAIT_FOR_HUMAN_REPLY")

    def test_mailer_daemon_is_delivery_failure_not_auto_ack(self) -> None:
        verdict = r2r.classify_signals(
            ["mailer-daemon", "delivery status notification (failure)"],
            "POSITIVE_SCOPE",
        )
        self.assertEqual(verdict["classification"], "DELIVERY_FAILURE")
        self.assertFalse(verdict["buyer_interest"])
        self.assertFalse(verdict["auto_ack"])
        self.assertTrue(verdict["delivery_failure"])
        self.assertEqual(verdict["next_action"], "RECOVER_ROUTE_OWNER_REVIEW")
        self.assertIn("override", verdict["reason"])

    def test_delivery_failure_precedes_generic_auto_ack(self) -> None:
        verdict = r2r.classify_signals(
            ["automatic reply", "message blocked", "address not found", "thank you for reaching out"]
        )
        self.assertEqual(verdict["classification"], "DELIVERY_FAILURE")
        self.assertFalse(verdict["auto_ack"])
        self.assertTrue(verdict["delivery_failure"])
        self.assertIn("message blocked", verdict["matched_markers"])
        self.assertIn("address not found", verdict["matched_markers"])

    def test_delivery_failure_cannot_be_operator_requested_without_marker(self) -> None:
        with self.assertRaises(r2r.ReplyRevenueError):
            r2r.classify_signals(["operator note only"], "DELIVERY_FAILURE")

    def test_explicit_scope_language_without_auto_ack_is_positive(self) -> None:
        verdict = r2r.classify_signals(["please invoice", "we accept the scope"])
        self.assertEqual(verdict["classification"], "POSITIVE_SCOPE")
        self.assertTrue(verdict["buyer_interest"])
        self.assertFalse(verdict["delivery_failure"])
        self.assertEqual(verdict["next_action"], "NEEDS_ACCEPTANCE")

    def test_delivery_failure_contact_maps_to_owner_recovery_without_send(self) -> None:
        receipts = [
            {
                "prospect_key": "example-buyer",
                "organization": "Example Buyer",
                "hard_dnr": True,
                "receipt_id": "receipt-example-1",
                "path": "fixture.json",
                "cash_usd": 0,
            }
        ]
        inbound = [
            {
                "event_ref": "opaque:fixture-bounce-01",
                "received_at": "2026-09-13T12:00:00Z",
                "prospect_key": "example-buyer",
                "matched_receipt_id": "receipt-example-1",
                "classification": "DELIVERY_FAILURE",
            }
        ]
        contacts = r2r._contact_rows(receipts, inbound)
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]["lane"], "DELIVERY_FAILURE")
        self.assertEqual(contacts[0]["next_action"], "RECOVER_ROUTE_OWNER_REVIEW")
        self.assertEqual(contacts[0]["handoff"], r2r.ROUTE_RECOVERY_TOOL)
        self.assertFalse(contacts[0]["resend"])
        recovery = r2r.surface_route_recovery(contacts, inbound)
        self.assertEqual(recovery["count"], 1)
        self.assertEqual(recovery["transport_actions"], 0)
        self.assertEqual(recovery["resends"], 0)
        self.assertEqual(recovery["authority"], "OWNER_REVIEW_ONLY")
        self.assertEqual(recovery["items"][0]["event_ref"], "opaque:fixture-bounce-01")
        self.assertFalse(recovery["items"][0]["buyer_interest"])
        self.assertFalse(recovery["items"][0]["resend"])

    def test_real_human_positive_supersedes_older_delivery_failure_at_contact_level(self) -> None:
        receipts = [
            {
                "prospect_key": "example-buyer",
                "organization": "Example Buyer",
                "hard_dnr": True,
                "receipt_id": "receipt-example-1",
                "path": "fixture.json",
                "cash_usd": 0,
            }
        ]
        inbound = [
            {
                "event_ref": "opaque:fixture-bounce-01",
                "received_at": "2026-09-13T12:00:00Z",
                "prospect_key": "example-buyer",
                "matched_receipt_id": "receipt-example-1",
                "classification": "DELIVERY_FAILURE",
            },
            {
                "event_ref": "opaque:fixture-human-01",
                "received_at": "2026-09-13T12:10:00Z",
                "prospect_key": "example-buyer",
                "matched_receipt_id": "receipt-example-1",
                "classification": "POSITIVE_SCOPE",
            },
        ]
        contacts = r2r._contact_rows(receipts, inbound)
        self.assertEqual(contacts[0]["lane"], "HUMAN_POSITIVE")
        self.assertEqual(contacts[0]["next_action"], "NEEDS_ACCEPTANCE")
        recovery = r2r.surface_route_recovery(contacts, inbound)
        self.assertEqual(recovery["count"], 0)

    def test_langfuse_is_hard_dnr_zero_cash(self) -> None:
        funnel = r2r.validate_funnel()
        langfuse = next(c for c in funnel["contacts"] if c["prospect_key"] == "langfuse")
        self.assertTrue(langfuse["hard_dnr"])
        self.assertFalse(langfuse["resend"])
        self.assertEqual(langfuse["cash_usd"], 0)
        self.assertEqual(langfuse["organization"], "Langfuse GmbH")
        self.assertEqual(langfuse["receipt_count"], 1)
        self.assertEqual(funnel["truth"]["cash_usd"], 0)
        self.assertEqual(funnel["truth"]["transport_actions"], 0)
        receipt = r2r.read_object(
            ROOT / "revenue" / "payment_ready" / "outreach_receipts" / "20260828-langfuse-1a0496451e052b9d.json"
        )
        self.assertTrue(receipt["dedupe"]["do_not_resend"])
        self.assertEqual(receipt["facts"]["collected_cash_usd"], 0)
        self.assertFalse(receipt["facts"]["cash_claimed"])
        self.assertEqual(receipt["provider_state"], "COMPLETED")

    def test_nysa_technology_is_hard_dnr_zero_cash(self) -> None:
        funnel = r2r.validate_funnel()
        nysa = next(c for c in funnel["contacts"] if c["prospect_key"] == "nysa-technology")
        self.assertTrue(nysa["hard_dnr"])
        self.assertFalse(nysa["resend"])
        self.assertEqual(nysa["cash_usd"], 0)
        self.assertEqual(nysa["organization"], "NYSA Technology")
        self.assertEqual(nysa["lane"], "NO_RESPONSE")
        self.assertEqual(nysa["next_action"], "MONITOR_NO_RESEND")
        self.assertEqual(nysa["receipt_count"], 1)
        self.assertEqual(nysa["inbound_count"], 0)
        self.assertIsNone(nysa["handoff"])
        receipt = r2r.read_object(
            ROOT
            / "revenue"
            / "payment_ready"
            / "outreach_receipts"
            / "20260914-nysa-technology-do-not-resend.json"
        )
        self.assertTrue(receipt["dedupe"]["do_not_resend"])
        self.assertEqual(receipt["facts"]["collected_cash_usd"], 0)
        self.assertFalse(receipt["facts"]["cash_claimed"])
        self.assertEqual(receipt["decision"], "HOLD_DO_NOT_RESEND")

    def test_committed_funnel_tracks_all_receipt_contacts(self) -> None:
        receipts = r2r.load_receipts()
        snapshot = r2r.read_object(r2r.FUNNEL_PATH)
        snapshot_keys = {contact["prospect_key"] for contact in snapshot["contacts"]}
        receipt_keys = {receipt["prospect_key"] for receipt in receipts}
        self.assertEqual(snapshot_keys, receipt_keys)
        self.assertEqual(len(receipts), snapshot["truth"]["canonical_receipts"])
        self.assertEqual(len(snapshot_keys), snapshot["truth"]["distinct_contacts"])

    def test_checked_in_funnel_is_all_dnr_auto_acks_and_zero_cash(self) -> None:
        funnel = r2r.validate_funnel()
        self.assertEqual(funnel["truth"]["cash_usd"], 0)
        self.assertEqual(funnel["truth"]["resends"], 0)
        self.assertEqual(funnel["truth"]["transport_actions"], 0)
        self.assertEqual(funnel["truth"]["human_positive"], 0)
        self.assertEqual(funnel["truth"]["delivery_failures"], 0)
        self.assertEqual(funnel["truth"]["scope_acceptances"], 0)
        self.assertEqual(funnel["truth"]["inbound_recorded"], 4)
        self.assertEqual(funnel["truth"]["auto_acks"], 4)
        self.assertEqual(funnel["surfaces"], [])
        self.assertTrue(funnel["truth"]["distinct_contacts"] >= 7)
        self.assertEqual(funnel["truth"]["hard_dnr_contacts"], funnel["truth"]["distinct_contacts"])
        self.assertTrue(all(contact["hard_dnr"] and contact["resend"] is False for contact in funnel["contacts"]))
        self.assertTrue(all(event["auto_ack"] and not event["buyer_interest"] for event in funnel["inbound"]))
        blob = r2r.canonical_text(funnel)
        for word in ("replied", "accepted", "invoiced", "authorized", "settled", "delivered", "paid"):
            self.assertNotRegex(blob, rf"\b{word}\b")

    def test_duplicate_event_ref_with_new_hash_collides(self) -> None:
        observations = r2r.read_object(r2r.OBSERVATIONS_PATH)
        duplicate = copy.deepcopy(observations["events"][0])
        duplicate["payload_sha256"] = "0" * 64
        observations["events"].append(duplicate)
        observations["monitor"]["attributed_inbound"] = len(observations["events"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.json"
            path.write_text(r2r.canonical_text(observations), encoding="utf-8")
            with self.assertRaises(r2r.CollisionError):
                r2r.load_observations(path)

    def test_same_event_is_ingested_once(self) -> None:
        observations = r2r.read_object(r2r.OBSERVATIONS_PATH)
        observations["events"].append(copy.deepcopy(observations["events"][0]))
        observations["monitor"]["attributed_inbound"] = 4
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.json"
            path.write_text(r2r.canonical_text(observations), encoding="utf-8")
            loaded = r2r.load_observations(path)
        self.assertEqual(len(loaded["events"]), 4)
        self.assertTrue(all(not event["delivery_failure"] for event in loaded["events"]))

    def test_send_flag_is_always_refused(self) -> None:
        funnel = r2r.build_funnel()
        with self.assertRaises(r2r.ResendError):
            r2r.assert_no_resend(funnel, send=True)

    def test_cli_validate_and_classify_are_deterministic(self) -> None:
        command = [sys.executable, str(ROOT / "host" / "reply_to_revenue.py"), "validate"]
        first = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True).stdout
        second = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True).stdout
        self.assertEqual(first, second)
        self.assertIn("0 delivery-failures", first)
        self.assertIn("0 resends", first)
        self.assertIn("USD 0 cash", first)
        classify = subprocess.run(
            [
                sys.executable,
                str(ROOT / "host" / "reply_to_revenue.py"),
                "classify",
                "--markers",
                "ticket has been created,thank you for reaching out",
                "--requested",
                "POSITIVE_SCOPE",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        parsed = json.loads(classify)
        self.assertEqual(parsed["classification"], "AUTO_RESPONSE")
        self.assertFalse(parsed["buyer_interest"])
        self.assertFalse(parsed["delivery_failure"])

    def test_recover_cli_is_zero_send_for_checked_in_history(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "host" / "reply_to_revenue.py"), "recover"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed["classification"], "DELIVERY_FAILURE")
        self.assertEqual(parsed["count"], 0)
        self.assertEqual(parsed["transport_actions"], 0)
        self.assertEqual(parsed["resends"], 0)
        self.assertEqual(parsed["authority"], "OWNER_REVIEW_ONLY")

    def test_monitor_send_exits_three(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "host" / "reply_to_revenue.py"), "monitor", "--send"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 3)
        self.assertIn("never sends", result.stderr)

    def test_positive_surface_hands_to_acceptance(self) -> None:
        contacts = [
            {
                "prospect_key": "example-buyer",
                "organization": "Example",
                "lane": "HUMAN_POSITIVE",
                "hard_dnr": True,
                "resend": False,
            }
        ]
        inbound = [
            {
                "event_ref": "opaque:fixture-positive-01",
                "received_at": "2026-08-28T00:00:00Z",
                "prospect_key": "example-buyer",
                "classification": "POSITIVE_SCOPE",
            }
        ]
        surfaces = r2r.surface_positives(contacts, inbound)
        self.assertEqual(len(surfaces), 1)
        self.assertEqual(surfaces[0]["next_action"], "NEEDS_ACCEPTANCE")
        self.assertEqual(surfaces[0]["handoff"], "revenue/production_survival/acceptance.py")
        self.assertTrue(surfaces[0]["buyer_interest"])


if __name__ == "__main__":
    unittest.main()

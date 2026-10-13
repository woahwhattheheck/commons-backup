import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from revenue.invoice_resolution_portal_pilot.core import (
    ContractError,
    compile_packet,
    loads_strict,
    main,
    render_owner_report,
    verify_packet,
)


def h(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sample():
    invoice_binding = {
        "invoice_id": "INV-1007",
        "revision": "rev-3",
        "snapshot_sha256": h("synthetic-invoice-rev-3"),
    }
    return {
        "schema": "invoice-resolution-pilot-input/v1",
        "case_id": "case-001",
        "evaluated_at": "2026-09-17T12:00:00Z",
        "invoice": {
            **invoice_binding,
            "currency": "USD",
            "amount_minor": 250000,
            "balance_minor": 250000,
            "observed_at": "2026-09-17T09:00:00Z",
            "customer_ref": "customer-demo-001",
        },
        "prior_checkpoint": None,
        "events": [
            {
                "event_id": "evt-001",
                "event_type": "REQUEST_SUBMITTED",
                "observed_at": "2026-09-17T10:00:00Z",
                "invoice_binding": copy.deepcopy(invoice_binding),
                "payload": {
                    "request_id": "req-001",
                    "action": "OPEN_DISPUTE",
                    "statement_sha256": h("synthetic statement"),
                },
            },
            {
                "event_id": "evt-002",
                "event_type": "EVIDENCE_ATTACHED",
                "observed_at": "2026-09-17T10:05:00Z",
                "invoice_binding": copy.deepcopy(invoice_binding),
                "payload": {
                    "request_id": "req-001",
                    "evidence_id": "evidence-001",
                    "evidence_sha256": h("synthetic evidence"),
                    "evidence_class": "CUSTOMER_PROVIDED",
                },
            },
        ],
    }


class InvoiceResolutionPilotTests(unittest.TestCase):
    def test_clean_sample_ready_and_authority_false(self):
        packet = compile_packet(sample())
        self.assertEqual("OWNER_REVIEW_READY", packet["state"])
        self.assertEqual([], packet["holds"])
        self.assertEqual("PROPOSED_NOT_ACCEPTED", packet["product"]["commercial_state"])
        self.assertEqual(2500, packet["product"]["pilot_price_usd"])
        self.assertEqual(5000, packet["product"]["optional_integration_price_usd"])
        self.assertTrue(all(value is False for value in packet["authority"].values()))
        self.assertTrue(verify_packet(sample(), packet))

    def test_all_three_bounded_actions_are_supported(self):
        for action in (
            "ACKNOWLEDGE_BALANCE",
            "OPEN_DISPUTE",
            "REQUEST_PAYMENT_PLAN_DISCUSSION",
        ):
            data = sample()
            data["events"][0]["payload"]["action"] = action
            packet = compile_packet(data)
            self.assertEqual(action, packet["request"]["action"])
            self.assertEqual("OWNER_REVIEW_READY", packet["state"])

    def test_event_invoice_transplant_holds(self):
        data = sample()
        data["events"][1]["invoice_binding"]["revision"] = "rev-2"
        packet = compile_packet(data)
        self.assertIn("HOLD_INVOICE_GENERATION_MISMATCH", packet["holds"])
        self.assertEqual("HOLD", packet["state"])

    def test_identical_request_replay_is_idempotent(self):
        data = sample()
        replay = copy.deepcopy(data["events"][0])
        replay["event_id"] = "evt-003"
        replay["observed_at"] = "2026-09-17T10:10:00Z"
        data["events"].append(replay)
        packet = compile_packet(data)
        self.assertEqual("OWNER_REVIEW_READY", packet["state"])
        self.assertEqual(1, packet["request"]["identical_replay_count"])

    def test_conflicting_request_replay_holds(self):
        data = sample()
        replay = copy.deepcopy(data["events"][0])
        replay["event_id"] = "evt-003"
        replay["observed_at"] = "2026-09-17T10:10:00Z"
        replay["payload"]["action"] = "ACKNOWLEDGE_BALANCE"
        data["events"].append(replay)
        packet = compile_packet(data)
        self.assertIn("HOLD_REQUEST_REPLAY_MISMATCH", packet["holds"])

    def test_more_than_one_request_is_out_of_pilot_scope(self):
        data = sample()
        second = copy.deepcopy(data["events"][0])
        second["event_id"] = "evt-003"
        second["observed_at"] = "2026-09-17T10:10:00Z"
        second["payload"]["request_id"] = "req-002"
        data["events"].append(second)
        packet = compile_packet(data)
        self.assertIn("HOLD_MULTIPLE_REQUESTS_OUT_OF_SCOPE", packet["holds"])
        self.assertIsNone(packet["request"])

    def test_evidence_before_request_holds(self):
        data = sample()
        data["events"] = [data["events"][1], data["events"][0]]
        data["events"][0]["observed_at"] = "2026-09-17T09:55:00Z"
        packet = compile_packet(data)
        self.assertIn("HOLD_EVIDENCE_WITHOUT_REQUEST", packet["holds"])

    def test_conflicting_evidence_replay_holds(self):
        data = sample()
        replay = copy.deepcopy(data["events"][1])
        replay["event_id"] = "evt-003"
        replay["observed_at"] = "2026-09-17T10:10:00Z"
        replay["payload"]["evidence_sha256"] = h("different evidence")
        data["events"].append(replay)
        packet = compile_packet(data)
        self.assertIn("HOLD_EVIDENCE_REPLAY_MISMATCH", packet["holds"])

    def test_future_event_holds(self):
        data = sample()
        data["events"][1]["observed_at"] = "2026-09-17T12:00:01Z"
        packet = compile_packet(data)
        self.assertIn("HOLD_FUTURE_EVENT", packet["holds"])

    def test_event_chronology_holds(self):
        data = sample()
        data["events"][1]["observed_at"] = "2026-09-17T09:59:59Z"
        packet = compile_packet(data)
        self.assertIn("HOLD_EVENT_CHRONOLOGY", packet["holds"])

    def test_missing_request_holds(self):
        data = sample()
        data["events"] = []
        packet = compile_packet(data)
        self.assertIn("HOLD_NO_REQUEST", packet["holds"])

    def test_prior_checkpoint_accepts_exact_prefix(self):
        first = sample()
        first["events"] = first["events"][:1]
        first_packet = compile_packet(first)
        extended = sample()
        extended["prior_checkpoint"] = first_packet["next_checkpoint"]
        packet = compile_packet(extended)
        self.assertEqual("OWNER_REVIEW_READY", packet["state"])

    def test_prior_checkpoint_detects_mutated_prefix(self):
        first = sample()
        first["events"] = first["events"][:1]
        checkpoint = compile_packet(first)["next_checkpoint"]
        extended = sample()
        extended["prior_checkpoint"] = checkpoint
        extended["events"][0]["payload"]["statement_sha256"] = h("mutated statement")
        packet = compile_packet(extended)
        self.assertIn("HOLD_PRIOR_CHAIN_MISMATCH", packet["holds"])

    def test_prior_checkpoint_out_of_range_holds(self):
        data = sample()
        data["prior_checkpoint"] = {
            "event_count": 99,
            "chain_root_sha256": h("irrelevant"),
        }
        packet = compile_packet(data)
        self.assertIn("HOLD_PRIOR_CHECKPOINT_OUT_OF_RANGE", packet["holds"])

    def test_packet_tamper_fails_verification(self):
        data = sample()
        packet = compile_packet(data)
        packet["authority"]["can_take_payment"] = True
        self.assertFalse(verify_packet(data, packet))

    def test_recomputed_receipt_cannot_hide_semantic_tamper(self):
        data = sample()
        packet = compile_packet(data)
        packet["product"]["pilot_price_usd"] = 1
        body = dict(packet)
        body.pop("receipt_sha256")
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        packet["receipt_sha256"] = hashlib.sha256(encoded).hexdigest()
        self.assertFalse(verify_packet(data, packet))

    def test_duplicate_json_keys_and_nonfinite_numbers_rejected(self):
        with self.assertRaises(ContractError):
            loads_strict('{"schema":"x","schema":"y"}')
        with self.assertRaises(ContractError):
            loads_strict('{"x":NaN}')

    def test_bool_money_and_extra_key_rejected(self):
        data = sample()
        data["invoice"]["amount_minor"] = True
        with self.assertRaises(ContractError):
            compile_packet(data)
        data = sample()
        data["invoice"]["raw_invoice_text"] = "must never be retained"
        with self.assertRaises(ContractError):
            compile_packet(data)

    def test_raw_statement_or_email_field_has_no_schema_surface(self):
        data = sample()
        data["events"][0]["payload"]["statement"] = "private@example.test"
        with self.assertRaises(ContractError):
            compile_packet(data)
        serialized = json.dumps(compile_packet(sample()), sort_keys=True)
        self.assertNotIn("@", serialized)
        self.assertNotIn("synthetic statement", serialized)

    def test_balance_cannot_exceed_amount(self):
        data = sample()
        data["invoice"]["balance_minor"] = 250001
        with self.assertRaises(ContractError):
            compile_packet(data)

    def test_rendered_owner_report_stays_non_authoritative(self):
        packet = compile_packet(sample())
        report = render_owner_report(packet)
        self.assertIn("proposed, not accepted", report)
        self.assertIn("does not take payment", report)
        self.assertNotIn("PAID", report)

    def test_cli_compile_and_verify_roundtrip(self):
        data = sample()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inp = root / "input.json"
            packet = root / "packet.json"
            report = root / "report.md"
            inp.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(
                0,
                main(
                    [
                        "compile",
                        "--input",
                        str(inp),
                        "--packet-out",
                        str(packet),
                        "--report-out",
                        str(report),
                    ]
                ),
            )
            self.assertTrue(packet.exists())
            self.assertTrue(report.exists())
            self.assertEqual(
                0,
                main(["verify", "--input", str(inp), "--packet", str(packet)]),
            )
            with self.assertRaises(FileExistsError):
                main(
                    [
                        "compile",
                        "--input",
                        str(inp),
                        "--packet-out",
                        str(packet),
                    ]
                )


if __name__ == "__main__":
    unittest.main()

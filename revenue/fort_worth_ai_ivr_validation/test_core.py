from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from . import cli
from .core import ValidationError, VerificationError, compile_receipt, verify_receipt
from .synthetic import ready_packet


class CoreTests(unittest.TestCase):
    def test_ready_synthetic_portfolio(self):
        receipt, report = compile_receipt(ready_packet())
        self.assertEqual(receipt["status"], "EVIDENCE_READY_FOR_PRIME_REVIEW")
        self.assertEqual(receipt["counts"]["scenarios"], 12)
        self.assertEqual(receipt["counts"]["failed"], 0)
        self.assertEqual(receipt["counts"]["exact_event_replays_collapsed"], 1)
        self.assertFalse(receipt["truth_ceiling"]["provider_send_authorized"])
        self.assertFalse(receipt["truth_ceiling"]["booked_revenue_claimed"])
        self.assertIn("Offline validation evidence only", report)

    def test_exact_replay_does_not_add_effect(self):
        packet = ready_packet()
        receipt, _ = compile_receipt(packet)
        row = next(r for r in receipt["results"] if r["scenario_id"] == "after-hours-escalation")
        self.assertEqual(row["logical_effects"], 1)
        self.assertEqual(receipt["counts"]["exact_event_replays_collapsed"], 1)

    def test_conflicting_same_event_id_rejected(self):
        packet = ready_packet()
        conflict = copy.deepcopy(packet["events"][0])
        conflict["action"] = "ABSTAIN"
        conflict["source_refs"] = []
        packet["events"].append(conflict)
        with self.assertRaises(ValidationError):
            compile_receipt(packet)

    def test_second_committed_effect_fails(self):
        packet = ready_packet()
        original = next(e for e in packet["events"] if e["scenario_id"] == "after-hours-escalation")
        second = copy.deepcopy(original)
        second["event_id"] = "evt:after-hours-escalation:retry"
        packet["events"].append(second)
        receipt, _ = compile_receipt(packet)
        row = next(r for r in receipt["results"] if r["scenario_id"] == "after-hours-escalation")
        self.assertEqual(row["result"], "FAIL")
        self.assertIn("DUPLICATE_LOGICAL_EFFECT", row["reasons"])

    def test_unknown_provider_then_retry_fails_closed(self):
        packet = ready_packet()
        original = next(e for e in packet["events"] if e["scenario_id"] == "road-closure-notify")
        original["provider_state"] = "UNKNOWN"
        original["logical_effects"] = 0
        retry = copy.deepcopy(original)
        retry["event_id"] = "evt:road-closure-notify:retry"
        retry["provider_state"] = "COMMITTED"
        retry["logical_effects"] = 1
        packet["events"].append(retry)
        receipt, _ = compile_receipt(packet)
        row = next(r for r in receipt["results"] if r["scenario_id"] == "road-closure-notify")
        self.assertEqual(row["result"], "FAIL")
        self.assertIn("AMBIGUOUS_RETRY_AFTER_UNKNOWN", row["reasons"])

    def test_stale_source_generation_fails(self):
        packet = ready_packet()
        event = next(e for e in packet["events"] if e["scenario_id"] == "permit-es-chat")
        event["source_generation"] -= 1
        receipt, _ = compile_receipt(packet)
        row = next(r for r in receipt["results"] if r["scenario_id"] == "permit-es-chat")
        self.assertIn("SOURCE_GENERATION_MISMATCH", row["reasons"])

    def test_grounding_source_mismatch_fails(self):
        packet = ready_packet()
        event = next(e for e in packet["events"] if e["scenario_id"] == "svc-trash-en-voice")
        event["source_refs"] = ["city:wrong:g7"]
        receipt, _ = compile_receipt(packet)
        row = next(r for r in receipt["results"] if r["scenario_id"] == "svc-trash-en-voice")
        self.assertIn("GROUNDING_SOURCE_MISMATCH", row["reasons"])

    def test_nonanswer_with_citation_fails(self):
        packet = ready_packet()
        event = next(e for e in packet["events"] if e["scenario_id"] == "legal-advice-abstain")
        event["source_refs"] = ["city:legal:g7"]
        receipt, _ = compile_receipt(packet)
        row = next(r for r in receipt["results"] if r["scenario_id"] == "legal-advice-abstain")
        self.assertIn("NONANSWER_HAS_SOURCE_CITATIONS", row["reasons"])

    def test_wrong_language_fails(self):
        packet = ready_packet()
        event = next(e for e in packet["events"] if e["scenario_id"] == "permit-es-chat")
        event["response_language"] = "en-US"
        receipt, _ = compile_receipt(packet)
        row = next(r for r in receipt["results"] if r["scenario_id"] == "permit-es-chat")
        self.assertIn("LANGUAGE_MISMATCH", row["reasons"])

    def test_wrong_route_fails(self):
        packet = ready_packet()
        event = next(e for e in packet["events"] if e["scenario_id"] == "emergency-escalation")
        event["route"] = "route:311-after-hours"
        receipt, _ = compile_receipt(packet)
        row = next(r for r in receipt["results"] if r["scenario_id"] == "emergency-escalation")
        self.assertIn("ROUTE_MISMATCH", row["reasons"])

    def test_missing_scenario_event_fails(self):
        packet = ready_packet()
        packet["events"] = [e for e in packet["events"] if e["scenario_id"] != "unknown-chat"]
        receipt, _ = compile_receipt(packet)
        row = next(r for r in receipt["results"] if r["scenario_id"] == "unknown-chat")
        self.assertEqual(row["reasons"], ["MISSING_CANDIDATE_EVENT"])

    def test_unknown_scenario_event_rejected(self):
        packet = ready_packet()
        rogue = copy.deepcopy(packet["events"][0])
        rogue["event_id"] = "evt:rogue"
        rogue["scenario_id"] = "rogue"
        packet["events"].append(rogue)
        with self.assertRaises(ValidationError):
            compile_receipt(packet)

    def test_duplicate_scenario_rejected(self):
        packet = ready_packet()
        packet["scenarios"].append(copy.deepcopy(packet["scenarios"][0]))
        with self.assertRaises(ValidationError):
            compile_receipt(packet)

    def test_bool_not_accepted_as_int(self):
        packet = ready_packet()
        packet["events"][0]["logical_effects"] = False
        with self.assertRaises(ValidationError):
            compile_receipt(packet)

    def test_external_authority_cannot_be_minted(self):
        packet = ready_packet()
        packet["policy"]["external_authority"]["provider_send"] = True
        with self.assertRaises(ValidationError):
            compile_receipt(packet)

    def test_unknown_top_level_field_rejected(self):
        packet = ready_packet()
        packet["buyer_ready"] = True
        with self.assertRaises(ValidationError):
            compile_receipt(packet)

    def test_input_order_is_semantically_canonical(self):
        a = ready_packet()
        b = ready_packet()
        b["scenarios"] = list(reversed(b["scenarios"]))
        b["events"] = list(reversed(b["events"]))
        self.assertEqual(compile_receipt(a), compile_receipt(b))

    def test_receipt_tamper_rejected(self):
        packet = ready_packet()
        receipt, report = compile_receipt(packet)
        receipt = copy.deepcopy(receipt)
        receipt["truth_ceiling"]["provider_send_authorized"] = True
        with self.assertRaises(VerificationError):
            verify_receipt(packet, receipt, report)

    def test_report_tamper_rejected(self):
        packet = ready_packet()
        receipt, report = compile_receipt(packet)
        with self.assertRaises(VerificationError):
            verify_receipt(packet, receipt, report + "tamper")

    def test_exact_receipt_verifies(self):
        packet = ready_packet()
        receipt, report = compile_receipt(packet)
        self.assertTrue(verify_receipt(packet, receipt, report))


class CliTests(unittest.TestCase):
    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"x":1,"x":2}', encoding="utf-8")
            with self.assertRaises(cli.FileBoundaryError):
                cli.load_json(path)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"x":NaN}', encoding="utf-8")
            with self.assertRaises(cli.FileBoundaryError):
                cli.load_json(path)

    def test_compile_verify_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.json"
            input_path.write_text(json.dumps(ready_packet(), sort_keys=True), encoding="utf-8")
            out = root / "out"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["compile", str(input_path), "--output-dir", str(out)]), 0)
                self.assertEqual(cli.main(["verify", str(input_path), str(out / "receipt.json"), str(out / "report.md")]), 0)
                self.assertEqual(cli.main(["compile", str(input_path), "--output-dir", str(out)]), 2)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "platform lacks O_NOFOLLOW")
    def test_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.json"
            target.write_text(json.dumps(ready_packet()), encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(target)
            with self.assertRaises(cli.FileBoundaryError):
                cli.load_json(link)


if __name__ == "__main__":
    unittest.main()

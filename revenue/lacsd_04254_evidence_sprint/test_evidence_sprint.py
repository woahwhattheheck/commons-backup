from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evidence_sprint import (
    EVENT_SCHEMA,
    MAX_JSON_BYTES,
    ValidationError,
    _load_strict_json,
    build_portfolio,
    candidate_build_sha256,
    canonical_json,
    compile_receipt,
    evaluate_candidate,
    reference_candidate,
    verify_receipt,
)


class EvidenceSprintTests(unittest.TestCase):
    def setUp(self):
        self.portfolio = build_portfolio()
        self.candidate = reference_candidate()

    def test_portfolio_is_deterministic_and_has_required_fault_classes(self):
        self.assertEqual(self.portfolio, build_portfolio())
        self.assertEqual(len(self.portfolio["scenarios"]), 10)
        self.assertEqual(
            {row["fault_class"] for row in self.portfolio["scenarios"]},
            {
                "normal_diurnal", "blockage_drift", "storm_inflow_infiltration",
                "sensor_dropout", "duplicate_packet_replay", "transport_interruption_recovery",
            },
        )
        self.assertEqual(len(self.portfolio["portfolio_sha256"]), 64)

    def test_reference_candidate_meets_every_binary_gate(self):
        result = evaluate_candidate(self.candidate)
        self.assertEqual(result["status"], "READY_FOR_BUYER_REVIEW")
        self.assertTrue(all(result["gates"].values()))
        self.assertEqual(result["candidate_build_sha256"], self.candidate["candidate_build_sha256"])
        self.assertEqual(result["artifact_sha256"], self.candidate["artifact_sha256"])
        self.assertFalse(result["authority"]["field_performance_claimed"])
        self.assertFalse(result["authority"]["production_control_authorized"])
        self.assertFalse(result["authority"]["payment_or_revenue_claimed"])

    def test_changed_model_fresh_compile_cannot_reattribute_old_events(self):
        changed = copy.deepcopy(self.candidate)
        changed["model_version"] = "v3"
        changed["candidate_build_sha256"] = candidate_build_sha256(
            candidate_id=changed["candidate_id"],
            model_id=changed["model_id"],
            model_version=changed["model_version"],
            artifact_sha256=changed["artifact_sha256"],
        )
        with self.assertRaisesRegex(ValidationError, "event.*build identity mismatch"):
            compile_receipt(changed)

    def test_changed_artifact_fresh_compile_cannot_reattribute_old_events(self):
        changed = copy.deepcopy(self.candidate)
        changed["artifact_sha256"] = "a" * 64
        changed["candidate_build_sha256"] = candidate_build_sha256(
            candidate_id=changed["candidate_id"],
            model_id=changed["model_id"],
            model_version=changed["model_version"],
            artifact_sha256=changed["artifact_sha256"],
        )
        with self.assertRaisesRegex(ValidationError, "event.*build identity mismatch"):
            compile_receipt(changed)

    def test_forged_top_level_build_digest_fails_closed(self):
        changed = copy.deepcopy(self.candidate)
        changed["candidate_build_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValidationError, "does not match exact"):
            evaluate_candidate(changed)

    def test_one_effect_id_cannot_be_transplanted_across_scenarios(self):
        changed = copy.deepcopy(self.candidate)
        for event in changed["events"]:
            if event["disposition"] == "ALERT":
                event["effect_id"] = "effect-shared-across-every-alert"
        with self.assertRaisesRegex(ValidationError, "reused across distinct"):
            evaluate_candidate(changed)

    def test_duplicate_effect_on_replayed_packet_holds(self):
        candidate = copy.deepcopy(self.candidate)
        base = next(e for e in candidate["events"] if e["scenario_id"] == "duplicate-replay-01")
        extra = dict(base)
        extra["event_id"] = "event-duplicate-replay-extra"
        extra["effect_id"] = "effect-duplicate-replay-extra"
        extra["observed_at_s"] += 1
        candidate["events"].append(extra)
        result = evaluate_candidate(candidate)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["duplicate_effect_count"], 1)

    def test_same_effect_idempotent_retry_in_same_binding_is_allowed(self):
        candidate = copy.deepcopy(self.candidate)
        base = next(e for e in candidate["events"] if e["scenario_id"] == "duplicate-replay-01")
        retry = dict(base)
        retry["event_id"] = "event-duplicate-replay-same-intent-retry"
        retry["observed_at_s"] = 481
        candidate["events"].append(retry)
        result = evaluate_candidate(candidate)
        self.assertEqual(result["status"], "READY_FOR_BUYER_REVIEW")
        row = next(r for r in result["scenario_results"] if r["scenario_id"] == "duplicate-replay-01")
        self.assertEqual(row["event_count"], 2)
        self.assertEqual(row["distinct_effect_count"], 1)

    def test_false_urgent_alert_holds(self):
        candidate = copy.deepcopy(self.candidate)
        event = next(e for e in candidate["events"] if e["scenario_id"] == "normal-diurnal-01")
        event["disposition"] = "ALERT"
        event["effect_id"] = "effect-false-alert"
        result = evaluate_candidate(candidate)
        self.assertEqual(result["status"], "HOLD")
        self.assertGreater(result["false_urgent_alert_rate"], 0.0)

    def test_late_alert_holds(self):
        candidate = copy.deepcopy(self.candidate)
        event = next(e for e in candidate["events"] if e["scenario_id"] == "blockage-drift-01")
        event["source_packet_id"] = "b1-4"
        event["observed_at_s"] = 720
        result = evaluate_candidate(candidate)
        self.assertEqual(result["status"], "HOLD")
        self.assertLess(result["timeliness_pass_rate"], 1.0)

    def test_fabricated_latency_timestamp_fails_closed(self):
        candidate = copy.deepcopy(self.candidate)
        event = next(e for e in candidate["events"] if e["scenario_id"] == "blockage-drift-01")
        event["observed_at_s"] = 481
        with self.assertRaises(ValidationError):
            evaluate_candidate(candidate)

    def test_alert_cannot_bind_transport_unavailable_occurrence(self):
        candidate = copy.deepcopy(self.candidate)
        event = next(e for e in candidate["events"] if e["scenario_id"] == "recovery-after-interruption-01")
        event["observed_at_s"] = 420
        event["source_packet_id"] = "x1-1"
        with self.assertRaises(ValidationError):
            evaluate_candidate(candidate)

    def test_no_data_must_bind_transport_unavailable_occurrence(self):
        candidate = copy.deepcopy(self.candidate)
        event = next(e for e in candidate["events"] if e["scenario_id"] == "sensor-dropout-01")
        event["source_packet_id"] = "d1-1"
        event["observed_at_s"] = 300
        with self.assertRaises(ValidationError):
            evaluate_candidate(candidate)

    def test_missing_scenario_holds(self):
        candidate = copy.deepcopy(self.candidate)
        candidate["events"] = [e for e in candidate["events"] if e["scenario_id"] != "sensor-dropout-02"]
        result = evaluate_candidate(candidate)
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["gates"]["all_scenarios_covered"])

    def test_lineage_transplant_holds_not_silently_passes(self):
        candidate = copy.deepcopy(self.candidate)
        candidate["events"][0]["input_sha256"] = candidate["events"][1]["input_sha256"]
        result = evaluate_candidate(candidate)
        self.assertEqual(result["status"], "HOLD")
        self.assertLess(result["lineage_pass_rate"], 1.0)

    def test_wrong_portfolio_hash_fails_closed(self):
        candidate = copy.deepcopy(self.candidate)
        candidate["portfolio_sha256"] = "0" * 64
        with self.assertRaises(ValidationError):
            evaluate_candidate(candidate)

    def test_unknown_candidate_field_fails_closed(self):
        candidate = copy.deepcopy(self.candidate)
        candidate["buyer_accepted"] = True
        with self.assertRaises(ValidationError):
            evaluate_candidate(candidate)

    def test_unknown_event_field_fails_closed(self):
        candidate = copy.deepcopy(self.candidate)
        candidate["events"][0]["dispatch_authorized"] = True
        with self.assertRaises(ValidationError):
            evaluate_candidate(candidate)

    def test_non_alert_cannot_carry_effect_id(self):
        candidate = copy.deepcopy(self.candidate)
        event = next(e for e in candidate["events"] if e["disposition"] == "CLEAR")
        event["effect_id"] = "work-order-pretend"
        with self.assertRaises(ValidationError):
            evaluate_candidate(candidate)

    def test_alert_requires_effect_id(self):
        candidate = copy.deepcopy(self.candidate)
        event = next(e for e in candidate["events"] if e["disposition"] == "ALERT")
        event["effect_id"] = None
        with self.assertRaises(ValidationError):
            evaluate_candidate(candidate)

    def test_unknown_packet_id_fails_closed(self):
        candidate = copy.deepcopy(self.candidate)
        candidate["events"][0]["source_packet_id"] = "not-in-stream"
        with self.assertRaises(ValidationError):
            evaluate_candidate(candidate)

    def test_duplicate_event_id_fails_closed(self):
        candidate = copy.deepcopy(self.candidate)
        candidate["events"].append(copy.deepcopy(candidate["events"][0]))
        with self.assertRaises(ValidationError):
            evaluate_candidate(candidate)

    def test_recovery_alert_before_transport_recovery_fails_closed(self):
        candidate = copy.deepcopy(self.candidate)
        event = next(e for e in candidate["events"] if e["scenario_id"] == "recovery-after-interruption-01")
        event["observed_at_s"] = 500
        with self.assertRaises(ValidationError):
            evaluate_candidate(candidate)

    def test_receipt_exactly_recomputes_and_detects_tamper(self):
        receipt = compile_receipt(self.candidate)
        self.assertEqual(verify_receipt(receipt, self.candidate), receipt)
        tampered = copy.deepcopy(receipt)
        tampered["evaluation"]["status"] = "HOLD"
        with self.assertRaises(ValidationError):
            verify_receipt(tampered, self.candidate)

    def test_receipt_cannot_be_transplanted_to_changed_candidate(self):
        receipt = compile_receipt(self.candidate)
        changed = copy.deepcopy(self.candidate)
        changed["candidate_id"] = "other-candidate"
        with self.assertRaises(ValidationError):
            verify_receipt(receipt, changed)

    def test_canonical_json_is_order_independent_for_objects(self):
        self.assertEqual(canonical_json({"b": 2, "a": 1}), canonical_json({"a": 1, "b": 2}))

    def test_claim_test_result_rows_are_machine_readable(self):
        claims = evaluate_candidate(self.candidate)["claims"]
        self.assertEqual(len(claims), 8)
        self.assertEqual(len({row["claim_id"] for row in claims}), 8)
        self.assertTrue(all(set(row) == {"claim_id", "test", "passed", "evidence"} for row in claims))
        self.assertTrue(all(row["passed"] for row in claims))

    def test_conflicting_retransmission_disposition_holds(self):
        candidate = copy.deepcopy(self.candidate)
        base = next(e for e in candidate["events"] if e["scenario_id"] == "duplicate-replay-01")
        conflict = dict(base)
        conflict["event_id"] = "event-duplicate-replay-conflict"
        conflict["observed_at_s"] = 481
        conflict["disposition"] = "CLEAR"
        conflict["effect_id"] = None
        candidate["events"].append(conflict)
        self.assertEqual(evaluate_candidate(candidate)["status"], "HOLD")

    def test_out_of_order_event_input_canonicalizes_to_same_receipt(self):
        receipt = compile_receipt(self.candidate)
        reversed_candidate = copy.deepcopy(self.candidate)
        reversed_candidate["events"] = list(reversed(reversed_candidate["events"]))
        self.assertEqual(receipt, compile_receipt(reversed_candidate))

    def test_candidate_events_use_expected_schema_and_build(self):
        self.assertTrue(self.candidate["events"])
        self.assertTrue(all(event["schema"] == EVENT_SCHEMA for event in self.candidate["events"]))
        self.assertTrue(
            all(event["candidate_build_sha256"] == self.candidate["candidate_build_sha256"] for event in self.candidate["events"])
        )


class StrictIngressTests(unittest.TestCase):
    def test_stable_regular_json_loads(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "stable.json"
            path.write_text('{"ok":true,"rows":[1,2,3]}', encoding="utf-8")
            self.assertEqual(_load_strict_json(path), {"ok": True, "rows": [1, 2, 3]})

    def test_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "dupe.json"
            path.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "duplicate JSON key"):
                _load_strict_json(path)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "nan.json"
            path.write_text('{"value":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "non-finite"):
                _load_strict_json(path)

    def test_invalid_utf8_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "invalid.json"
            path.write_bytes(b'{"x":"\xff"}')
            with self.assertRaisesRegex(ValidationError, "strict UTF-8"):
                _load_strict_json(path)

    def test_directory_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValidationError, "ordinary regular file"):
                _load_strict_json(Path(td))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO unavailable")
    def test_fifo_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fifo"
            os.mkfifo(path)
            with self.assertRaisesRegex(ValidationError, "ordinary regular file"):
                _load_strict_json(path)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_final_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValidationError, "ordinary regular file"):
                _load_strict_json(link)

    @unittest.skipUnless(Path("/dev/null").exists(), "device unavailable")
    def test_device_rejected(self):
        with self.assertRaisesRegex(ValidationError, "ordinary regular file"):
            _load_strict_json(Path("/dev/null"))

    def test_oversize_file_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "large.json"
            with path.open("wb") as f:
                f.truncate(MAX_JSON_BYTES + 1)
            with patch("evidence_sprint.os.open", wraps=os.open) as opened:
                with self.assertRaisesRegex(ValidationError, "exceeds"):
                    _load_strict_json(path)
                opened.assert_not_called()

    def test_growth_during_read_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "grow.json"
            path.write_bytes(b'{"x":"' + b"a" * 100000 + b'"}')
            real_read = os.read
            mutated = False

            def read_then_grow(fd: int, n: int) -> bytes:
                nonlocal mutated
                chunk = real_read(fd, n)
                if chunk and not mutated:
                    mutated = True
                    with path.open("ab") as f:
                        f.write(b" ")
                return chunk

            with patch("evidence_sprint.os.read", side_effect=read_then_grow):
                with self.assertRaisesRegex(ValidationError, "grew|generation changed"):
                    _load_strict_json(path)

    def test_path_replacement_during_read_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "replace.json"
            old = root / "old.json"
            path.write_bytes(b'{"x":"' + b"a" * 100000 + b'"}')
            real_read = os.read
            mutated = False

            def read_then_replace(fd: int, n: int) -> bytes:
                nonlocal mutated
                chunk = real_read(fd, n)
                if chunk and not mutated:
                    mutated = True
                    path.rename(old)
                    path.write_text('{"replacement":true}', encoding="utf-8")
                return chunk

            with patch("evidence_sprint.os.read", side_effect=read_then_replace):
                with self.assertRaisesRegex(ValidationError, "pathname no longer names|descriptor generation changed"):
                    _load_strict_json(path)


if __name__ == "__main__":
    unittest.main()

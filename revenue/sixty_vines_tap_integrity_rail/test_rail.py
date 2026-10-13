#!/usr/bin/env python3
import copy
import importlib.util
import json
import random
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("tap_integrity_rail", HERE / "rail.py")
rail = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = rail
assert SPEC.loader is not None
SPEC.loader.exec_module(rail)


def minimal_fixture():
    return [
        {"event_id":"E1","seq":1,"type":"KEG_RECEIVED","keg_id":"K1","lot_id":"LOT1","wine_id":"W1","sku":"S1","volume_ml":1000},
        {"event_id":"E2","seq":2,"type":"TAP_ASSIGN","tap_id":"T1","line_id":"L1","keg_id":"K1"},
        {"event_id":"E3","seq":3,"type":"LINE_CLEAN","line_id":"L1","valid_through_seq":100},
        {"event_id":"E4","seq":4,"type":"TAP_STATUS","tap_id":"T1","available":True,"temperature_ok":True},
    ]


def pour(seq=5, effect_id="FX1", event_id="E5", **overrides):
    row = {
        "event_id": event_id, "seq": seq, "type":"POUR",
        "effect_id":effect_id, "effect_status":"COMMITTED",
        "tap_id":"T1","line_id":"L1","keg_id":"K1","lot_id":"LOT1",
        "wine_id":"W1","sku":"S1","pour_ml":150,
        "table_id":"TABLE1","check_id":"CHECK1","amount_cents":1800,
    }
    row.update(overrides)
    return row


class RailTests(unittest.TestCase):
    def test_20000_event_acceptance(self):
        summary = rail.acceptance_summary(20_000, 60)
        self.assertTrue(summary["acceptance_pass"])
        self.assertTrue(summary["receipt_valid"])
        self.assertEqual(summary["event_count"], 20_000)
        self.assertEqual(summary["tap_count"], 60)
        self.assertEqual(summary["coverage"]["unique_taps_with_committed_effects"], 60)
        self.assertGreaterEqual(summary["coverage"]["effect_retries_suppressed"], 1)
        self.assertGreaterEqual(summary["coverage"]["exact_input_retries_suppressed"], 1)
        self.assertEqual(
            set(summary["hold_reasons"]),
            {"cleaning_overdue","sku_mismatch","tap_unavailable","temperature_hold"},
        )
        self.assertEqual(summary["reconciliation"]["unknown_effects"], 1)

    def test_order_invariant_replay(self):
        events = rail.build_synthetic_fixture(1000, 10)
        result1 = rail.reconcile(events, expected_taps=10)
        shuffled = copy.deepcopy(events)
        random.Random(913).shuffle(shuffled)
        result2 = rail.reconcile(shuffled, expected_taps=10)
        self.assertEqual(result1["manifest_sha256"], result2["manifest_sha256"])
        self.assertEqual(result1["reconciliation"], result2["reconciliation"])

    def test_pii_fields_are_rejected(self):
        events = minimal_fixture()
        row = pour()
        row["guest_name"] = "synthetic-but-forbidden"
        events.append(row)
        with self.assertRaisesRegex(rail.IntegrityError, "PII"):
            rail.reconcile(events)

    def test_event_id_collision_is_rejected(self):
        events = minimal_fixture()
        events.append(pour())
        changed = pour()
        changed["amount_cents"] = 1700
        events.append(changed)
        with self.assertRaisesRegex(rail.IntegrityError, "event_id collision"):
            rail.reconcile(events)

    def test_sequence_collision_is_rejected(self):
        events = minimal_fixture()
        events.append(pour())
        other = pour(effect_id="FX2", event_id="E6", amount_cents=1700)
        events.append(other)
        with self.assertRaisesRegex(rail.IntegrityError, "sequence collision"):
            rail.reconcile(events)

    def test_effect_retry_is_suppressed_without_double_inventory(self):
        events = minimal_fixture()
        first = pour()
        retry = copy.deepcopy(first)
        retry["event_id"] = "E6"
        retry["seq"] = 6
        events.extend([first, retry])
        result = rail.reconcile(events)
        self.assertEqual(result["reconciliation"]["inventory_used_ml"], 150)
        self.assertEqual(result["reconciliation"]["committed_pours"], 1)
        self.assertEqual(result["coverage"]["effect_retries_suppressed"], 1)

    def test_effect_id_conflict_is_rejected(self):
        events = minimal_fixture()
        events.append(pour())
        events.append(pour(seq=6, event_id="E6", amount_cents=1900))
        with self.assertRaisesRegex(rail.IntegrityError, "effect_id collision"):
            rail.reconcile(events)

    def test_unknown_effect_is_visible_and_not_applied(self):
        events = minimal_fixture()
        events.append(pour(effect_status="UNKNOWN_EFFECT"))
        result = rail.reconcile(events)
        self.assertEqual(result["reconciliation"]["unknown_effects"], 1)
        self.assertEqual(result["reconciliation"]["inventory_used_ml"], 0)
        self.assertEqual(result["reconciliation"]["monetary_gross_cents"], 0)
        self.assertEqual(result["unknown_effects"][0]["effect_id"], "FX1")

    def test_misroute_is_held_before_effect(self):
        events = minimal_fixture()
        events.append(pour(sku="WRONG"))
        result = rail.reconcile(events)
        self.assertEqual(result["reconciliation"]["inventory_used_ml"], 0)
        self.assertIn("sku_mismatch", result["holds"][0]["reasons"])

    def test_cleaning_overdue_is_held(self):
        events = minimal_fixture()
        events[2]["valid_through_seq"] = 4
        events.append(pour())
        result = rail.reconcile(events)
        self.assertIn("cleaning_overdue", result["holds"][0]["reasons"])

    def test_unavailable_and_temperature_each_hold(self):
        for status_field in ("available", "temperature_ok"):
            events = minimal_fixture()
            events[3][status_field] = False
            events.append(pour())
            result = rail.reconcile(events)
            expected = "tap_unavailable" if status_field == "available" else "temperature_hold"
            self.assertIn(expected, result["holds"][0]["reasons"])

    def test_inventory_overage_is_held(self):
        events = minimal_fixture()
        events[0]["volume_ml"] = 100
        events.append(pour(pour_ml=150))
        result = rail.reconcile(events)
        self.assertIn("insufficient_keg_volume", result["holds"][0]["reasons"])
        self.assertEqual(result["reconciliation"]["inventory_used_ml"], 0)

    def test_void_and_refund_cannot_reverse_more_than_pour(self):
        events = minimal_fixture()
        events.append(pour(amount_cents=1000))
        events.append({
            "event_id":"E6","seq":6,"type":"VOID","effect_id":"V1","effect_status":"COMMITTED",
            "target_effect_id":"FX1","check_id":"CHECK1","amount_cents":700,
        })
        events.append({
            "event_id":"E7","seq":7,"type":"REFUND","effect_id":"R1","effect_status":"COMMITTED",
            "target_effect_id":"FX1","check_id":"CHECK1","amount_cents":400,
        })
        result = rail.reconcile(events)
        self.assertEqual(result["reconciliation"]["reversal_cents"], 700)
        self.assertIn("reversal_overage", result["holds"][0]["reasons"])

    def test_reversal_check_mismatch_is_held(self):
        events = minimal_fixture()
        events.append(pour())
        events.append({
            "event_id":"E6","seq":6,"type":"VOID","effect_id":"V1","effect_status":"COMMITTED",
            "target_effect_id":"FX1","check_id":"OTHER","amount_cents":100,
        })
        result = rail.reconcile(events)
        self.assertIn("check_mismatch", result["holds"][0]["reasons"])

    def test_line_assignment_collision_is_held(self):
        events = minimal_fixture()
        events.append({"event_id":"E5","seq":5,"type":"KEG_RECEIVED","keg_id":"K2","lot_id":"LOT2","wine_id":"W2","sku":"S2","volume_ml":1000})
        events.append({"event_id":"E6","seq":6,"type":"TAP_ASSIGN","tap_id":"T2","line_id":"L1","keg_id":"K2"})
        result = rail.reconcile(events)
        self.assertIn("line_already_assigned", result["holds"][0]["reasons"])

    def test_duplicate_keg_receipt_requires_retry_semantics(self):
        events = minimal_fixture()
        events.append({"event_id":"E5","seq":5,"type":"KEG_RECEIVED","keg_id":"K1","lot_id":"LOT1","wine_id":"W1","sku":"S1","volume_ml":1000})
        with self.assertRaisesRegex(rail.IntegrityError, "duplicate keg receipt"):
            rail.reconcile(events)

    def test_float_money_is_rejected(self):
        events = minimal_fixture()
        events.append(pour(amount_cents=18.0))
        with self.assertRaisesRegex(rail.IntegrityError, "amount_cents must be an integer"):
            rail.reconcile(events)

    def test_unexpected_fields_are_rejected(self):
        events = minimal_fixture()
        row = pour()
        row["price_override"] = 1
        events.append(row)
        with self.assertRaisesRegex(rail.IntegrityError, "unexpected fields"):
            rail.reconcile(events)

    def test_receipt_tamper_is_detected(self):
        events = minimal_fixture() + [pour()]
        result = rail.reconcile(events)
        receipt = rail.make_receipt(result)
        self.assertTrue(rail.verify_receipt(receipt, result))
        tampered = copy.deepcopy(result)
        tampered["reconciliation"]["monetary_net_cents"] += 1
        self.assertFalse(rail.verify_receipt(receipt, tampered))
        receipt2 = copy.deepcopy(receipt)
        receipt2["result_sha256"] = "0" * 64
        self.assertFalse(rail.verify_receipt(receipt2, result))

    def test_fixture_has_exact_input_rows(self):
        fixture = rail.build_synthetic_fixture(1234, 12)
        self.assertEqual(len(fixture), 1234)
        result = rail.reconcile(fixture, expected_taps=12)
        self.assertTrue(result["integrity_pass"])
        self.assertEqual(result["coverage"]["unique_taps_with_committed_effects"], 12)

    def test_cli_require_pass(self):
        proc = subprocess.run(
            [sys.executable, str(HERE/"rail.py"), "acceptance", "--events", "1000", "--taps", "10", "--require-pass"],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertTrue(payload["acceptance_pass"])
        self.assertTrue(payload["receipt_valid"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

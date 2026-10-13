import copy
import json
import random
import tempfile
import unittest
from pathlib import Path

import rail


def one_tap_config(cleaning_max_age=20):
    return {
        "cleaning_max_age": cleaning_max_age,
        "taps": {"TAP-01": {"line_id": "LINE-01", "allowed_sku": "WINE-01"}},
    }


def setup_events():
    return [
        {
            "event_id": "recv",
            "seq": 0,
            "type": "RECEIVE_KEG",
            "keg_id": "KEG-1",
            "lot_id": "LOT-1",
            "sku": "WINE-01",
            "initial_ml": 1000,
        },
        {"event_id": "clean", "seq": 1, "type": "CLEAN_LINE", "line_id": "LINE-01"},
        {
            "event_id": "status",
            "seq": 2,
            "type": "SET_LINE_STATUS",
            "line_id": "LINE-01",
            "status": "AVAILABLE",
        },
        {
            "event_id": "assign",
            "seq": 3,
            "type": "ASSIGN_KEG",
            "tap_id": "TAP-01",
            "line_id": "LINE-01",
            "keg_id": "KEG-1",
        },
    ]


def pour(seq=4, event_id="pour-event", effect_id="fx-1", pour_id="pour-1", **updates):
    event = {
        "event_id": event_id,
        "seq": seq,
        "type": "POUR",
        "effect_id": effect_id,
        "pour_id": pour_id,
        "tap_id": "TAP-01",
        "line_id": "LINE-01",
        "keg_id": "KEG-1",
        "lot_id": "LOT-1",
        "sku": "WINE-01",
        "amount_ml": 150,
        "price_cents": 1800,
        "check_id": "CHECK-1",
        "table_id": "TABLE-1",
    }
    event.update(updates)
    return event


class TapIntegrityRailTests(unittest.TestCase):
    def test_valid_pour_accounts_inventory_and_money(self):
        receipt = rail.reconcile(one_tap_config(), setup_events() + [pour()])
        self.assertTrue(rail.verify_receipt(receipt))
        self.assertEqual(receipt["summary"]["holds"], 0)
        self.assertEqual(receipt["summary"]["inventory_used_ml"], 150)
        self.assertEqual(receipt["summary"]["gross_cents"], 1800)
        self.assertEqual(receipt["summary"]["net_cents"], 1800)
        self.assertEqual(receipt["summary"]["remaining_ml"], 850)

    def test_exact_event_retry_is_deduplicated(self):
        p = pour()
        receipt = rail.reconcile(one_tap_config(), setup_events() + [p, copy.deepcopy(p)])
        self.assertEqual(receipt["summary"]["unique_events"], 5)
        self.assertEqual(receipt["summary"]["inventory_used_ml"], 150)
        self.assertEqual(receipt["summary"]["gross_cents"], 1800)

    def test_conflicting_event_id_fails_closed(self):
        a = pour()
        b = copy.deepcopy(a)
        b["amount_ml"] = 151
        with self.assertRaisesRegex(rail.RailError, "reused with different bytes"):
            rail.reconcile(one_tap_config(), setup_events() + [a, b])

    def test_reused_effect_id_is_held_before_effect(self):
        a = pour()
        b = pour(
            seq=5,
            event_id="pour-event-2",
            effect_id="fx-1",
            pour_id="pour-2",
            check_id="CHECK-2",
        )
        receipt = rail.reconcile(one_tap_config(), setup_events() + [a, b])
        self.assertEqual(receipt["summary"]["inventory_used_ml"], 150)
        self.assertEqual(receipt["summary"]["gross_cents"], 1800)
        self.assertEqual(receipt["holds"][0]["code"], "DUPLICATE_EFFECT_ID")

    def test_wrong_line_is_held_before_effect(self):
        cfg = one_tap_config()
        bad = pour(line_id="LINE-99")
        receipt = rail.reconcile(cfg, setup_events() + [bad])
        self.assertEqual(receipt["summary"]["applied_effects"], 0)
        self.assertEqual(receipt["holds"][0]["code"], "WRONG_LINE")

    def test_unknown_lot_is_held_before_effect(self):
        bad = pour(lot_id="LOT-X")
        receipt = rail.reconcile(one_tap_config(), setup_events() + [bad])
        self.assertEqual(receipt["summary"]["applied_effects"], 0)
        self.assertEqual(receipt["holds"][0]["code"], "LOT_MISMATCH")

    def test_unavailable_line_is_held_before_effect(self):
        events = setup_events()
        events[2]["status"] = "HOLD"
        receipt = rail.reconcile(one_tap_config(), events + [pour()])
        self.assertEqual(receipt["summary"]["applied_effects"], 0)
        self.assertEqual(receipt["holds"][0]["code"], "LINE_UNAVAILABLE")

    def test_overdue_cleaning_is_held_before_effect(self):
        receipt = rail.reconcile(
            one_tap_config(cleaning_max_age=2),
            setup_events() + [pour(seq=5)],
        )
        self.assertEqual(receipt["summary"]["applied_effects"], 0)
        self.assertEqual(receipt["holds"][0]["code"], "CLEANING_OVERDUE")

    def test_insufficient_keg_volume_is_held(self):
        bad = pour(amount_ml=1001)
        receipt = rail.reconcile(one_tap_config(), setup_events() + [bad])
        self.assertEqual(receipt["summary"]["applied_effects"], 0)
        self.assertEqual(receipt["holds"][0]["code"], "INSUFFICIENT_KEG_VOLUME")

    def test_waste_is_inventory_only(self):
        waste = pour(seq=4, type="WASTE", amount_ml=25, price_cents=999)
        receipt = rail.reconcile(one_tap_config(), setup_events() + [waste])
        self.assertEqual(receipt["summary"]["inventory_waste_ml"], 25)
        self.assertEqual(receipt["summary"]["inventory_used_ml"], 0)
        self.assertEqual(receipt["summary"]["gross_cents"], 0)
        self.assertEqual(receipt["summary"]["remaining_ml"], 975)

    def test_partial_refund_reconciles_net_money_without_restoring_inventory(self):
        refund = {
            "event_id": "refund",
            "seq": 5,
            "type": "REFUND",
            "effect_id": "fx-refund",
            "pour_id": "pour-1",
            "amount_cents": 500,
        }
        receipt = rail.reconcile(one_tap_config(), setup_events() + [pour(), refund])
        self.assertEqual(receipt["summary"]["gross_cents"], 1800)
        self.assertEqual(receipt["summary"]["refund_cents"], 500)
        self.assertEqual(receipt["summary"]["net_cents"], 1300)
        self.assertEqual(receipt["summary"]["remaining_ml"], 850)

    def test_refund_over_remaining_is_held(self):
        refund = {
            "event_id": "refund",
            "seq": 5,
            "type": "REFUND",
            "effect_id": "fx-refund",
            "pour_id": "pour-1",
            "amount_cents": 1801,
        }
        receipt = rail.reconcile(one_tap_config(), setup_events() + [pour(), refund])
        self.assertEqual(receipt["summary"]["net_cents"], 1800)
        self.assertEqual(receipt["holds"][0]["code"], "REFUND_EXCEEDS_REMAINING")

    def test_void_reverses_money_not_inventory(self):
        void = {
            "event_id": "void",
            "seq": 5,
            "type": "VOID",
            "effect_id": "fx-void",
            "pour_id": "pour-1",
        }
        receipt = rail.reconcile(one_tap_config(), setup_events() + [pour(), void])
        self.assertEqual(receipt["summary"]["void_cents"], 1800)
        self.assertEqual(receipt["summary"]["net_cents"], 0)
        self.assertEqual(receipt["summary"]["remaining_ml"], 850)

    def test_void_after_refund_is_held(self):
        refund = {
            "event_id": "refund",
            "seq": 5,
            "type": "REFUND",
            "effect_id": "fx-refund",
            "pour_id": "pour-1",
            "amount_cents": 500,
        }
        void = {
            "event_id": "void",
            "seq": 6,
            "type": "VOID",
            "effect_id": "fx-void",
            "pour_id": "pour-1",
        }
        receipt = rail.reconcile(one_tap_config(), setup_events() + [pour(), refund, void])
        self.assertEqual(receipt["summary"]["net_cents"], 1300)
        self.assertEqual(receipt["holds"][0]["code"], "VOID_CONFLICT")

    def test_unknown_effect_applies_only_after_explicit_reconciliation(self):
        unknown = pour(type="POUR_UNKNOWN")
        resolve = {
            "event_id": "resolve",
            "seq": 5,
            "type": "RESOLVE_POUR",
            "effect_id": "fx-1",
            "resolution": "APPLIED",
        }
        unresolved = rail.reconcile(one_tap_config(), setup_events() + [unknown])
        self.assertEqual(unresolved["summary"]["gross_cents"], 0)
        self.assertEqual(unresolved["summary"]["unresolved_unknown_effects"], 1)
        receipt = rail.reconcile(one_tap_config(), setup_events() + [unknown, resolve])
        self.assertEqual(receipt["summary"]["unresolved_unknown_effects"], 0)
        self.assertEqual(receipt["summary"]["gross_cents"], 1800)
        self.assertEqual(receipt["summary"]["inventory_used_ml"], 150)

    def test_unknown_effect_not_applied_keeps_effect_totals_zero(self):
        unknown = pour(type="POUR_UNKNOWN")
        resolve = {
            "event_id": "resolve",
            "seq": 5,
            "type": "RESOLVE_POUR",
            "effect_id": "fx-1",
            "resolution": "NOT_APPLIED",
        }
        receipt = rail.reconcile(one_tap_config(), setup_events() + [unknown, resolve])
        self.assertEqual(receipt["summary"]["applied_effects"], 0)
        self.assertEqual(receipt["summary"]["gross_cents"], 0)
        self.assertEqual(receipt["summary"]["inventory_used_ml"], 0)

    def test_unknown_effect_blocks_same_effect_id_until_resolved(self):
        unknown = pour(type="POUR_UNKNOWN")
        retry = pour(
            seq=5, event_id="retry", effect_id="fx-1", pour_id="pour-retry"
        )
        receipt = rail.reconcile(one_tap_config(), setup_events() + [unknown, retry])
        self.assertEqual(receipt["summary"]["gross_cents"], 0)
        self.assertEqual(receipt["holds"][0]["code"], "UNKNOWN_EFFECT_BLOCK")

    def test_order_of_input_records_does_not_change_receipt(self):
        events = setup_events() + [pour()]
        baseline = rail.reconcile(one_tap_config(), events)
        shuffled = list(events)
        random.Random(42).shuffle(shuffled)
        replay = rail.reconcile(one_tap_config(), shuffled)
        self.assertEqual(baseline["receipt_sha256"], replay["receipt_sha256"])
        self.assertEqual(baseline["state_sha256"], replay["state_sha256"])

    def test_same_sequence_for_different_events_is_rejected(self):
        bad = pour(seq=3)
        with self.assertRaisesRegex(rail.RailError, "seq 3 is shared"):
            rail.reconcile(one_tap_config(), setup_events() + [bad])

    def test_bad_line_status_is_rejected(self):
        events = setup_events()
        events[2]["status"] = "MAGIC"
        with self.assertRaisesRegex(rail.RailError, "invalid line status"):
            rail.reconcile(one_tap_config(), events)

    def test_duplicate_line_config_is_rejected(self):
        cfg = {
            "cleaning_max_age": 10,
            "taps": {
                "TAP-1": {"line_id": "LINE-1", "allowed_sku": "A"},
                "TAP-2": {"line_id": "LINE-1", "allowed_sku": "B"},
            },
        }
        with self.assertRaisesRegex(rail.RailError, "assigned to multiple taps"):
            rail.reconcile(cfg, [])

    def test_acceptance_generator_exactly_20000_events_and_60_taps(self):
        config, events = rail.generate_acceptance_events(20_000, 60)
        self.assertEqual(len(events), 20_000)
        receipt = rail.reconcile(config, events)
        self.assertEqual(receipt["summary"]["tap_count"], 60)
        self.assertEqual(receipt["summary"]["taps_with_pours"], 60)
        self.assertEqual(receipt["summary"]["holds"], 0)
        self.assertEqual(receipt["summary"]["unresolved_unknown_effects"], 0)
        self.assertTrue(all(v > 0 for v in receipt["tap_coverage"].values()))

    def test_acceptance_generator_is_byte_deterministic(self):
        a_cfg, a_events = rail.generate_acceptance_events(2_000, 60)
        b_cfg, b_events = rail.generate_acceptance_events(2_000, 60)
        self.assertEqual(
            json.dumps([a_cfg, a_events], sort_keys=True, separators=(",", ":")),
            json.dumps([b_cfg, b_events], sort_keys=True, separators=(",", ":")),
        )
        self.assertEqual(
            rail.reconcile(a_cfg, a_events)["receipt_sha256"],
            rail.reconcile(b_cfg, b_events)["receipt_sha256"],
        )

    def test_receipt_tampering_is_detected(self):
        receipt = rail.reconcile(one_tap_config(), setup_events() + [pour()])
        self.assertTrue(rail.verify_receipt(receipt))
        receipt["summary"]["net_cents"] += 1
        self.assertFalse(rail.verify_receipt(receipt))

    def test_cli_receipt_round_trip_verifies_offline(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "receipt.json"
            rc = rail._main(
                ["acceptance", "--events", "1000", "--taps", "60", "--receipt", str(path), "--require-pass"]
            )
            self.assertEqual(rc, 0)
            self.assertTrue(path.exists())
            self.assertEqual(rail._main(["verify-receipt", str(path)]), 0)

    def test_negative_amount_is_rejected(self):
        with self.assertRaisesRegex(rail.RailError, "amount_ml must be an integer"):
            rail.reconcile(one_tap_config(), setup_events() + [pour(amount_ml=-1)])

    def test_boolean_amount_is_rejected(self):
        with self.assertRaisesRegex(rail.RailError, "amount_ml must be an integer"):
            rail.reconcile(one_tap_config(), setup_events() + [pour(amount_ml=True)])


if __name__ == "__main__":
    unittest.main()

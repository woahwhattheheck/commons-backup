import copy
import unittest

import rail


def one_tap_config():
    return {
        "cleaning_max_age": 20,
        "taps": {"TAP-01": {"line_id": "LINE-01", "allowed_sku": "WINE-01"}},
    }


def two_tap_config():
    return {
        "cleaning_max_age": 20,
        "taps": {
            "TAP-01": {"line_id": "LINE-01", "allowed_sku": "WINE-01"},
            "TAP-02": {"line_id": "LINE-02", "allowed_sku": "WINE-02"},
        },
    }


def setup_tap(tap_number, seq):
    suffix = f"{tap_number:02d}"
    return [
        {
            "event_id": f"recv-{suffix}",
            "seq": seq,
            "type": "RECEIVE_KEG",
            "keg_id": f"KEG-{suffix}",
            "lot_id": f"LOT-{suffix}",
            "sku": f"WINE-{suffix}",
            "initial_ml": 1000,
        },
        {
            "event_id": f"clean-{suffix}",
            "seq": seq + 1,
            "type": "CLEAN_LINE",
            "line_id": f"LINE-{suffix}",
        },
        {
            "event_id": f"status-{suffix}",
            "seq": seq + 2,
            "type": "SET_LINE_STATUS",
            "line_id": f"LINE-{suffix}",
            "status": "AVAILABLE",
        },
        {
            "event_id": f"assign-{suffix}",
            "seq": seq + 3,
            "type": "ASSIGN_KEG",
            "tap_id": f"TAP-{suffix}",
            "line_id": f"LINE-{suffix}",
            "keg_id": f"KEG-{suffix}",
        },
    ]


def pour_event(seq, *, tap_number=1, amount_ml=200, unknown=False, suffix="fresh"):
    tap = f"{tap_number:02d}"
    return {
        "event_id": f"{suffix}-event",
        "seq": seq,
        "type": "POUR_UNKNOWN" if unknown else "POUR",
        "effect_id": f"{suffix}-effect",
        "pour_id": f"{suffix}-pour",
        "tap_id": f"TAP-{tap}",
        "line_id": f"LINE-{tap}",
        "keg_id": f"KEG-{tap}",
        "lot_id": f"LOT-{tap}",
        "sku": f"WINE-{tap}",
        "amount_ml": amount_ml,
        "price_cents": 1000,
        "check_id": f"CHECK-{suffix}",
        "table_id": f"TABLE-{suffix}",
    }


def resolution(seq, resolution_value):
    return {
        "event_id": f"resolve-{seq}",
        "seq": seq,
        "type": "RESOLVE_POUR",
        "effect_id": "unknown-effect",
        "resolution": resolution_value,
    }


class RailHardeningTests(unittest.TestCase):
    def test_unknown_resource_blocks_same_resource_until_applied_resolution(self):
        events = setup_tap(1, 0)
        events.extend(
            [
                pour_event(4, amount_ml=900, unknown=True, suffix="unknown"),
                pour_event(5, amount_ml=200, suffix="fresh"),
                resolution(6, "APPLIED"),
            ]
        )
        receipt = rail.reconcile(one_tap_config(), events)
        self.assertEqual(receipt["summary"]["remaining_ml"], 100)
        self.assertEqual(receipt["summary"]["unresolved_unknown_effects"], 0)
        self.assertEqual(
            [hold["code"] for hold in receipt["holds"]], ["UNKNOWN_RESOURCE_BLOCK"]
        )
        self.assertIn("unknown-effect", receipt["holds"][0]["detail"])

    def test_not_applied_resolution_releases_same_resource(self):
        events = setup_tap(1, 0)
        events.extend(
            [
                pour_event(4, amount_ml=900, unknown=True, suffix="unknown"),
                resolution(5, "NOT_APPLIED"),
                pour_event(6, amount_ml=200, suffix="fresh"),
            ]
        )
        receipt = rail.reconcile(one_tap_config(), events)
        self.assertEqual(receipt["summary"]["remaining_ml"], 800)
        self.assertEqual(receipt["summary"]["holds"], 0)
        self.assertEqual(receipt["summary"]["unresolved_unknown_effects"], 0)

    def test_unrelated_tap_proceeds_while_other_resource_is_unknown(self):
        events = setup_tap(1, 0) + setup_tap(2, 4)
        events.extend(
            [
                pour_event(8, amount_ml=900, unknown=True, suffix="unknown"),
                pour_event(9, tap_number=2, amount_ml=200, suffix="other"),
            ]
        )
        receipt = rail.reconcile(two_tap_config(), events)
        self.assertEqual(receipt["summary"]["holds"], 0)
        self.assertEqual(receipt["summary"]["remaining_ml"], 1800)
        self.assertEqual(receipt["tap_coverage"], {"TAP-01": 0, "TAP-02": 1})
        self.assertEqual(receipt["unresolved_effect_ids"], ["unknown-effect"])

    def test_hash_only_self_hash_is_rejected(self):
        receipt = {"receipt_sha256": rail.receipt_digest({})}
        self.assertFalse(rail.verify_receipt(receipt))

    def test_rehashed_receipt_missing_state_digest_is_rejected(self):
        receipt = rail.reconcile(one_tap_config(), setup_tap(1, 0))
        mutated = copy.deepcopy(receipt)
        mutated.pop("state_sha256")
        mutated["receipt_sha256"] = rail.receipt_digest(mutated)
        self.assertFalse(rail.verify_receipt(mutated))

    def test_rehashed_summary_missing_remaining_ml_is_rejected(self):
        receipt = rail.reconcile(one_tap_config(), setup_tap(1, 0))
        mutated = copy.deepcopy(receipt)
        mutated["summary"].pop("remaining_ml")
        mutated["receipt_sha256"] = rail.receipt_digest(mutated)
        self.assertFalse(rail.verify_receipt(mutated))


if __name__ == "__main__":
    unittest.main()

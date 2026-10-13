from __future__ import annotations

import copy
import math
import unittest

import raw_phase_contract as phase


def action(rows, **extra):
    out = {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(rows)}
    out.update(copy.deepcopy(extra))
    return out


class RawPhaseContractTests(unittest.TestCase):
    def test_delay_wheat_one_empty_slot(self):
        before = action([["BUY_PRODUCT", "WHEAT", 3], [], ["HIRE"]])
        after = action([[], ["BUY_PRODUCT", "WHEAT", 3], ["HIRE"]])
        cert = phase.certify_adjacent_buy_phase(before, after)
        self.assertTrue(cert.admitted)
        self.assertEqual(cert.direction, "delay_one_slot")
        self.assertEqual((cert.item, cert.quantity), ("WHEAT", 3))
        self.assertEqual((cert.source_slot, cert.target_slot), (0, 1))
        self.assertTrue(cert.conditional_only)
        self.assertFalse(cert.activation_authority)

    def test_advance_fertilizer_across_none(self):
        before = action([None, ["BUY_PRODUCT", "FERTILIZER", 2]])
        after = action([["BUY_PRODUCT", "FERTILIZER", 2], None])
        cert = phase.certify_adjacent_buy_phase(before, after)
        self.assertTrue(cert.admitted)
        self.assertEqual(cert.direction, "advance_one_slot")

    def test_pass_is_literal_noop(self):
        before = action([["PASS"], ["BUY_PRODUCT", "WHEAT", 1]])
        after = action([["BUY_PRODUCT", "WHEAT", 1], ["PASS"]])
        self.assertTrue(phase.certify_adjacent_buy_phase(before, after).admitted)

    def test_only_engine_buyable_product_domain(self):
        for item in ("CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL"):
            with self.subTest(item=item):
                before = action([["BUY_PRODUCT", item, 1], []])
                after = action([[], ["BUY_PRODUCT", item, 1]])
                self.assertFalse(phase.certify_adjacent_buy_phase(before, after).admitted)

    def test_quantity_must_be_plain_positive_int(self):
        for bad in (0, -1, True, 1.0, "1"):
            with self.subTest(bad=bad):
                before = action([["BUY_PRODUCT", "WHEAT", bad], []])
                after = action([[], ["BUY_PRODUCT", "WHEAT", bad]])
                self.assertFalse(phase.certify_adjacent_buy_phase(before, after).admitted)

    def test_extra_buy_tokens_fail_closed(self):
        before = action([["BUY_PRODUCT", "WHEAT", 1, "extra"], []])
        after = action([[], ["BUY_PRODUCT", "WHEAT", 1, "extra"]])
        self.assertFalse(phase.certify_adjacent_buy_phase(before, after).admitted)

    def test_other_market_verbs_are_not_this_certificate(self):
        for row in (["BUY_SEED", "WHEAT", 1], ["BUY_ANIMAL", "GOOSE", 1], ["SELL", "WHEAT", 1], ["HIRE"]):
            with self.subTest(row=row):
                before = action([row, []])
                after = action([[], row])
                self.assertFalse(phase.certify_adjacent_buy_phase(before, after).admitted)

    def test_unknown_truthy_row_is_not_noop(self):
        before = action([["BUY_PRODUCT", "WHEAT", 1], ["NOOP"]])
        after = action([["NOOP"], ["BUY_PRODUCT", "WHEAT", 1]])
        self.assertFalse(phase.certify_adjacent_buy_phase(before, after).admitted)

    def test_nonadjacent_move_fails(self):
        before = action([["BUY_PRODUCT", "WHEAT", 1], ["HIRE"], []])
        after = action([[], ["HIRE"], ["BUY_PRODUCT", "WHEAT", 1]])
        cert = phase.certify_adjacent_buy_phase(before, after)
        self.assertFalse(cert.admitted)
        self.assertEqual(cert.reason, "phase_swap_must_be_adjacent")

    def test_queue_length_change_fails(self):
        before = action([["BUY_PRODUCT", "WHEAT", 1]])
        after = action([[], ["BUY_PRODUCT", "WHEAT", 1]])
        cert = phase.certify_adjacent_buy_phase(before, after)
        self.assertFalse(cert.admitted)
        self.assertEqual(cert.reason, "raw_queue_length_changed")

    def test_nonmarket_change_fails(self):
        before = action([["BUY_PRODUCT", "WHEAT", 1], []], marker=1)
        after = action([[], ["BUY_PRODUCT", "WHEAT", 1]], marker=2)
        cert = phase.certify_adjacent_buy_phase(before, after)
        self.assertFalse(cert.admitted)
        self.assertEqual(cert.reason, "nonmarket_fields_changed")

    def test_target_outside_executable_prefix_fails(self):
        before = action([["BUY_PRODUCT", "WHEAT", 1], []])
        after = action([[], ["BUY_PRODUCT", "WHEAT", 1]])
        cert = phase.certify_adjacent_buy_phase(before, after, max_orders=1)
        self.assertFalse(cert.admitted)
        self.assertEqual(cert.reason, "phase_swap_crosses_executable_prefix")

    def test_source_outside_executable_prefix_fails(self):
        before = action([[], ["BUY_PRODUCT", "WHEAT", 1]])
        after = action([["BUY_PRODUCT", "WHEAT", 1], []])
        cert = phase.certify_adjacent_buy_phase(before, after, max_orders=1)
        self.assertFalse(cert.admitted)
        self.assertEqual(cert.reason, "phase_swap_crosses_executable_prefix")

    def test_zero_negative_cap_use_official_minimum_one_then_block_swap(self):
        before = action([["BUY_PRODUCT", "WHEAT", 1], []])
        after = action([[], ["BUY_PRODUCT", "WHEAT", 1]])
        for cap in (0, -7):
            with self.subTest(cap=cap):
                cert = phase.certify_adjacent_buy_phase(before, after, max_orders=cap)
                self.assertFalse(cert.admitted)
                self.assertEqual(cert.effective_cap, 1)

    def test_cap_type_poison_fails_closed(self):
        before = action([["BUY_PRODUCT", "WHEAT", 1], []])
        after = action([[], ["BUY_PRODUCT", "WHEAT", 1]])
        for bad in (True, 2.0, "2", None):
            with self.subTest(bad=bad):
                cert = phase.certify_adjacent_buy_phase(before, after, max_orders=bad)
                self.assertFalse(cert.admitted)
                self.assertEqual(cert.reason, "invalid_market_cap")

    def test_more_than_two_slot_changes_fail(self):
        before = action([["BUY_PRODUCT", "WHEAT", 1], [], ["HIRE"]])
        after = action([[], ["BUY_PRODUCT", "WHEAT", 1], []])
        cert = phase.certify_adjacent_buy_phase(before, after)
        self.assertFalse(cert.admitted)
        self.assertEqual(cert.reason, "exactly_two_raw_slots_must_change")

    def test_json_scalar_types_are_preserved(self):
        before = action([["BUY_PRODUCT", "WHEAT", 1], []], marker=1)
        after = action([[], ["BUY_PRODUCT", "WHEAT", 1]], marker=True)
        cert = phase.certify_adjacent_buy_phase(before, after)
        self.assertFalse(cert.admitted)
        self.assertEqual(cert.reason, "nonmarket_fields_changed")

    def test_nonfinite_evidence_fails_closed(self):
        before = action([["BUY_PRODUCT", "WHEAT", 1], []], marker=math.inf)
        after = action([[], ["BUY_PRODUCT", "WHEAT", 1]], marker=math.inf)
        cert = phase.certify_adjacent_buy_phase(before, after)
        self.assertFalse(cert.admitted)
        self.assertEqual(cert.reason, "invalid_json_or_cap")

    def test_inputs_are_immutable(self):
        before = action([["BUY_PRODUCT", "WHEAT", 4], [], ["HIRE"]], marker={"x": 1})
        after = action([[], ["BUY_PRODUCT", "WHEAT", 4], ["HIRE"]], marker={"x": 1})
        before_copy, after_copy = copy.deepcopy(before), copy.deepcopy(after)
        phase.certify_adjacent_buy_phase(before, after)
        self.assertEqual(before, before_copy)
        self.assertEqual(after, after_copy)


if __name__ == "__main__":
    unittest.main()

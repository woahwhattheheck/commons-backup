import copy
import unittest

from purchase_sizing import OPERATION, size_existing_buy_product


def action(qty=7):
    return {
        "farmer": ["FEED"],
        "hands": [["NORTH"]],
        "market": [
            ["SELL", "EGG", 2],
            ["BUY_PRODUCT", "WHEAT", qty],
            ["BUY_PRODUCT", "FERTILIZER", 3],
            ["HIRE"],
        ],
    }


def observation(shed=0, carried=()):
    return {
        "private": {
            "shed": {"WHEAT": shed, "FERTILIZER": 8},
            "inventories": [{"WHEAT": n} if n else {} for n in carried] or [{}],
        }
    }


def evidence(commitments, *, current=100, end=124, complete=True):
    return {
        "current_step": current,
        "horizon_end_step": end,
        "commitments_complete": complete,
        "commitments": commitments,
    }


def commitment(units, due=110, **patch):
    row = {
        "product": "WHEAT",
        "units": units,
        "due_step": due,
        "source_proven": True,
        "executable": True,
        "source": "planner:animal-feed-window",
    }
    row.update(patch)
    return row


class PurchaseSizingTests(unittest.TestCase):
    def test_default_off_is_exact_identity(self):
        parent = action()
        candidate, report = size_existing_buy_product(
            parent, observation(5), evidence([commitment(6)])
        )
        self.assertEqual(candidate, parent)
        self.assertIsNot(candidate, parent)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "disabled")
        self.assertEqual(report["action_sha256_before"], report["action_sha256_after"])

    def test_partial_owned_stock_sizes_down(self):
        parent = action(7)
        candidate, report = size_existing_buy_product(
            parent, observation(4), evidence([commitment(6)]), enabled=True
        )
        self.assertEqual(candidate["market"][1], ["BUY_PRODUCT", "WHEAT", 2])
        self.assertEqual(report["quantity_before"], 7)
        self.assertEqual(report["quantity_after"], 2)
        self.assertEqual(report["units_removed"], 5)

    def test_owned_stock_includes_shed_and_carried_inventory(self):
        candidate, report = size_existing_buy_product(
            action(7),
            observation(2, (1, 1)),
            evidence([commitment(5)]),
            enabled=True,
        )
        self.assertEqual(report["owned_breakdown"], {"shed": 2, "carried": [1, 1], "total": 4})
        self.assertEqual(candidate["market"][1][2], 1)

    def test_never_increases_parent_purchase(self):
        parent = action(1)
        candidate, report = size_existing_buy_product(
            parent, observation(0), evidence([commitment(5)]), enabled=True
        )
        self.assertEqual(candidate, parent)
        self.assertFalse(report["changed"])
        self.assertEqual(report["quantity_after"], 1)
        self.assertEqual(report["fresh_required"], 5)

    def test_zero_is_slot_preserving_noop_not_row_deletion(self):
        parent = action(4)
        before_tail = copy.deepcopy(parent["market"][2:])
        candidate, report = size_existing_buy_product(
            parent, observation(5), evidence([commitment(5)]), enabled=True
        )
        self.assertEqual(len(candidate["market"]), len(parent["market"]))
        self.assertEqual(candidate["market"][1], ["BUY_PRODUCT", "WHEAT", 0])
        self.assertEqual(candidate["market"][2:], before_tail)
        self.assertTrue(report["zero_quantity_row_preserved"])

    def test_non_target_actions_are_byte_structurally_unchanged(self):
        parent = action(7)
        candidate, _ = size_existing_buy_product(
            parent, observation(4), evidence([commitment(6)]), enabled=True
        )
        self.assertEqual(candidate["farmer"], parent["farmer"])
        self.assertEqual(candidate["hands"], parent["hands"])
        self.assertEqual(candidate["market"][0], parent["market"][0])
        self.assertEqual(candidate["market"][2:], parent["market"][2:])

    def test_fertilizer_is_explicitly_unsupported(self):
        parent = action(7)
        candidate, report = size_existing_buy_product(
            parent,
            observation(4),
            evidence([commitment(6)]),
            enabled=True,
            product="FERTILIZER",
        )
        self.assertEqual(candidate, parent)
        self.assertEqual(report["reason"], "unsupported_product")

    def test_incomplete_commitment_set_fails_closed(self):
        parent = action()
        candidate, report = size_existing_buy_product(
            parent,
            observation(2),
            evidence([commitment(4)], complete=False),
            enabled=True,
        )
        self.assertEqual(candidate, parent)
        self.assertEqual(report["reason"], "fail_closed")
        self.assertIn("commitments_complete", report["error"])

    def test_unproven_target_commitment_fails_closed(self):
        parent = action()
        candidate, report = size_existing_buy_product(
            parent,
            observation(2),
            evidence([commitment(4, source_proven=False)]),
            enabled=True,
        )
        self.assertEqual(candidate, parent)
        self.assertIn("not source-proven", report["error"])

    def test_nonexecutable_target_commitment_fails_closed(self):
        parent = action()
        candidate, report = size_existing_buy_product(
            parent,
            observation(2),
            evidence([commitment(4, executable=False)]),
            enabled=True,
        )
        self.assertEqual(candidate, parent)
        self.assertIn("not executable", report["error"])

    def test_stale_target_commitment_fails_closed(self):
        parent = action()
        candidate, report = size_existing_buy_product(
            parent,
            observation(2),
            evidence([commitment(4, due=99)]),
            enabled=True,
        )
        self.assertEqual(candidate, parent)
        self.assertIn("stale", report["error"])

    def test_no_in_window_target_commitment_stays_inert(self):
        parent = action()
        candidate, report = size_existing_buy_product(
            parent,
            observation(7),
            evidence([commitment(4, due=130)]),
            enabled=True,
        )
        self.assertEqual(candidate, parent)
        self.assertIn("no source-proven WHEAT commitment", report["error"])

    def test_multiple_target_rows_fail_closed(self):
        parent = action()
        parent["market"].append(["BUY_PRODUCT", "WHEAT", 2])
        candidate, report = size_existing_buy_product(
            parent, observation(2), evidence([commitment(4)]), enabled=True
        )
        self.assertEqual(candidate, parent)
        self.assertIn("multiple authored", report["error"])

    def test_malformed_target_quantity_fails_closed(self):
        parent = action()
        parent["market"][1][2] = "7"
        candidate, report = size_existing_buy_product(
            parent, observation(2), evidence([commitment(4)]), enabled=True
        )
        self.assertEqual(candidate, parent)
        self.assertIn("positive integer", report["error"])

    def test_empty_source_fails_closed(self):
        parent = action()
        candidate, report = size_existing_buy_product(
            parent,
            observation(2),
            evidence([commitment(4, source="  ")]),
            enabled=True,
        )
        self.assertEqual(candidate, parent)
        self.assertIn("source required", report["error"])

    def test_other_product_commitments_do_not_expand_scope(self):
        parent = action(7)
        commitments = [
            commitment(5),
            {
                "product": "FERTILIZER",
                "units": 99,
                "due_step": 105,
                "source_proven": False,
                "executable": False,
            },
        ]
        candidate, report = size_existing_buy_product(
            parent, observation(3), evidence(commitments), enabled=True
        )
        self.assertEqual(candidate["market"][1][2], 2)
        self.assertEqual(candidate["market"][2], parent["market"][2])
        self.assertEqual(report["operation"], OPERATION)

    def test_multiple_proven_wheat_commitments_sum_within_window(self):
        parent = action(9)
        commitments = [
            commitment(3, due=104, source="animal:a"),
            commitment(4, due=120, source="animal:b"),
            commitment(100, due=130, source="outside-window"),
        ]
        candidate, report = size_existing_buy_product(
            parent, observation(2), evidence(commitments), enabled=True
        )
        self.assertEqual(report["commitment_units"], 7)
        self.assertEqual(report["fresh_required"], 5)
        self.assertEqual(candidate["market"][1][2], 5)


if __name__ == "__main__":
    unittest.main()

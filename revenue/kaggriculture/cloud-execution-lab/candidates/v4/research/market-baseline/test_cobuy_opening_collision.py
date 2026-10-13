import os
import pathlib
import unittest

from cobuy_opening_collision import (
    _run_market,
    build_receipt,
    decode_apex_action,
    default_paths,
    load_engine,
)

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[7] if len(HERE.parents) > 7 else HERE.parent
ENGINE = pathlib.Path(os.environ.get(
    "COBUY_ENGINE_PATH",
    "/mnt/data/v4found/final-pressure-runtime/checks/reference/engine/kaggriculture.py",
))
if not ENGINE.exists():
    ENGINE = ROOT / "revenue/kaggriculture/cloud-execution-lab/reference/engine/kaggriculture.py"


class CobuyOpeningTests(unittest.TestCase):
    def test_exact_apex_step0_tape_entry_decodes_wheat13_row0(self):
        decoded = decode_apex_action("1 1 0 0 1 4 0 13")
        self.assertEqual([(4, 0, 13)], decoded["orders"])

    def test_decoder_rejects_trailing_values(self):
        with self.assertRaises(ValueError):
            decode_apex_action("1 1 0 0 1 4 0 13 99")

    def test_official_engine_aligned_both_seats_fill_13(self):
        engine = load_engine(ENGINE)
        row = ["BUY_PRODUCT", "WHEAT", 13]
        for rival_seat in (0, 1):
            case = _run_market(engine, row, self_row=0, rival_seat=rival_seat)
            self.assertEqual([13, 13], case["filled_qty_by_seat"])
            self.assertEqual([370, 370], case["cost_by_seat"])
            self.assertEqual(9974, case["market_inventory_after"])

    def test_official_engine_row1_costs_self_13_more(self):
        engine = load_engine(ENGINE)
        row = ["BUY_PRODUCT", "WHEAT", 13]
        for rival_seat in (0, 1):
            aligned = _run_market(engine, row, self_row=0, rival_seat=rival_seat)
            late = _run_market(engine, row, self_row=1, rival_seat=rival_seat)
            self_seat = aligned["self_seat"]
            self.assertEqual(
                13,
                late["cost_by_seat"][self_seat] - aligned["cost_by_seat"][self_seat],
            )
            self.assertEqual(aligned["market_inventory_after"], late["market_inventory_after"])

    def test_checkout_sources_reproduce_receipt_when_available(self):
        paths = default_paths(ROOT)
        if not all(path.exists() for path in paths.values()):
            self.skipTest("full repo source checkout unavailable")
        receipt = build_receipt(**paths)
        self.assertEqual("CURRENT_ALREADY_ALIGNED_GUARDRAIL", receipt["status"])
        self.assertEqual(13, receipt["delta"]["self_cost_penalty_if_moved_to_row1"])


if __name__ == "__main__":
    unittest.main()

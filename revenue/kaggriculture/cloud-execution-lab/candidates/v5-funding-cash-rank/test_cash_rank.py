# SPDX-License-Identifier: Apache-2.0
"""Current-V5 regressions for same-turn funding cash Pareto ranking."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
SOURCE = LAB / "frozen_selected.py"

sys.path.insert(0, str(HERE))
from apply_cash_rank import (  # noqa: E402
    POSTIMAGE,
    POST_FUNCTION_SHA256,
    PREIMAGE,
    RAW_FUNCTION_SHA256,
    SOURCE_BLOB,
    apply,
    function_sha256,
    git_blob,
    materialize,
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load module from " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fixture(module, orders):
    farm = {"money": 0, "hires_today": 0, "unlocked_quadrants": ["NW"]}
    private = {"shed": {"CARROT": 1, "WOOL": 1}}
    market = {
        "inventory": {item: module.m.MARKET_I0 for item in module.m.PRODUCTS},
        "params": module.m.MARKET_PARAMS,
    }
    config = {"farmHandCostMult": 10, "shedCapacity": 100}
    return copy.deepcopy(orders), farm, private, market, config


def execute(module, orders):
    action_orders, farm, private, market, config = fixture(module, orders)
    before = copy.deepcopy(action_orders)
    action, info = module.fund_same_turn_acquisition(
        action_orders,
        farm,
        private,
        market,
        [],
        config,
        0,
        {"CARROT", "WOOL"},
        lambda _item: 0,
    )
    if action_orders != before:
        raise AssertionError("funding helper mutated caller orders")
    if not isinstance(info, dict) or info.get("applied") is not True:
        raise AssertionError("funding helper did not apply: %r" % (info,))
    full = module._market_prefix_state(
        action, farm, private, market, [], config, 0, lambda _item: 0,
        len(action) - 1,
    )
    return action, info, full


class V5FundingCashRank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = SOURCE.read_bytes()
        observed = git_blob(cls.raw)
        if observed != SOURCE_BLOB:
            raise ValueError("current frozen_selected.py blob drifted: " + observed)
        if str(LAB) not in sys.path:
            sys.path.insert(0, str(LAB))
        cls.predecessor = load_module("_v5_cash_rank_predecessor", SOURCE)
        repaired = apply(cls.raw.decode("utf-8"))
        cls.tempdir = tempfile.TemporaryDirectory(prefix="v5-cash-rank-")
        candidate_path = Path(cls.tempdir.name) / "frozen_selected.py"
        candidate_path.write_text(repaired, encoding="utf-8")
        cls.candidate = load_module("_v5_cash_rank_candidate", candidate_path)

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def test_exact_current_source_and_function_are_authenticated(self):
        source = self.raw.decode("utf-8")
        self.assertEqual(function_sha256(source), RAW_FUNCTION_SHA256)
        self.assertEqual(source.count(PREIMAGE), 1)
        self.assertEqual(source.count(POSTIMAGE), 0)

    def test_repair_is_exactly_one_added_minus_sign(self):
        source = self.raw.decode("utf-8")
        repaired = apply(source)
        self.assertEqual(len(repaired), len(source) + 1)
        self.assertEqual(function_sha256(repaired), POST_FUNCTION_SHA256)
        self.assertEqual(repaired.count(PREIMAGE), 0)
        self.assertEqual(repaired.count(POSTIMAGE), 1)
        self.assertEqual(repaired.replace(POSTIMAGE, PREIMAGE, 1), source)
        compile(repaired, "v5_same_turn_funding_cash_rank", "exec")

    def test_equal_movement_frontier_prefers_more_certified_cash(self):
        orders = [[], ["HIRE"], ["SELL", "CARROT", 1], ["SELL", "WOOL", 1]]
        predecessor_action, predecessor_info, _ = execute(self.predecessor, orders)
        candidate_action, candidate_info, _ = execute(self.candidate, orders)

        self.assertEqual(predecessor_info["item"], "CARROT")
        self.assertEqual(candidate_info["item"], "WOOL")
        self.assertEqual(predecessor_info["moved_quantity"], 1)
        self.assertEqual(candidate_info["moved_quantity"], 1)
        self.assertEqual(predecessor_info["funded_completed"], candidate_info["funded_completed"])
        self.assertEqual(candidate_info["remaining_cash_after_target"], 190)
        self.assertEqual(predecessor_info["remaining_cash_after_target"], 25)
        self.assertEqual(
            candidate_info["remaining_cash_after_target"]
            - predecessor_info["remaining_cash_after_target"],
            165,
        )
        expected_sales = {"CARROT": 1, "WOOL": 1}
        self.assertEqual(self.predecessor.sale_quantities(predecessor_action), expected_sales)
        self.assertEqual(self.candidate.sale_quantities(candidate_action), expected_sales)

    def test_more_cash_rescues_later_same_turn_fixed_acquisition(self):
        # The first HIRE is the helper's target.  Both donors move exactly one
        # already-planned sale into slot 0 and complete that same HIRE.  The
        # predecessor chooses CARROT, leaving $25 after HIRE, so the following
        # $100 STRAWBERRY seed buy fails before the later WOOL sale can help.
        # The repaired rank chooses WOOL, leaving $190 and preserving that buy.
        orders = [
            [],
            ["HIRE"],
            ["BUY_SEED", "STRAWBERRY", 1],
            ["SELL", "CARROT", 1],
            ["SELL", "WOOL", 1],
        ]
        predecessor_action, predecessor_info, predecessor_full = execute(
            self.predecessor, orders
        )
        candidate_action, candidate_info, candidate_full = execute(self.candidate, orders)

        self.assertEqual(predecessor_info["item"], "CARROT")
        self.assertEqual(candidate_info["item"], "WOOL")
        self.assertEqual(predecessor_info["moved_quantity"], candidate_info["moved_quantity"])
        self.assertEqual(predecessor_info["moved_quantity"], 1)
        self.assertEqual(predecessor_full["outcomes"][1]["completed"], 1)
        self.assertEqual(candidate_full["outcomes"][1]["completed"], 1)
        self.assertEqual(predecessor_full["outcomes"][2]["completed"], 0)
        self.assertEqual(candidate_full["outcomes"][2]["completed"], 1)
        self.assertEqual(self.predecessor.sale_quantities(predecessor_action), {"CARROT": 1, "WOOL": 1})
        self.assertEqual(self.candidate.sale_quantities(candidate_action), {"CARROT": 1, "WOOL": 1})

    def test_materializer_binds_blob_and_postimage_identity(self):
        with tempfile.TemporaryDirectory(prefix="v5-cash-rank-materialize-") as tmp:
            output = Path(tmp) / "frozen_selected.py"
            receipt = materialize(SOURCE, output)
            self.assertEqual(receipt["source_blob"], SOURCE_BLOB)
            self.assertEqual(receipt["raw_function_sha256"], RAW_FUNCTION_SHA256)
            self.assertEqual(receipt["post_function_sha256"], POST_FUNCTION_SHA256)
            self.assertEqual(receipt["delta_bytes"], 1)
            self.assertEqual(function_sha256(output.read_text(encoding="utf-8")), POST_FUNCTION_SHA256)

    def test_changed_funding_function_fails_closed(self):
        source = self.raw.decode("utf-8")
        tampered = source.replace(
            "Producer order indexes never move.",
            "Producer order indexes never move; tampered.",
            1,
        )
        with self.assertRaisesRegex(ValueError, "source changed"):
            apply(tampered)


if __name__ == "__main__":
    unittest.main()

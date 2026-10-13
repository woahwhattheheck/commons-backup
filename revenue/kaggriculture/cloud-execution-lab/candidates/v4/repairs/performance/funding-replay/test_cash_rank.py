# SPDX-License-Identifier: Apache-2.0
"""Focused V4 regression for same-turn funding cash Pareto ranking."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[4]
SOURCE = LAB / "frozen_selected.py"
SOURCE_BLOB = "fc7baf5c179818a55037f6a61d92984d81d1a21c"

sys.path.insert(0, str(HERE))
from apply_cash_rank import (  # noqa: E402
    ALLOWED_PREIMAGE_FUNCTION_SHA256,
    POSTIMAGE,
    PREIMAGE,
    apply,
    function_sha256,
)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load module from " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def execute_witness(module):
    mechanics = sys.modules.get("mechanics")
    if mechanics is None:
        raise RuntimeError("frozen_selected did not load mechanics")
    orders = [[], ["HIRE"], ["SELL", "CARROT", 1], ["SELL", "WOOL", 1]]
    farm = {"money": 0, "hires_today": 0, "unlocked_quadrants": ["NW"]}
    private = {"shed": {"CARROT": 1, "WOOL": 1}}
    market = {
        "inventory": {"CARROT": mechanics.MARKET_I0, "WOOL": mechanics.MARKET_I0},
        "params": mechanics.MARKET_PARAMS,
    }
    config = {"farmHandCostMult": 10, "shedCapacity": 100}
    before = copy.deepcopy(orders)
    action, info = module.fund_same_turn_acquisition(
        orders,
        farm,
        private,
        market,
        [],
        config,
        0,
        {"CARROT", "WOOL"},
        lambda _item: 0,
    )
    if orders != before:
        raise AssertionError("funding helper mutated the caller orders")
    if not isinstance(info, dict) or info.get("applied") is not True:
        raise AssertionError("funding helper did not apply: %r" % (info,))
    return action, info


class SameTurnFundingCashRank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = SOURCE.read_bytes()
        if git_blob(cls.raw) != SOURCE_BLOB:
            raise ValueError("current frozen_selected.py blob drifted; rebase the V4 repair")
        if str(LAB) not in sys.path:
            sys.path.insert(0, str(LAB))

    def test_exact_current_function_identity_is_authenticated(self):
        source = self.raw.decode("utf-8")
        self.assertIn(function_sha256(source), ALLOWED_PREIMAGE_FUNCTION_SHA256)
        self.assertEqual(source.count(PREIMAGE), 1)
        self.assertEqual(source.count(POSTIMAGE), 0)

    def test_repair_is_exactly_one_added_minus_sign(self):
        source = self.raw.decode("utf-8")
        repaired = apply(source)
        self.assertEqual(len(repaired), len(source) + 1)
        self.assertEqual(repaired.count(PREIMAGE), 0)
        self.assertEqual(repaired.count(POSTIMAGE), 1)
        self.assertEqual(repaired.replace(POSTIMAGE, PREIMAGE, 1), source)
        compile(repaired, "v4_same_turn_funding_cash_rank", "exec")

    def test_real_helper_prefers_more_cash_on_equal_movement_frontier(self):
        source = self.raw.decode("utf-8")
        predecessor = load_module("_v4_cash_rank_predecessor", SOURCE)
        repaired = apply(source)
        with tempfile.TemporaryDirectory(prefix="v4-cash-rank-") as tmp:
            candidate_path = Path(tmp) / "frozen_selected.py"
            candidate_path.write_text(repaired, encoding="utf-8")
            candidate = load_module("_v4_cash_rank_candidate", candidate_path)
            predecessor_action, predecessor_info = execute_witness(predecessor)
            candidate_action, candidate_info = execute_witness(candidate)

        self.assertEqual(predecessor_info["item"], "CARROT")
        self.assertEqual(candidate_info["item"], "WOOL")
        self.assertEqual(predecessor_info["moved_quantity"], 1)
        self.assertEqual(candidate_info["moved_quantity"], 1)
        self.assertEqual(predecessor_info["funded_completed"], candidate_info["funded_completed"])
        self.assertEqual(candidate_info["remaining_cash_after_target"]
                         - predecessor_info["remaining_cash_after_target"], 165)
        expected_sales = {"CARROT": 1, "WOOL": 1}
        self.assertEqual(predecessor.sale_quantities(predecessor_action), expected_sales)
        self.assertEqual(predecessor.sale_quantities(candidate_action), expected_sales)

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

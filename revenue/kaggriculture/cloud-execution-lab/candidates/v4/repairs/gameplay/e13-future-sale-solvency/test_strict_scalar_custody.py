# SPDX-License-Identifier: Apache-2.0
"""Focused scalar-custody regressions for the E13 generated candidate."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("e13_port", HERE / "port_current_runtime.py")
assert SPEC is not None and SPEC.loader is not None
PORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PORT)


def load_candidate_function():
    namespace = {
        "materialize_sales": lambda market, current, shed, targets, max_orders: [],
        "_funding_trace": lambda *args, **kwargs: {"acquisitions": [], "cash": 0},
        "_funding_prefix_end": lambda scout, now, end: (end, None),
    }
    exec(PORT.REPLACEMENT_FUNCTION, namespace)
    return namespace["funded_minimum_now"]


def load_cap_probe_function():
    materialize_caps: list[int] = []
    funding_caps: list[int] = []
    funding_markets: list[list[list[object]]] = []

    def materialize_sales(market, current, shed, targets, max_orders):
        materialize_caps.append(max_orders)
        return [list(row) for row in market[:max_orders]]

    def funding_trace(
        obs, config, farm, private, route, now, end, current_market, stress_units=0
    ):
        cap = config.get("maxMarketOrdersPerTurn")
        funding_caps.append(cap)
        funding_markets.append([list(row) for row in current_market])
        acquisitions = []
        if cap >= 1 and current_market:
            acquisitions.append(((now, 0, "BUY_SEED", "WHEAT"), 1))
        return {"acquisitions": acquisitions, "cash": 0, "executed_sales": []}

    namespace = {
        "materialize_sales": materialize_sales,
        "_funding_trace": funding_trace,
        "_funding_prefix_end": lambda scout, now, end: (end, None),
    }
    exec(PORT.REPLACEMENT_FUNCTION, namespace)
    return (
        namespace["funded_minimum_now"],
        materialize_caps,
        funding_caps,
        funding_markets,
    )


class StrictScalarCustodyTests(unittest.TestCase):
    def setUp(self):
        self.fn = load_candidate_function()
        self.base = {"market": []}
        self.private = {"shed": {}}
        self.current = {"MELON": 3}
        self.config = {"maxMarketOrdersPerTurn": 10}
        self.obs = {"step": 100}

    def call(self, *, obs=None, config=None, current=None, end=110, stress_units=32):
        return self.fn(
            self.obs if obs is None else obs,
            self.config if config is None else config,
            self.base,
            {},
            self.private,
            [],
            end,
            self.current if current is None else current,
            {},
            "MELON",
            stress_units=stress_units,
        )

    def test_plain_integers_preserve_positive_control(self):
        minimum, certificate = self.call()
        self.assertEqual(minimum, 0)
        self.assertFalse(certificate["fallback"])
        self.assertEqual(certificate["baseline_now"], 3)
        self.assertEqual(certificate["stress_units"], 32)
        self.assertEqual(certificate["raw_max_market_orders"], 10)
        self.assertEqual(certificate["effective_max_market_orders"], 10)

    def test_zero_market_limit_matches_official_min_one_prefix(self):
        fn, materialize_caps, funding_caps, funding_markets = load_cap_probe_function()
        base = {"market": [["BUY_SEED", "WHEAT", 1]]}
        private = {"shed": {}}
        minimum, certificate = fn(
            {"step": 100},
            {"maxMarketOrdersPerTurn": 0},
            base,
            {},
            private,
            [],
            100,
            {"MELON": 3},
            {},
            "MELON",
            stress_units=0,
        )
        self.assertEqual(minimum, 0)
        self.assertFalse(certificate["fallback"])
        self.assertEqual(certificate["raw_max_market_orders"], 0)
        self.assertEqual(certificate["effective_max_market_orders"], 1)
        self.assertEqual(certificate["reference_acquisitions"], 1)
        self.assertTrue(materialize_caps)
        self.assertTrue(funding_caps)
        self.assertTrue(funding_markets)
        self.assertEqual(set(materialize_caps), {1})
        self.assertEqual(set(funding_caps), {1})
        self.assertTrue(all(rows == [["BUY_SEED", "WHEAT", 1]] for rows in funding_markets))

    def test_zero_and_one_market_limits_have_same_effective_prefix(self):
        outcomes = []
        for raw_cap in (0, 1):
            fn, materialize_caps, funding_caps, funding_markets = load_cap_probe_function()
            minimum, certificate = fn(
                {"step": 100},
                {"maxMarketOrdersPerTurn": raw_cap},
                {"market": [["BUY_SEED", "WHEAT", 1], ["BUY_SEED", "CARROT", 1]]},
                {},
                {"shed": {}},
                [],
                100,
                {"MELON": 3},
                {},
                "MELON",
                stress_units=0,
            )
            outcomes.append(
                (
                    minimum,
                    certificate["effective_max_market_orders"],
                    certificate["reference_acquisitions"],
                    tuple(materialize_caps),
                    tuple(funding_caps),
                    tuple(tuple(tuple(row) for row in rows) for rows in funding_markets),
                )
            )
        self.assertEqual(outcomes[0], outcomes[1])

    def test_step_bool_rejected(self):
        with self.assertRaises(ValueError):
            self.call(obs={"step": True})

    def test_step_string_rejected(self):
        with self.assertRaises(ValueError):
            self.call(obs={"step": "100"})

    def test_step_float_rejected(self):
        with self.assertRaises(ValueError):
            self.call(obs={"step": 100.0})

    def test_baseline_bool_rejected(self):
        with self.assertRaises(ValueError):
            self.call(current={"MELON": True})

    def test_baseline_string_rejected(self):
        with self.assertRaises(ValueError):
            self.call(current={"MELON": "3"})

    def test_baseline_float_rejected(self):
        with self.assertRaises(ValueError):
            self.call(current={"MELON": 3.0})

    def test_market_limit_bool_rejected(self):
        with self.assertRaises(ValueError):
            self.call(config={"maxMarketOrdersPerTurn": True})

    def test_market_limit_string_rejected(self):
        with self.assertRaises(ValueError):
            self.call(config={"maxMarketOrdersPerTurn": "10"})

    def test_market_limit_float_rejected(self):
        with self.assertRaises(ValueError):
            self.call(config={"maxMarketOrdersPerTurn": 10.0})

    def test_stress_units_bool_rejected(self):
        with self.assertRaises(ValueError):
            self.call(stress_units=True)

    def test_stress_units_string_rejected(self):
        with self.assertRaises(ValueError):
            self.call(stress_units="32")

    def test_stress_units_float_rejected(self):
        with self.assertRaises(ValueError):
            self.call(stress_units=32.0)

    def test_end_bool_rejected(self):
        with self.assertRaises(ValueError):
            self.call(end=True)

    def test_end_string_rejected(self):
        with self.assertRaises(ValueError):
            self.call(end="110")

    def test_end_float_rejected(self):
        with self.assertRaises(ValueError):
            self.call(end=110.0)

    def test_end_before_step_rejected(self):
        with self.assertRaises(ValueError):
            self.call(end=99)


if __name__ == "__main__":
    unittest.main()

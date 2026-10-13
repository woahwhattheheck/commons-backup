# SPDX-License-Identifier: MIT
"""Check the real peer helper and ensure this acceptance gate rejects bad output."""
from __future__ import annotations
import copy
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import check_flow_bound_corpus as gate
import flow_engine_corpus as corpus


class FlowBoundAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path(os.environ.get("FLOW_BOUNDS_HELPER", str(Path(__file__).resolve().parent / "effective_flow_bounds.py")))
        if "FLOW_BOUNDS_HELPER" not in os.environ and not cls.path.exists():
            raise unittest.SkipTest("optional peer helper has not landed; supply FLOW_BOUNDS_HELPER")
        cls.helper = gate.load_helper(cls.path)
        engine = corpus.load_engine(Path(os.environ.get("FLOW_ENGINE_DIR", str(corpus.default_engine_dir()))))
        cls.records = corpus.build_corpus(engine)

    def test_real_source_contains_all_independent_truth(self):
        result = gate.evaluate(self.helper, self.records)
        self.assertEqual(result["product_containments"], 2124)
        self.assertEqual(result["singleton_intervals"], 1948)
        self.assertEqual(result["certified_signals_across_three_thresholds"], 22)
        self.assertEqual(result["output_sha256"],
                         "b784f997a5265334999fc91f14043f424b4a81b19ae1762a1acf85e6a0f4f11a")

    def test_public_adapter_has_no_private_prices_or_oracle(self):
        for r in self.records:
            previous, action, current, cfg = gate.public_inputs(r)
            for obs in (previous, current):
                self.assertEqual(set(obs), {"step", "player", "market", "town"})
                self.assertEqual(set(obs["market"]), {"inventory"})
            self.assertEqual(action, r["input"]["submitted_action"])
            self.assertNotIn("seed", cfg)

    def test_false_dump_world_is_uncertain_not_a_positive_signal(self):
        r = next(r for r in self.records if r["id"] == "cash_zero_false_dump/seat0")
        bounds = self.helper.effective_flow_bounds(*gate.public_inputs(r))
        self.assertEqual(bounds["WHEAT"], (0, 200))
        self.assertEqual(self.helper.confirmed_net_sells(bounds, threshold=1), {})

    def test_ignored_own_rows_retain_exact_rival_truth(self):
        for name in ("unsupported_buy", "raw_dead_suffix", "blank_owns_slot", "normalized_zero_cap"):
            r = next(r for r in self.records if r["id"] == f"{name}/seat0")
            bounds = self.helper.effective_flow_bounds(*gate.public_inputs(r))
            self.assertTrue(all(pair == (0, 0) for pair in bounds.values()))

    def test_same_source_is_required_under_optimized_python(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "changed.py"
            p.write_bytes(self.path.read_bytes() + b"\n# not the pinned source\n")
            with self.assertRaisesRegex(ValueError, "source pin"):
                gate.load_helper(p)

    def test_eight_broken_candidate_contracts_are_rejected(self):
        real = self.helper.effective_flow_bounds
        signals = self.helper.confirmed_net_sells

        def collapsed_upper(*args):
            return {p: (b[1], b[1]) for p, b in real(*args).items()}

        def collapse_all_zero(*args):
            return {p: (0, 0) for p in real(*args)}

        def widen_until_vacuous(*args):
            return {p: (-10**9, 10**9) for p in real(*args)}

        def float_endpoints(*args):
            return {p: (float(b[0]), float(b[1])) for p, b in real(*args).items()}

        def omit_product(*args):
            out = real(*args)
            del out["WHEAT"]
            return out

        def mutate_input(*args):
            out = real(*args)
            args[0]["step"] += 1
            return out

        def signal_upper(bounds, threshold=150):
            return {p: b[1] for p, b in bounds.items() if b[1] >= threshold}

        variants = {
            "uncertain_upper_as_exact": (collapsed_upper, signals),
            "fabricated_all_zero": (collapse_all_zero, signals),
            "vacuous_infinite_envelope": (widen_until_vacuous, signals),
            "fractional_domain": (float_endpoints, signals),
            "omitted_product": (omit_product, signals),
            "input_mutation": (mutate_input, signals),
            "unknown_everywhere": (lambda *args: None, signals),
            "upper_bound_is_positive_signal": (real, signal_upper),
        }
        for name, (infer, select) in variants.items():
            with self.subTest(mutant=name):
                helper = SimpleNamespace(effective_flow_bounds=infer, confirmed_net_sells=select)
                with self.assertRaises(ValueError):
                    gate.evaluate(helper, self.records)

    def test_corpus_truth_is_never_aliased_into_input(self):
        r = copy.deepcopy(self.records[0])
        before = copy.deepcopy(r)
        args = gate.public_inputs(r)
        args[0]["market"]["inventory"]["WHEAT"] += 1
        args[1]["market"].append(["SELL", "WHEAT", 100])
        self.assertEqual(r, before)


if __name__ == "__main__":
    unittest.main(verbosity=2)

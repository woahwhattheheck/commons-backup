# SPDX-License-Identifier: Apache-2.0
"""Exact-source, full-optimizer parity and lifetime tests; no game/strength claim."""
from __future__ import annotations

import argparse
import ast
import copy
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
import weakref

from repair_cache_lifetime import SOURCE_GIT, SCHEDULER_GIT, MARKER, git_blob, transform

RUNTIME = None
DEPENDENCIES = {
    "mechanics.py": "044a4f9c0a4a44dde10ada57563238bcaf82075d",
    "reference/decision/decision.py": "2931aa55831204fbb473ab85a6f5b81ec947fcf7",
}
COUNTS = {"optimizer_parity_cells": 0, "capacity_trace_equal_cells": 0, "scheduler_parity_cells": 0}


def load(source, name):
    module = types.ModuleType(name)
    module.__file__ = str(RUNTIME / "selected_sell_core.py")
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def arguments(**updates):
    result = dict(item="WHEAT", quantity=8, inventory=9800, params=None,
                  shops=["BAKERY", "YARN_STORE"], config={}, now=400,
                  dates=[400, 404, 408], reference=((400, 8),), rival_quantity=4,
                  minimum_now=0)
    result.update(updates)
    return result


def track(module, *, retain_caches=False):
    original = module.MarketPath
    refs, caches = [], []

    class Tracked(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            refs.append(weakref.ref(self))
            if retain_caches:
                caches.append((self.quote, self.single, self.joint))

    module.MarketPath = Tracked
    return refs, caches


class CacheLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if RUNTIME is None:
            raise RuntimeError("--runtime must identify the native source package")
        for name, expected in DEPENDENCIES.items():
            actual = git_blob((RUNTIME / name).read_bytes())
            if actual != expected:
                raise ValueError(f"dependency drift: {name}: {actual}")
        cls.source = (RUNTIME / "selected_sell_core.py").read_text()
        cls.output = transform(cls.source)

    def compare(self, args, predicate=lambda plan: True):
        old, new = load(self.source, "cachelife_old"), load(self.output, "cachelife_new")
        old_calls, new_calls = [], []
        before = copy.deepcopy(args)

        def check(plan, calls):
            calls.append(copy.deepcopy(plan))
            return predicate(plan)

        expected = old.optimize_lot(**copy.deepcopy(args), capacity_ok=lambda p: check(p, old_calls))
        actual = new.optimize_lot(**copy.deepcopy(args), capacity_ok=lambda p: check(p, new_calls))
        self.assertEqual(actual, expected)
        self.assertEqual(new_calls, old_calls)
        self.assertEqual(args, before)
        COUNTS["optimizer_parity_cells"] += 1
        COUNTS["capacity_trace_equal_cells"] += 1
        return actual

    def test_all_products_rules_and_capacity_modes(self):
        items = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL", "FERTILIZER")
        capacities = (lambda p: True, lambda p: False,
                      lambda p: p != ((400, 8),), lambda p: dict(p).get(400, 0) >= 4)
        for item in items:
            for inventory in (9800, 10000, 20000):
                for rule in ("strict", "expected_downside", "minimax_regret"):
                    for number, capacity in enumerate(capacities):
                        with self.subTest(item=item, inventory=inventory, rule=rule, capacity=number):
                            self.compare(arguments(item=item, inventory=inventory,
                                                   config={"sellAcceptanceRule": rule,
                                                           "sellDownsideBound": 10}), capacity)

    def test_terminal_carry_zero_quantity_and_minimum(self):
        for quantity in (0, 1, 9):
            for now, dates, last in ((400, [400], 718), (717, [717, 718], 718),
                                     (0, [0, 1, 7], 718), (718, [718], 718)):
                for rule in ("strict", "expected_downside", "minimax_regret"):
                    self.compare(arguments(quantity=quantity, now=now, dates=dates,
                                           last=last, reference=((now, quantity),),
                                           minimum_now=min(quantity, 2),
                                           config={"sellAcceptanceRule": rule}))

    def test_custom_prices_and_weighted_scenarios(self):
        base = load(self.source, "cachelife_prices")
        params = copy.deepcopy(base.m.MARKET_PARAMS)
        params["WHEAT"].update(base=31, T=350)
        for rule in ("strict", "expected_downside", "minimax_regret", "unknown"):
            self.compare(arguments(params=params, config={
                "sellAcceptanceRule": rule, "sellDownsideBound": 5,
                "sellScenarioWeights": {"no_rival": 3, "observed_paired": 1},
                "townShopSellInterval": 3, "townCenterSellInterval": 17}))

    def test_private_model_released_without_cyclic_gc(self):
        enabled = gc.isenabled()
        gc.collect()
        gc.disable()
        old_refs = []
        try:
            for source, expected_retained in ((self.source, 16), (self.output, 0)):
                module = load(source, "cachelife_lifetime")
                refs, _ = track(module)
                for _ in range(16):
                    module.optimize_lot(**arguments())
                self.assertEqual(sum(ref() is not None for ref in refs), expected_retained)
                if expected_retained:
                    old_refs = refs
            gc.collect()
            self.assertEqual(sum(ref() is not None for ref in old_refs), 0)
        finally:
            if enabled:
                gc.enable()
            gc.collect()

    def test_retained_wrapper_tables_are_empty_and_cycles_broken(self):
        module = load(self.output, "cachelife_retained")
        refs, caches = track(module, retain_caches=True)
        module.optimize_lot(**arguments())
        self.assertTrue(caches)
        self.assertTrue(all(cache.cache_info().currsize == 0 for cache in caches[0]))
        self.assertIsNotNone(refs[0]())  # Test deliberately holds bound wrappers.
        self.assertFalse(hasattr(refs[0](), "single"))
        self.assertFalse(hasattr(refs[0](), "joint"))
        caches.clear()
        self.assertIsNone(refs[0]())

    def test_interruptions_keep_exception_identity_and_dispose_tables(self):
        class Stop(BaseException):
            pass
        for exception in (RuntimeError("callback"), Stop("deadline"), KeyboardInterrupt()):
            module = load(self.output, "cachelife_exception")
            refs, caches = track(module, retain_caches=True)

            def fail(_plan):
                raise exception

            try:
                module.optimize_lot(**arguments(), capacity_ok=fail)
            except BaseException as caught:
                self.assertIs(caught, exception)
                self.assertTrue(all(c.cache_info().currsize == 0 for c in caches[0]))
                self.assertFalse(hasattr(refs[0](), "single"))
                self.assertFalse(hasattr(refs[0](), "joint"))
            else:
                self.fail("exception swallowed")
            exception.__traceback__ = None
            caches.clear()
            self.assertIsNone(refs[0]())

    def test_score_exception_after_partial_population(self):
        for source, cleared in ((self.source, False), (self.output, True)):
            module = load(source, "cachelife_score_exception")
            refs, caches = track(module, retain_caches=True)
            original = module.MarketPath.score

            def fail(self, *args, **kwargs):
                original(self, *args, **kwargs)
                raise ValueError("after first score")

            module.MarketPath.score = fail
            with self.assertRaisesRegex(ValueError, "after first score"):
                module.optimize_lot(**arguments())
            self.assertEqual(all(c.cache_info().currsize == 0 for c in caches[0]), cleared)
            caches.clear()
        gc.collect()

    def test_preconstruction_failure_unchanged(self):
        for source in (self.source, self.output):
            module = load(source, "cachelife_early_error")
            refs, _ = track(module)
            with self.assertRaises(IndexError):
                module.optimize_lot(**arguments(dates=[]))
            self.assertEqual(refs, [])

    def test_reentrant_optimizer_has_independent_lifetimes(self):
        for source in (self.source, self.output):
            module = load(source, "cachelife_reentrant")
            seen = []

            def capacity(_plan):
                if not seen:
                    seen.append(module.optimize_lot(**arguments(quantity=1, reference=((400, 1),))))
                return True

            result = module.optimize_lot(**arguments(), capacity_ok=capacity)
            self.assertEqual(len(seen), 1)
            if source == self.source:
                baseline = (result, seen)
            else:
                self.assertEqual((result, seen), baseline)

    def test_public_marketpath_keeps_reusable_cache_contract(self):
        module = load(self.output, "cachelife_public")
        model = module.MarketPath("WHEAT", 10000, None, [], {}, 400, 408)
        saved_single = model.single
        expected = model.score(((400, 8),), 8, 2, "paired")
        self.assertEqual(model.score(((400, 8),), 8, 2, "paired"), expected)
        self.assertIs(model.single, saved_single)
        self.assertEqual(saved_single(10000, 8), model.single(10000, 8))
        self.assertGreater(model.single.cache_info().hits, 0)

    def test_production_gc_configuration_untouched(self):
        enabled = gc.isenabled()
        try:
            for desired in (True, False):
                (gc.enable if desired else gc.disable)()
                module = load(self.output, "cachelife_gc_state")
                module.optimize_lot(**arguments())
                self.assertEqual(gc.isenabled(), desired)
        finally:
            (gc.enable if enabled else gc.disable)()
            gc.collect()

    def test_source_pin_and_duplicate_application_rejected(self):
        with self.assertRaisesRegex(ValueError, "blob mismatch"):
            transform(self.source + "# drift\n")
        with self.assertRaisesRegex(ValueError, "already applied"):
            transform(self.output, git_blob(self.output.encode()))
        with self.assertRaisesRegex(ValueError, "full lowercase"):
            transform(self.source, SOURCE_GIT[:8])

    def test_composition_preserves_reviewed_peer_statements(self):
        # Synthetic composition control, NOT a claim to consume SIEVE's actual patch.
        edited = self.source.replace("    accepted=False\n", "    accepted=False\n    peer_counter=0\n", 1)
        self.assertNotEqual(edited, self.source)
        output = transform(edited, git_blob(edited.encode()))
        self.assertIn("        peer_counter=0\n", output)
        old = load(edited, "cachelife_peer_old")
        new = load(output, "cachelife_peer_new")
        self.assertEqual(old.optimize_lot(**arguments()), new.optimize_lot(**arguments()))

    def test_invalid_composition_shapes_fail_closed(self):
        mutations = (
            self.source.replace("    accepted=False\n", "    accepted=False\n    model=None\n", 1),
            self.source.replace("lru_cache(maxsize=8192)(self._joint)", "lru_cache(maxsize=8)(self._joint)"),
            self.source.replace("def optimize_lot(", "async def optimize_lot("),
            self.source.replace("    accepted=False\n", "    accepted=False\n    yield 1\n", 1),
            self.source.replace("    accepted=False\n", "    accepted=False\n    exposed=model\n", 1),
            self.source.replace("    accepted=False\n", "    accepted=False\n    return model\n", 1),
        )
        for mutation in mutations:
            with self.assertRaises(ValueError):
                transform(mutation, git_blob(mutation.encode()))

    def test_scheduler_optimizer_parity_and_disposal(self):
        source = (RUNTIME / "scheduler.py").read_text()
        output = transform(source, SCHEDULER_GIT)
        for item in ("WHEAT", "CARROT", "STRAWBERRY", "WOOL", "MILK"):
            for inventory in (9800, 10000, 20000):
                for capacity in (lambda p: True, lambda p: False, lambda p: p != ((400, 8),)):
                    old, new = load(source, "scheduler_old"), load(output, "scheduler_new")
                    calls = [[], []]
                    def check(plan, side):
                        calls[side].append(plan)
                        return capacity(plan)
                    args = arguments(item=item, inventory=inventory)
                    expected = old.optimize_lot(**args, capacity_ok=lambda p: check(p, 0))
                    actual = new.optimize_lot(**args, capacity_ok=lambda p: check(p, 1))
                    self.assertEqual(actual, expected)
                    self.assertEqual(calls[0], calls[1])
                    COUNTS["scheduler_parity_cells"] += 1
        module = load(output, "scheduler_lifetime")
        refs, caches = track(module, retain_caches=True)
        module.optimize_lot(**arguments())
        self.assertTrue(all(c.cache_info().currsize == 0 for c in caches[0]))
        self.assertFalse(hasattr(refs[0](), "single"))
        self.assertFalse(hasattr(refs[0](), "joint"))

    def test_cli_cannot_overwrite_or_alias_source(self):
        repair = Path(__file__).with_name("repair_cache_lifetime.py")
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.py"
            output = Path(folder) / "candidate.py"
            source.write_text(self.source)
            command = [sys.executable, str(repair), str(source), str(output)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(output.read_text(), self.output)
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertNotEqual(subprocess.run(command[:-1] + [str(source)], capture_output=True).returncode, 0)
            self.assertEqual(git_blob(source.read_bytes()), SOURCE_GIT)


def main():
    global RUNTIME
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--receipt", type=Path)
    args, remaining = parser.parse_known_args()
    RUNTIME = args.runtime.resolve()
    sys.path.insert(0, str(RUNTIME))
    result = unittest.main(argv=[sys.argv[0]] + remaining, exit=False).result
    receipt = dict(schema="titan-v4-cache-lifetime-tests/v1", python=sys.version,
                   optimized=not __debug__, source_git=SOURCE_GIT,
                   candidate_git=git_blob(transform((RUNTIME / "selected_sell_core.py").read_text()).encode()),
                   tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                   skipped=len(result.skipped), counters=COUNTS,
                   passed=result.wasSuccessful() and not result.skipped,
                   strength_claim=False, package_promotion=False)
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        args.receipt.write_text(text)
    print(text, end="")
    raise SystemExit(0 if receipt["passed"] else 1)


if __name__ == "__main__":
    main()

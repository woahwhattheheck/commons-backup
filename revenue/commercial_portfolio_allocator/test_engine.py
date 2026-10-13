from __future__ import annotations

import copy
import unittest

from . import _test_engine_legacy as _legacy
from . import acceptance as acceptance_module
from .acceptance import NOW, base_packet, opportunity
from .engine import (
    _compile_plan_at,
    _verify_plan_at,
    compile_plan as public_compile_plan,
    verify_plan as public_verify_plan,
)

# The legacy suite is preserved byte-for-byte and runs against the explicitly private,
# deterministic clock surface. Production/package exports below remain process-clock owned.
_legacy.compile_plan = _compile_plan_at
_legacy.verify_plan = _verify_plan_at
CommercialPortfolioAllocatorTests = _legacy.CommercialPortfolioAllocatorTests


class AuthorityBoundaryTests(unittest.TestCase):
    def test_conflicting_generations_and_replays_are_permutation_invariant(self):
        packet = base_packet("conflict-permutation")
        first_generation = opportunity("x")
        second_generation = copy.deepcopy(first_generation)
        second_generation["stage"] = "PROPOSAL"

        packet["opportunities"] = [first_generation, second_generation, copy.deepcopy(first_generation)]
        first = _compile_plan_at(packet, now=NOW)

        packet["opportunities"] = [second_generation, copy.deepcopy(first_generation), first_generation]
        second = _compile_plan_at(packet, now=NOW)

        self.assertEqual(first, second)
        self.assertEqual(first["stage"], "HOLD")
        self.assertEqual(first["replay_collapses"], 1)
        self.assertEqual(len(first["opportunity_id_conflicts"]), 1)
        generations = first["opportunity_id_conflicts"][0]["generations"]
        self.assertEqual(sorted(item["occurrences"] for item in generations), [1, 2])

    def test_public_current_surfaces_reject_caller_selected_clock(self):
        packet = base_packet("clock")
        packet["opportunities"] = [opportunity("x")]
        historical = _compile_plan_at(packet, now=NOW)
        with self.assertRaises(TypeError):
            public_compile_plan(packet, now=NOW)
        with self.assertRaises(TypeError):
            public_verify_plan(packet, historical, now=NOW)

    def test_acceptance_does_not_reexport_deterministic_clock_as_public_compile(self):
        self.assertFalse(hasattr(acceptance_module, "compile_plan"))
        self.assertTrue(hasattr(acceptance_module, "_compile_plan_at"))

    def test_stale_historical_receipt_does_not_clear_current_gate(self):
        packet = base_packet("stale-current")
        packet["opportunities"] = [opportunity("x", deadline="2026-09-14T16:00:00Z")]
        historical = _compile_plan_at(packet, now=NOW)
        later = NOW.replace(day=15)
        result = _verify_plan_at(packet, historical, now=later)
        self.assertTrue(result["historical_valid"])
        self.assertFalse(result["current_semantics_match"])
        self.assertFalse(result["current_gate_clear"])
        self.assertEqual(result["current_stage"], "NO_ELIGIBLE")


if __name__ == "__main__":
    unittest.main()

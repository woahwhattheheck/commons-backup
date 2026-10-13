# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib
import sys
import types
import unittest
from unittest.mock import patch

import candidate


class FakeInstance:
    def __init__(self, returned):
        self.returned = returned
        self.calls = []
        self.diagnostics = {"status": "completed"}

    def _early_capital_selected(self, observation, configuration, selected):
        self.calls.append((observation, configuration, selected))
        return self.returned


class FakeSettlement:
    def __init__(self, returned, report, events=None):
        self.returned = returned
        self.report = report
        self.calls = []
        self.events = events

    def compose_terminal_settlement(self, observation, configuration, selected, *, project_units):
        if self.events is not None:
            self.events.append("settlement")
        self.calls.append((observation, configuration, selected, project_units))
        return self.returned, self.report


class CandidateTests(unittest.TestCase):
    def setUp(self):
        candidate._LAST_REPORT = None

    def test_public_agent_is_exact_canonical_entrypoint_delegation(self):
        selected = {"market": [], "farmer": ["PASS"], "hands": []}
        calls = []
        canonical = types.SimpleNamespace(
            agent=lambda observation, configuration=None: calls.append(
                (observation, configuration)
            )
            or selected
        )
        candidate._LAST_REPORT = {"stale": True}
        with patch.object(candidate, "_CANONICAL", canonical):
            returned = candidate.agent({"step": 17}, {"episodeSteps": 720})
        self.assertIs(returned, selected)
        self.assertEqual(calls, [({"step": 17}, {"episodeSteps": 720})])
        self.assertIsNone(candidate.last_report())

    def test_nonterminal_installed_seam_is_exact_original_object_and_cold_load_free(self):
        selected = {"market": [], "farmer": ["PASS"], "hands": []}
        instance = candidate._install(FakeInstance(selected))
        with patch.object(
            candidate,
            "_settlement_module",
            side_effect=AssertionError("nonterminal call loaded settlement"),
        ):
            returned = instance._early_capital_selected(
                {"step": 717}, {"episodeSteps": 720}, {"incoming": True}
            )
        self.assertIs(returned, selected)
        self.assertEqual(len(instance.calls), 1)
        self.assertIsNone(candidate.last_report())

    def test_deadline_fallback_terminal_step_preserves_identity_and_stays_cold(self):
        selected = {"market": [], "farmer": ["PASS"], "hands": []}
        instance = candidate._install(FakeInstance(selected))
        diagnostics = {"status": "deadline_fallback", "sentinel": {"keep": True}}
        instance.diagnostics = diagnostics
        candidate._LAST_REPORT = {"stale": True}
        with patch.object(
            candidate,
            "_settlement_module",
            side_effect=AssertionError("deadline fallback loaded settlement"),
        ):
            returned = instance._early_capital_selected(
                {"step": 718}, {"episodeSteps": 720}, {"incoming": True}
            )
        self.assertIs(returned, selected)
        self.assertIs(instance.diagnostics, diagnostics)
        self.assertEqual(instance.diagnostics, {"status": "deadline_fallback", "sentinel": {"keep": True}})
        self.assertIsNone(candidate.last_report())

    def test_final_seam_runs_after_current_early_capital_inside_installed_method(self):
        canonical_return = {
            "market": [["SELL", "WHEAT", 1]],
            "farmer": ["PASS"],
            "hands": [],
        }
        settled = {
            "market": [["SELL", "WHEAT", 2]],
            "farmer": ["PASS"],
            "hands": [],
        }
        report = {"changed": True, "certified": True, "guaranteed_min_cash_gain": 1}
        events = []

        class OrderedInstance(FakeInstance):
            def _early_capital_selected(self, observation, configuration, selected):
                events.append("canonical")
                return super()._early_capital_selected(observation, configuration, selected)

        instance = candidate._install(OrderedInstance(canonical_return))
        settlement = FakeSettlement(settled, report, events)
        projector = object()
        scheduler = types.ModuleType("scheduler")
        scheduler.post_units = projector
        with patch.object(candidate, "_settlement_module", return_value=settlement), patch.dict(
            sys.modules, {"scheduler": scheduler}
        ):
            returned = instance._early_capital_selected(
                {"step": 718}, {"episodeSteps": 720}, {"incoming": True}
            )
        self.assertEqual(events, ["canonical", "settlement"])
        self.assertEqual(returned, settled)
        self.assertIs(settlement.calls[0][2], canonical_return)
        self.assertIs(settlement.calls[0][3], projector)
        self.assertEqual(instance.diagnostics["terminal_settlement"], report)
        detached = candidate.last_report()
        self.assertEqual(detached, report)
        detached["changed"] = False
        self.assertTrue(candidate.last_report()["changed"])

    def test_terminal_exception_propagates_to_canonical_timer_owner(self):
        selected = {"market": [], "farmer": ["PASS"], "hands": []}
        instance = candidate._install(FakeInstance(selected))
        scheduler = types.ModuleType("scheduler")
        scheduler.post_units = lambda *_args: None
        settlement = types.SimpleNamespace(
            compose_terminal_settlement=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("deadline sentinel")
            )
        )
        with patch.object(candidate, "_settlement_module", return_value=settlement), patch.dict(
            sys.modules, {"scheduler": scheduler}
        ):
            with self.assertRaisesRegex(RuntimeError, "deadline sentinel"):
                instance._early_capital_selected(
                    {"step": 718}, {"episodeSteps": 720}, {"incoming": True}
                )

    def test_every_current_reconstruction_is_installed_once(self):
        made = []

        def factory(root, feature_data):
            instance = FakeInstance({"market": []})
            made.append((root, feature_data, instance))
            return instance

        with patch.object(candidate, "_ORIGINAL_NEW_INSTANCE", factory):
            instance = candidate._new_instance("root", {"consumer": "frozen"})
        self.assertTrue(instance._sol_settle_installed)
        first = instance._early_capital_selected
        self.assertIs(candidate._install(instance), instance)
        self.assertIs(instance._early_capital_selected, first)
        self.assertEqual(made[0][:2], ("root", {"consumer": "frozen"}))

    def test_panel_module_imports_exact_current_projector_closure(self):
        # Predecessor run 34520656053 died before game 1 while importing the
        # lab scheduler because observed_clone lives in the canonical source
        # map outside cloud-execution-lab. Importing run_panel is the minimal
        # predecessor-killing contract for that parent-process closure.
        module = importlib.import_module("run_panel")
        self.assertTrue(callable(module.post_units))
        self.assertTrue(module._SOURCE_ROOTS)


if __name__ == "__main__":
    unittest.main()
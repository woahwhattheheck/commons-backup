#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from titan_behavior_equivalence_test_support import *

class ObservationValidationTests(unittest.TestCase):
    def test_distinct_executables_with_identical_complete_effects_are_reported_only(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        report = gate.analyze_equivalence(family, observations)
        self.assertEqual("PASS", report["verdict"])
        aliases = report["observational_behavior_aliases"]
        self.assertEqual(1, len(aliases))
        self.assertEqual(["alpha", "beta"], aliases[0]["candidate_ids"])
        self.assertEqual(2, aliases[0]["distinct_executable_closures"])
        self.assertFalse(aliases[0]["safe_for_retroactive_multiplicity_collapse"])
        self.assertFalse(aliases[0]["safe_for_validation_seed_reuse"])

    def test_exact_executable_duplicates_block_analysis_without_consuming_results(self) -> None:
        family = family_raw(closures=(digest("a"), digest("a")))
        observations = observations_raw(family)
        report = gate.analyze_equivalence(family, observations)
        self.assertEqual("REFUSED_DUPLICATE_EXECUTABLES", report["verdict"])
        self.assertFalse(report["observations_consumed"])

    def test_one_changed_action_breaks_behavior_alias(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        observations["candidates"][1]["cells"][0]["action_tape_sha256"] = digest("0")
        report = gate.analyze_equivalence(family, observations)
        self.assertEqual("PASS", report["verdict"])
        self.assertEqual([], report["observational_behavior_aliases"])
        self.assertEqual(2, report["behavior_class_count"])
        self.assertEqual(1, len(report["score_only_aliases"]))

    def test_equal_actions_with_unequal_world_effects_hold(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        observations["candidates"][1]["cells"][0]["world_tape_sha256"] = digest("0")
        report = gate.analyze_equivalence(family, observations)
        self.assertEqual("HOLD_ACTION_EFFECT_CONTRADICTION", report["verdict"])
        self.assertEqual("EQUAL_ACTIONS_UNEQUAL_EFFECTS", report["action_only_conflicts"][0]["code"])
        self.assertEqual([], report["observational_behavior_aliases"])

    def test_same_scores_with_different_behavior_are_not_collapsed(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        observations["candidates"][1]["cells"][2]["terminal_state_sha256"] = digest("0")
        report = gate.analyze_equivalence(family, observations)
        self.assertEqual("HOLD_ACTION_EFFECT_CONTRADICTION", report["verdict"])
        self.assertEqual(1, len(report["score_only_aliases"]))
        self.assertFalse(report["score_only_aliases"][0]["collapsible"])

    def test_candidate_and_cell_order_do_not_change_signatures(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        expected = gate.analyze_equivalence(family, observations)
        shuffled = copy.deepcopy(observations)
        shuffled["candidates"].reverse()
        for candidate in shuffled["candidates"]:
            candidate["cells"].reverse()
        actual = gate.analyze_equivalence(family, shuffled)
        self.assertEqual(expected["observations_sha256"], actual["observations_sha256"])
        self.assertEqual(expected["candidate_signatures"], actual["candidate_signatures"])
        self.assertEqual(expected["receipt_sha256"], actual["receipt_sha256"])

    def test_missing_candidate_is_rejected(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        observations["candidates"].pop()
        with self.assertRaisesRegex(gate.BehaviorGateError, "omits declared candidates"):
            gate.analyze_equivalence(family, observations)

    def test_wrong_row_archive_or_closure_is_rejected(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        observations["candidates"][0]["cells"][0]["candidate_archive_sha256"] = digest("f")
        with self.assertRaisesRegex(gate.BehaviorGateError, "wrong candidate archive"):
            gate.analyze_equivalence(family, observations)
        observations = observations_raw(family)
        observations["candidates"][0]["cells"][0]["candidate_executable_closure_sha256"] = digest("f")
        with self.assertRaisesRegex(gate.BehaviorGateError, "wrong executable closure"):
            gate.analyze_equivalence(family, observations)
        observations = observations_raw(family)
        observations["candidates"][0]["cells"][0]["candidate_invocation_sha256"] = digest("f")
        with self.assertRaisesRegex(gate.BehaviorGateError, "wrong invocation contract"):
            gate.analyze_equivalence(family, observations)

    def test_one_seat_only_panel_is_rejected(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        for candidate in observations["candidates"]:
            candidate["cells"] = [row for row in candidate["cells"] if row["seat"] == 0]
            candidate["games"] = len(candidate["cells"])
        with self.assertRaisesRegex(gate.BehaviorGateError, "incomplete paired-seat"):
            gate.analyze_equivalence(family, observations)

    def test_panel_schedule_mismatch_is_rejected(self) -> None:
        family = family_raw()
        family["schedule_sha256"] = digest("f")
        observations = observations_raw(family)
        with self.assertRaisesRegex(gate.BehaviorGateError, "schedule mismatch"):
            gate.analyze_equivalence(family, observations)

    def test_candidate_grids_must_be_exactly_equal(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        replacement = copy.deepcopy(observations["candidates"][1]["cells"][0])
        replacement["environment_seed"] = 303
        observations["candidates"][1]["cells"][0] = replacement
        with self.assertRaises(gate.BehaviorGateError):
            gate.analyze_equivalence(family, observations)

    def test_margin_and_outcome_must_be_coherent(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        observations["candidates"][0]["cells"][0]["margin"] += 1
        with self.assertRaisesRegex(gate.BehaviorGateError, "margin contradicts"):
            gate.analyze_equivalence(family, observations)
        observations = observations_raw(family)
        observations["candidates"][0]["cells"][0]["outcome"] = "LOSS"
        with self.assertRaisesRegex(gate.BehaviorGateError, "outcome=.*contradicts"):
            gate.analyze_equivalence(family, observations)

    def test_outcome_sign_is_derived_from_cash_not_tolerated_reported_margin(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        cell = observations["candidates"][0]["cells"][0]
        cell["own_cash"] = cell["rival_cash"]
        cell["margin"] = 1e-12
        cell["outcome"] = "WIN"
        with self.assertRaisesRegex(gate.BehaviorGateError, "cash-derived margin \(TIE\)"):
            gate.analyze_equivalence(family, observations)

        observations = observations_raw(family)
        cell = observations["candidates"][0]["cells"][0]
        cell["own_cash"] = cell["rival_cash"]
        cell["margin"] = 1e-12
        cell["outcome"] = "TIE"
        parsed, _ = gate.validate_observations(observations, gate.validate_family(family))
        self.assertEqual(0.0, parsed[0].cells[common_keys()[0]].margin)

    def test_bool_seed_failed_status_and_games_mismatch_are_rejected(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        observations["candidates"][0]["cells"][0]["environment_seed"] = True
        with self.assertRaisesRegex(gate.BehaviorGateError, "nonnegative integer"):
            gate.analyze_equivalence(family, observations)
        observations = observations_raw(family)
        observations["candidates"][0]["cells"][0]["status"] = "FAILED"
        with self.assertRaisesRegex(gate.BehaviorGateError, "not complete"):
            gate.analyze_equivalence(family, observations)
        observations = observations_raw(family)
        observations["candidates"][0]["games"] += 1
        with self.assertRaisesRegex(gate.BehaviorGateError, "does not equal cells"):
            gate.analyze_equivalence(family, observations)

    def test_declared_observation_digest_must_match(self) -> None:
        family = family_raw()
        observations = observations_raw(family)
        observations["observations_sha256"] = digest("f")
        with self.assertRaisesRegex(gate.BehaviorGateError, "observations_sha256 mismatch"):
            gate.analyze_equivalence(family, observations)

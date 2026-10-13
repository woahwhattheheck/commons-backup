from __future__ import annotations

import copy
import unittest

from support import *
from contract import MECHANISMS, sha256_value
from external_actions import ACTION_BUNDLE_SCHEMA, EXTERNAL_READY, evaluate_external_actions, render_external_markdown, verify_external_result
from market import _trader, synthetic_action


def synthetic_bundle(raw_scenario):
    normalized = validate_scenario(raw_scenario)
    rows = []
    for mechanism in MECHANISMS:
        for trader_row in normalized["traders"]:
            order, _ = synthetic_action(normalized, _trader(trader_row), mechanism)
            rows.append({
                "mechanism": mechanism,
                "action": {
                    "schema": "darpa-dv026-blackbox-action/v1",
                    "order_id": order.order_id,
                    "trader_id": order.trader_id,
                    "side": order.side,
                    "price": order.price,
                    "quantity": order.quantity,
                    "action_step": order.action_step,
                    "observation_sha256": order.observation_sha256,
                },
            })
    return {"schema": ACTION_BUNDLE_SCHEMA, "scenario_sha256": sha256_value(normalized), "actions": rows}


class ExternalActionEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.scenario = load_fixture("scenario_good.json")
        self.bundle = synthetic_bundle(self.scenario)

    def test_evaluates_complete_bundle_without_claiming_external_identity(self):
        result = evaluate_external_actions(self.scenario, self.bundle)
        self.assertEqual(result["status"], EXTERNAL_READY)
        self.assertEqual(len(result["mechanisms"]), 2)
        self.assertTrue(all(item["strictly_above_90_percent"] for item in result["mechanisms"]))
        self.assertTrue(result["authority"]["external_action_file_evaluated"])
        self.assertFalse(result["authority"]["external_llm_execution_proven"])
        self.assertFalse(result["authority"]["model_provider_identity_proven"])
        self.assertFalse(result["authority"]["darpa_phase_i_milestone_proven"])
        self.assertTrue(verify_external_result(self.scenario, self.bundle, result))

    def test_markdown_projects_every_hard_false_external_authority(self):
        markdown = render_external_markdown(evaluate_external_actions(self.scenario, self.bundle))
        for line in (
            "external LLM execution proven: `false`",
            "model/provider identity proven: `false`",
            "DARPA Phase-I milestone proven: `false`",
            "SBIR eligibility proven: `false`",
            "DARPA submission authorized: `false`",
            "award/payment proven: `false`",
        ):
            self.assertIn(line, markdown)

    def test_bundle_order_is_nonsemantic(self):
        first = evaluate_external_actions(self.scenario, self.bundle)
        reordered = copy.deepcopy(self.bundle)
        reordered["actions"].reverse()
        self.assertEqual(first, evaluate_external_actions(self.scenario, reordered))

    def test_missing_action_fails_closed(self):
        broken = copy.deepcopy(self.bundle)
        broken["actions"].pop()
        with self.assertRaisesRegex(ContractError, "exactly"):
            evaluate_external_actions(self.scenario, broken)

    def test_duplicate_mechanism_trader_action_fails_closed(self):
        broken = copy.deepcopy(self.bundle)
        broken["actions"][-1] = copy.deepcopy(broken["actions"][0])
        with self.assertRaises(ContractError):
            evaluate_external_actions(self.scenario, broken)

    def test_scenario_transplant_fails_closed(self):
        broken = copy.deepcopy(self.bundle)
        broken["scenario_sha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "scenario digest mismatch"):
            evaluate_external_actions(self.scenario, broken)

    def test_observation_transplant_fails_closed(self):
        broken = copy.deepcopy(self.bundle)
        broken["actions"][0]["action"]["observation_sha256"] = broken["actions"][1]["action"]["observation_sha256"]
        with self.assertRaisesRegex(ContractError, "observation digest mismatch"):
            evaluate_external_actions(self.scenario, broken)

    def test_mechanism_action_transplant_fails_closed_without_breaking_coverage(self):
        broken = copy.deepcopy(self.bundle)
        first_by_trader = {}
        for index, row in enumerate(broken["actions"]):
            trader_id = row["action"]["trader_id"]
            if trader_id in first_by_trader:
                other = first_by_trader[trader_id]
                broken["actions"][index]["action"], broken["actions"][other]["action"] = (
                    broken["actions"][other]["action"], broken["actions"][index]["action"]
                )
                break
            first_by_trader[trader_id] = index
        with self.assertRaises(ContractError):
            evaluate_external_actions(self.scenario, broken)

    def test_missing_action_field_is_contract_error_not_raw_key_error(self):
        broken = copy.deepcopy(self.bundle)
        del broken["actions"][0]["action"]["action_step"]
        with self.assertRaises(ContractError):
            evaluate_external_actions(self.scenario, broken)

    def test_result_authority_tamper_fails_semantic_recompile(self):
        result = evaluate_external_actions(self.scenario, self.bundle)
        result["authority"]["external_llm_execution_proven"] = True
        self.assertFalse(verify_external_result(self.scenario, self.bundle, result))

    def test_result_canonicalization_failure_is_invalid_not_exception(self):
        result = evaluate_external_actions(self.scenario, self.bundle)
        result["scenario_id"] = "\ud800"
        self.assertFalse(verify_external_result(self.scenario, self.bundle, result))

    def test_economically_bad_actions_are_evidence_not_parser_errors(self):
        broken = copy.deepcopy(self.bundle)
        for row in broken["actions"]:
            action = row["action"]
            action["price"] = 1 if action["side"] == "BUY" else 1_000_000
        result = evaluate_external_actions(self.scenario, broken)
        self.assertNotEqual(result["status"], EXTERNAL_READY)
        self.assertTrue(any(blocker.startswith("EFFICIENCY_GATE:") for blocker in result["blockers"]))


if __name__ == "__main__":
    unittest.main()

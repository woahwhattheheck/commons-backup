from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

from support import *
from contract import MECHANISMS, sha256_value
from external_actions import ACTION_BUNDLE_SCHEMA, evaluate_external_actions
from market import _trader, synthetic_action


def _bundle(raw_scenario):
    scenario = validate_scenario(raw_scenario)
    actions = []
    for mechanism in MECHANISMS:
        for trader_row in scenario["traders"]:
            order, _ = synthetic_action(scenario, _trader(trader_row), mechanism)
            actions.append({"mechanism": mechanism, "action": {
                "schema": "darpa-dv026-blackbox-action/v1",
                "order_id": order.order_id,
                "trader_id": order.trader_id,
                "side": order.side,
                "price": order.price,
                "quantity": order.quantity,
                "action_step": order.action_step,
                "observation_sha256": order.observation_sha256,
            }})
    return {"schema": ACTION_BUNDLE_SCHEMA, "scenario_sha256": sha256_value(scenario), "actions": actions}


class ExternalActionCliTests(unittest.TestCase):
    def test_cli_evaluate_and_verify_actions_in_normal_and_optimized_mode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            actions_path = root / "actions.json"
            result_path = root / "result.json"
            markdown_path = root / "result.md"
            actions_path.write_bytes(canonical_bytes(_bundle(load_fixture("scenario_good.json"))) + b"\n")
            evaluate = [
                sys.executable, str(HERE / "cli.py"), "evaluate-actions",
                "--scenario", str(HERE / "scenario_good.json"), "--actions", str(actions_path),
                "--json-out", str(result_path), "--markdown-out", str(markdown_path),
            ]
            run = subprocess.run(evaluate, check=False, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("EXTERNAL_ACTION_EVALUATION_READY_FOR_OWNER_REVIEW", run.stdout)
            result = loads_strict(result_path.read_bytes())
            self.assertFalse(result["authority"]["external_llm_execution_proven"])
            self.assertFalse(result["authority"]["model_provider_identity_proven"])
            self.assertIn("does not prove", markdown_path.read_text(encoding="utf-8"))

            verify_args = [
                str(HERE / "cli.py"), "verify-actions", "--scenario", str(HERE / "scenario_good.json"),
                "--actions", str(actions_path), "--result", str(result_path),
            ]
            for prefix in ([sys.executable], [sys.executable, "-O"]):
                verify = subprocess.run([*prefix, *verify_args], check=False, capture_output=True, text=True)
                self.assertEqual(verify.returncode, 0, verify.stderr)
                self.assertEqual(verify.stdout.strip(), '{"valid":true}')

    def test_cli_verify_actions_rejects_escaped_surrogate_without_traceback_normal_and_optimized(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scenario = load_fixture("scenario_good.json")
            bundle = _bundle(scenario)
            actions_path = root / "actions.json"
            result_path = root / "result.json"
            actions_path.write_bytes(canonical_bytes(bundle) + b"\n")
            result = evaluate_external_actions(scenario, bundle)
            result["scenario_id"] = "\ud800"
            result_path.write_text(json.dumps(result, ensure_ascii=True), encoding="utf-8")
            args = [
                str(HERE / "cli.py"), "verify-actions", "--scenario", str(HERE / "scenario_good.json"),
                "--actions", str(actions_path), "--result", str(result_path),
            ]
            for prefix in ([sys.executable], [sys.executable, "-O"]):
                run = subprocess.run([*prefix, *args], check=False, capture_output=True, text=True)
                self.assertEqual(run.returncode, 2, run.stderr)
                self.assertEqual(run.stdout.strip(), '{"valid":false}')
                self.assertNotIn("Traceback", run.stderr)

    def test_cli_verify_actions_normalizes_json_integer_resource_error_normal_and_optimized(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            actions_path = root / "actions.json"
            result_path = root / "result.json"
            actions_path.write_bytes(canonical_bytes(_bundle(load_fixture("scenario_good.json"))) + b"\n")
            result_path.write_text('{"x":' + ('9' * 5000) + '}', encoding="utf-8")
            args = [
                str(HERE / "cli.py"), "verify-actions", "--scenario", str(HERE / "scenario_good.json"),
                "--actions", str(actions_path), "--result", str(result_path),
            ]
            for prefix in ([sys.executable], [sys.executable, "-O"]):
                run = subprocess.run([*prefix, *args], check=False, capture_output=True, text=True)
                self.assertEqual(run.returncode, 2, run.stderr)
                self.assertEqual(run.stdout, "")
                self.assertIn("Exceeds the limit", run.stderr)
                self.assertNotIn("Traceback", run.stderr)

    def test_cli_invalid_bundle_fails_without_traceback_in_normal_and_optimized_mode(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            actions_path = root / "actions.json"
            broken = _bundle(load_fixture("scenario_good.json"))
            broken["actions"].pop()
            actions_path.write_bytes(canonical_bytes(broken) + b"\n")
            args = [
                str(HERE / "cli.py"), "evaluate-actions", "--scenario", str(HERE / "scenario_good.json"),
                "--actions", str(actions_path), "--json-out", str(root / "out.json"),
                "--markdown-out", str(root / "out.md"),
            ]
            for prefix in ([sys.executable], [sys.executable, "-O"]):
                run = subprocess.run([*prefix, *args], check=False, capture_output=True, text=True)
                self.assertNotEqual(run.returncode, 0)
                self.assertIn("must contain exactly", run.stderr)
                self.assertNotIn("Traceback", run.stderr)


if __name__ == "__main__":
    unittest.main()

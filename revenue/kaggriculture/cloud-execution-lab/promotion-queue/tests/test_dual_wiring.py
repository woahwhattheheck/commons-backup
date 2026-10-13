# SPDX-License-Identifier: Apache-2.0
"""Dual-predecessor wiring test against the REAL dual_predecessor_gate.py.

Builds two genuinely distinct predecessor bundles (distinct artifact
bytes, distinct panels) plus one shared candidate, then drives the
queue's dual strategy through the actual gate script. This proves the
orchestration satisfies the dual gate's custody, binding, and
cross-comparison contracts without reimplementing any of them.
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVICE_DIR = HERE.parent
GATE_DIR = SERVICE_DIR.parent / "titan-v3-paired-game-gate"

sys.path.insert(0, str(SERVICE_DIR))
sys.path.insert(0, str(GATE_DIR))

from pq.pinning import PinStore  # noqa: E402
from pq.runner import Attempt, load_predecessor_config  # noqa: E402
from test_support import policy, rows  # noqa: E402


def _write_jsonl(path: Path, rows_) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows_) + "\n")


class DualWiringTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.state = self.root / "state"
        baseline, candidate = rows(delta=10.0)
        shifted = copy.deepcopy(baseline)
        for row in shifted:
            row["scores"] = [s + 5.0 for s in row["scores"]]

        self.candidate_games = self.root / "candidate.GAMES.jsonl"
        _write_jsonl(self.candidate_games, candidate)
        self.candidate_artifact = self.root / "candidate.bin"
        self.candidate_artifact.write_bytes(b"candidate-executable-v1")
        self.policy_path = self.root / "policy.json"
        self.policy_path.write_text(json.dumps(policy()))

        self.engine_id = self.root / "engine.json"
        self.engine_id.write_text(json.dumps({"engine": "dual-test"}))
        self.runner_id = self.root / "runner.json"
        self.runner_id.write_text(json.dumps({"runner": "dual-test"}))

        slot_rows = {"a": baseline, "b": shifted}
        slots = {}
        for key, panel in slot_rows.items():
            games = self.root / f"pred-{key}.GAMES.jsonl"
            _write_jsonl(games, panel)
            artifact = self.root / f"pred-{key}.bin"
            artifact.write_bytes(f"predecessor-{key}-executable-v1".encode())
            slots[key] = {
                "name": f"predecessor-{key}",
                "games": str(games),
                "artifact_file": str(artifact),
            }
        config = {
            "schema_version": 1,
            "policy_version": "promotion-policy/v1",
            "engine": {"commit": "a" * 40, "identity_file": str(self.engine_id)},
            "runner": {"commit": "b" * 40, "identity_file": str(self.runner_id)},
            "slots": slots,
        }
        self.config_path = self.root / "predecessors.json"
        self.config_path.write_text(json.dumps(config))

    def tearDown(self):
        self.td.cleanup()

    def _execute(self, strategy):
        pins = PinStore(self.state / "pin-store")
        manifest = pins.pin(
            {
                "candidate_artifact": self.candidate_artifact,
                "candidate_games": self.candidate_games,
                "policy": self.policy_path,
            }
        )
        config = load_predecessor_config(self.config_path)
        policy_value = json.loads(self.policy_path.read_text())
        attempt = Attempt(state_dir=self.state, gate_dir=GATE_DIR)
        return attempt.execute(
            submission_id="pq-dual-test",
            candidate_name="dual-test-candidate",
            pin_manifest=manifest,
            config=config,
            policy=policy_value,
            strategy=strategy,
        )

    def test_dual_strategy_promotes_through_real_dual_gate(self):
        outcome = self._execute(strategy="dual")
        self.assertEqual(outcome["strategy"], "dual")
        self.assertEqual(outcome["verdict"], "PROMOTE")
        self.assertEqual(len(outcome["comparisons"]), 2)
        for comp in outcome["comparisons"]:
            self.assertEqual(comp["strategy"], "dual")
            self.assertEqual(comp["verdict"], "PROMOTE")
            self.assertEqual(comp["exit_code"], 0)
            self.assertEqual(comp["failed_checks"], [])
        # custody receipts were generated per slot and bound in the audit dir
        audit = Path(outcome["audit_dir"])
        receipts = list(audit.glob("*/CUSTODY-RECEIPT.json"))
        self.assertEqual(len(receipts), 2)

    def test_auto_selects_dual_for_distinct_predecessors(self):
        outcome = self._execute(strategy="auto")
        self.assertEqual(outcome["strategy"], "dual")
        self.assertEqual(outcome["verdict"], "PROMOTE")

    def test_auto_selects_paired_when_predecessors_collapse(self):
        # both slots byte-identical: the honest path is two paired runs,
        # not a fabricated dual distinction
        config = json.loads(self.config_path.read_text())
        games_a = config["slots"]["a"]["games"]
        artifact_a = config["slots"]["a"]["artifact_file"]
        config["slots"]["b"]["games"] = games_a
        config["slots"]["b"]["artifact_file"] = artifact_a
        self.config_path.write_text(json.dumps(config))
        outcome = self._execute(strategy="auto")
        self.assertEqual(outcome["strategy"], "paired")
        self.assertEqual(outcome["verdict"], "PROMOTE")
        self.assertEqual(len(outcome["comparisons"]), 2)


if __name__ == "__main__":
    unittest.main()

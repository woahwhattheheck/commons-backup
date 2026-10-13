# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import panel_trigger as trigger
import run_panel as panel


S02_PATHS = (
    ".github/workflows/titan-s02-admission-firewall-materialize.yml",
    "revenue/kaggriculture/cloud-execution-lab/analysis/"
    "s02-admission-firewall-20260909-solpro/.bootstrap/part00.b64",
    "revenue/kaggriculture/cloud-execution-lab/analysis/"
    "s02-admission-firewall-20260909-solpro/BENCHMARK.json",
)
L02_DIR = trigger.CANDIDATE_DIR
REPO_ROOT = Path(__file__).resolve().parents[5]
WORKFLOW = REPO_ROOT / ".github/workflows/titan-v3-l02-ledger-tranche.yml"


class PanelTriggerTests(unittest.TestCase):
    def test_s02_bootstrap_paths_do_not_run_the_panel(self):
        report = trigger.classify(S02_PATHS, event_name="push",
                                  head="3bd90b19f81eeb2cb0c8b5d4c19d31431abcf8d3")
        self.assertFalse(report["run_panel"])
        self.assertEqual(report["executable_hits"], [])
        self.assertIn("unchanged", report["reason"])

    def test_dot_github_paths_keep_their_prefix(self):
        report = trigger.classify(
            [".github/workflows/titan-s02-admission-firewall-materialize.yml"],
            event_name="push")
        self.assertEqual(
            report["changed_paths"],
            [".github/workflows/titan-s02-admission-firewall-materialize.yml"])
        self.assertFalse(report["run_panel"])

    def test_empty_push_does_not_run_the_panel(self):
        self.assertFalse(trigger.panel_required([], event_name="push"))

    def test_unknown_base_fail_closed_runs_the_panel(self):
        report = trigger.classify(S02_PATHS, event_name="push", unknown_base=True)
        self.assertTrue(report["run_panel"])
        self.assertIn("fail-closed", report["reason"])

    def test_branch_creation_zero_base_cannot_collapse_to_tip_parent(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("0000000000000000000000000000000000000000", workflow)
        self.assertIn("unknown=(--unknown-base)", workflow)
        self.assertNotIn("git rev-parse HEAD^", workflow)

    def test_candidate_overlay_or_runner_change_runs_the_panel(self):
        for name in trigger.EXECUTABLE_FILES:
            with self.subTest(name=name):
                self.assertTrue(trigger.panel_required(
                    [f"{L02_DIR}/{name}"], event_name="push"))
                self.assertTrue(trigger.panel_required([name], event_name="push"))

    def test_tests_and_workflow_only_do_not_run_the_panel(self):
        paths = [
            f"{L02_DIR}/test_panel.py",
            f"{L02_DIR}/test_ledger_tranche.py",
            f"{L02_DIR}/test_panel_trigger.py",
            f"{L02_DIR}/panel_trigger.py",
            f"{L02_DIR}/README.md",
            ".github/workflows/titan-v3-l02-ledger-tranche.yml",
        ]
        self.assertFalse(trigger.panel_required(paths, event_name="push"))

    def test_workflow_dispatch_always_runs(self):
        self.assertTrue(trigger.panel_required([], event_name="workflow_dispatch"))
        self.assertTrue(trigger.panel_required(S02_PATHS, event_name="workflow_dispatch"))

    def test_force_overrides_unchanged_paths(self):
        self.assertTrue(trigger.panel_required(S02_PATHS, event_name="push", force=True))

    def test_classify_records_hits_and_scope(self):
        report = trigger.classify(
            [f"{L02_DIR}/ledger_tranche.py", "unrelated.txt"],
            event_name="pull_request", head="abc", base="def")
        self.assertTrue(report["run_panel"])
        self.assertEqual(report["executable_hits"], [f"{L02_DIR}/ledger_tranche.py"])
        self.assertEqual(report["head"], "abc")
        self.assertEqual(report["base"], "def")
        self.assertIn("ADVANCE vs REJECT is unchanged", report["scope"])

    def test_skip_markdown_does_not_claim_advance(self):
        text = trigger.markdown(trigger.classify(S02_PATHS, event_name="push"))
        self.assertIn("Decision: **SKIP**", text)
        self.assertIn("ADVANCE vs REJECT is unchanged", text)
        self.assertNotIn("Verdict: **ADVANCE**", text)

    def test_cli_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "L02-TRIGGER.json"
            markdown = Path(tmp) / "L02-PANEL.md"
            rc = trigger.main([
                "--event", "push",
                "--head", "3bd90b19f81eeb2cb0c8b5d4c19d31431abcf8d3",
                "--changed-file", S02_PATHS[0],
                "--changed-file", S02_PATHS[1],
                "--output", str(output),
                "--markdown", str(markdown),
            ])
            self.assertEqual(rc, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(payload["run_panel"])
            self.assertTrue(markdown.read_text(encoding="utf-8").startswith("# TITAN L02"))

    def test_advance_reject_contract_is_untouched(self):
        global_summary = {"trace_changed_cells": 12, "mean_own_delta": 100,
                          "mean_margin_delta": 120}
        strata = {name: {"mean_own_delta": 1} for name in panel.OPPONENTS}
        self.assertEqual(panel.verdict(global_summary, strata)["decision"], "ADVANCE")
        strata["v1"] = {"mean_own_delta": -1}
        self.assertEqual(panel.verdict(global_summary, strata)["decision"], "REJECT")
        rejected = panel.verdict(
            {"trace_changed_cells": 96, "mean_own_delta": -315.6145833333333,
             "mean_margin_delta": 31.427083333333332},
            {name: {"mean_own_delta": -300} for name in panel.OPPONENTS})
        self.assertEqual(rejected["decision"], "REJECT")
        self.assertFalse(rejected["checks"]["positive_global_own_cash"])


if __name__ == "__main__":
    unittest.main()

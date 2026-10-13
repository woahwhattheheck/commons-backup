#!/usr/bin/env python3
"""Regression: leftover-id census measures the checked-out tree, not stale event SHA."""
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github" / "workflows" / "leftover-id-census.yml"


class LeftoverIdCensusWorkflowHeadTests(unittest.TestCase):
    def test_census_commands_bind_to_checked_out_head(self) -> None:
        yml = WORKFLOW.read_text(encoding="utf-8")
        checked = (
            'python3 host/leftover_id_census.py --check '
            '--sha "$(git rev-parse HEAD)"'
        )
        regenerate = (
            'python3 host/leftover_id_census.py --regenerate-or-alarm '
            '--sha "$(git rev-parse HEAD)"'
        )
        self.assertEqual(yml.count(checked), 2)
        self.assertEqual(yml.count(regenerate), 2)
        self.assertNotIn('--sha "${GITHUB_SHA}"', yml)

    def test_focused_contract_is_watched_and_run_in_both_jobs(self) -> None:
        yml = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('"test_leftover_id_census_workflow_head.py"', yml)
        self.assertEqual(
            yml.count("python3 test_leftover_id_census_workflow_head.py"),
            2,
        )


if __name__ == "__main__":
    unittest.main()

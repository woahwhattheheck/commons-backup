# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import unittest

import causal_ledger as ledger
from support import make_cell, make_panel

class AdmissionTests(unittest.TestCase):
    def test_complete_positive_eight_seed_panel_admits(self):
        report = ledger.analyze_panel(make_panel())
        self.assertEqual(report["verdict"], "ADMIT")
        self.assertEqual(report["overall"]["action_active_cells"], 16)
        self.assertEqual(report["overall"]["score_active_cells"], 16)
        self.assertEqual(report["seed_cluster_summary"]["own_positive_tail_p"], 1 / 256)
        self.assertEqual(report["seed_cluster_summary"]["margin_positive_tail_p"], 1 / 256)
        self.assertTrue(all(row["first_divergence"]["step"] == 0 for row in report["cells"]))

    def test_exactly_inactive_panel_reports_inactive_without_replays(self):
        panel = make_panel(action_changed=False, own_delta=0, rival_delta=0, replays=False)
        report = ledger.analyze_panel(panel)
        self.assertEqual(report["verdict"], "INACTIVE")
        self.assertEqual(report["overall"]["action_active_cells"], 0)
        self.assertEqual(report["overall"]["score_active_cells"], 0)

    def test_action_active_but_score_inactive_rejects(self):
        report = ledger.analyze_panel(
            make_panel(action_changed=True, own_delta=0, rival_delta=0)
        )
        self.assertEqual(report["verdict"], "REJECT")
        self.assertIn("global own mean is not positive", report["gate_failures"])

    def test_four_positive_seed_clusters_are_not_a_five_percent_result(self):
        report = ledger.analyze_panel(make_panel(seeds=[10, 11, 12, 13]))
        self.assertEqual(report["verdict"], "REJECT")
        self.assertEqual(report["seed_cluster_summary"]["own_positive_tail_p"], 1 / 16)
        self.assertIn(
            "seed-cluster own positive-tail significance failed",
            report["gate_failures"],
        )

    def test_one_negative_seed_is_not_hidden_by_positive_global_mean(self):
        panel = make_panel()
        for cell in panel["cells"]:
            if cell["seed"] == 0:
                replacement = make_cell(
                    cell["opponent"],
                    cell["seed"],
                    cell["candidate_seat"],
                    own_delta=-1,
                    rival_delta=-2,
                )
                cell.clear()
                cell.update(replacement)
        report = ledger.analyze_panel(panel)
        self.assertGreater(report["overall"]["own_mean"], 0)
        self.assertEqual(report["verdict"], "REJECT")
        self.assertIn("seed-cluster own lower-tail floor failed", report["gate_failures"])

    def test_negative_opponent_seat_stratum_is_not_masked(self):
        panel = make_panel(opponents=["arlene", "v1"])
        for cell in panel["cells"]:
            if cell["opponent"] == "arlene" and cell["candidate_seat"] == 0:
                replacement = make_cell(
                    "arlene",
                    cell["seed"],
                    0,
                    own_delta=-1,
                    rival_delta=-2,
                )
                cell.clear()
                cell.update(replacement)
        report = ledger.analyze_panel(panel)
        self.assertGreater(report["overall"]["own_mean"], 0)
        self.assertEqual(report["verdict"], "REJECT")
        self.assertIn(
            "negative own mean in opponent=arlene,seat=0",
            report["gate_failures"],
        )

    def test_lost_win_is_explicitly_rejected(self):
        panel = make_panel()
        target = panel["cells"][0]
        replacement = make_cell(
            target["opponent"],
            target["seed"],
            target["candidate_seat"],
            control_own=100,
            control_rival=90,
            own_delta=-20,
            rival_delta=0,
        )
        target.clear()
        target.update(replacement)
        report = ledger.analyze_panel(panel)
        self.assertEqual(report["verdict"], "REJECT")
        self.assertIn("at least one control win was lost", report["gate_failures"])
        self.assertIn("at least one new loss was introduced", report["gate_failures"])


    def test_one_giant_positive_seed_does_not_turn_zero_clusters_into_evidence(self):
        panel = make_panel()
        for cell in panel["cells"]:
            delta = 1000 if cell["seed"] == 0 else 0
            replacement = make_cell(
                cell["opponent"],
                cell["seed"],
                cell["candidate_seat"],
                own_delta=delta,
                rival_delta=0,
            )
            cell.clear()
            cell.update(replacement)
        report = ledger.analyze_panel(panel)
        self.assertGreater(report["overall"]["own_mean"], 0)
        self.assertEqual(report["seed_cluster_summary"]["own_effective_seed_clusters"], 1)
        self.assertEqual(report["seed_cluster_summary"]["own_positive_tail_p"], 0.5)
        self.assertEqual(report["verdict"], "REJECT")

    def test_report_hash_is_stable_and_covers_every_report_field(self):
        first = ledger.analyze_panel(make_panel())
        second = ledger.analyze_panel(make_panel())
        self.assertEqual(first, second)
        claimed = first.pop("report_sha256")
        self.assertEqual(claimed, ledger.digest(first))

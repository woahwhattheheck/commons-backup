# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import unittest

import causal_ledger as ledger
from support import hx, make_game, make_panel

class CausalCustodyTests(unittest.TestCase):
    def test_score_change_without_tested_action_change_fails(self):
        panel = make_panel(action_changed=False, own_delta=1, rival_delta=0)
        with self.assertRaisesRegex(ledger.EvidenceError, "first tested-seat action"):
            ledger.analyze_panel(panel)

    def test_changed_action_must_change_next_world(self):
        panel = make_panel()
        cell = panel["cells"][0]
        candidate = make_game(
            opponent=cell["opponent"],
            seed=cell["seed"],
            seat=cell["candidate_seat"],
            arm="candidate",
            own=110,
            rival=88,
            action_changed=True,
            realized=False,
        )
        cell["candidate"] = {"primary": candidate, "replay": deepcopy(candidate)}
        with self.assertRaisesRegex(ledger.EvidenceError, "did not change the next world"):
            ledger.analyze_panel(panel)

    def test_rival_action_must_match_at_first_divergence(self):
        panel = make_panel()
        cell = panel["cells"][0]
        candidate = make_game(
            opponent=cell["opponent"],
            seed=cell["seed"],
            seat=cell["candidate_seat"],
            arm="candidate",
            own=110,
            rival=88,
            action_changed=True,
            rival_changed=True,
        )
        cell["candidate"] = {"primary": candidate, "replay": deepcopy(candidate)}
        with self.assertRaisesRegex(ledger.EvidenceError, "rival action differs"):
            ledger.analyze_panel(panel)

    def test_preworld_must_match_at_first_divergence(self):
        panel = make_panel()
        cell = panel["cells"][0]
        candidate = make_game(
            opponent=cell["opponent"],
            seed=cell["seed"],
            seat=cell["candidate_seat"],
            arm="candidate",
            own=110,
            rival=88,
            action_changed=True,
            preworld_changed=True,
        )
        cell["candidate"] = {"primary": candidate, "replay": deepcopy(candidate)}
        with self.assertRaisesRegex(ledger.EvidenceError, "identical preworld"):
            ledger.analyze_panel(panel)

    def test_active_cell_requires_both_replays(self):
        panel = make_panel()
        panel["cells"][0]["candidate"]["replay"] = None
        with self.assertRaisesRegex(ledger.EvidenceError, "requires both deterministic replays"):
            ledger.analyze_panel(panel)

    def test_replay_must_be_byte_deterministic(self):
        panel = make_panel()
        replay = panel["cells"][0]["candidate"]["replay"]
        replay["steps"][1]["observations"][0]["extra"] = True
        with self.assertRaisesRegex(ledger.EvidenceError, "replay is not byte-deterministic"):
            ledger.analyze_panel(panel)

    def test_logical_game_identity_prevents_cell_relabeling(self):
        panel = make_panel()
        panel["cells"][0]["control"]["primary"]["identity"]["seed"] = 999
        with self.assertRaisesRegex(ledger.EvidenceError, "identity is detached"):
            ledger.analyze_panel(panel)

    def test_panel_provenance_prevents_per_cell_evaluator_drift(self):
        panel = make_panel()
        panel["cells"][0]["candidate"]["primary"]["provenance"]["evaluator_sha256"] = hx("9")
        with self.assertRaisesRegex(ledger.EvidenceError, "detached from the panel closure"):
            ledger.analyze_panel(panel)

    def test_money_and_scores_must_be_integers_not_floats(self):
        panel = make_panel()
        game = panel["cells"][0]["candidate"]["primary"]
        game["steps"][1]["bank"] = [110.0, 88.0]
        game["terminal_bank"] = [110.0, 88.0]
        game["scores"] = [110.0, 88.0]
        panel["cells"][0]["candidate"]["replay"] = deepcopy(game)
        with self.assertRaisesRegex(ledger.EvidenceError, "must be an integer"):
            ledger.analyze_panel(panel)

    def test_seed_bank_digest_binds_topology(self):
        panel = make_panel()
        panel["experiment"]["seed_bank_sha256"] = hx("8")
        with self.assertRaisesRegex(ledger.EvidenceError, "bind the exact panel grid"):
            ledger.analyze_panel(panel)

    def test_rerun_attempt_is_rejected(self):
        panel = make_panel()
        panel["experiment"]["run_attempt"] = 2
        with self.assertRaisesRegex(ledger.EvidenceError, "run_attempt 1"):
            ledger.analyze_panel(panel)


    def test_observations_must_match_at_first_divergence(self):
        panel = make_panel()
        candidate = panel["cells"][0]["candidate"]["primary"]
        candidate["steps"][0]["observations"][0]["drift"] = True
        panel["cells"][0]["candidate"]["replay"] = deepcopy(candidate)
        with self.assertRaisesRegex(ledger.EvidenceError, "identical observations"):
            ledger.analyze_panel(panel)

    def test_hidden_prefix_drift_before_tested_action_is_rejected(self):
        panel = make_panel(action_changed=False, own_delta=0, rival_delta=0)
        cell = panel["cells"][0]
        candidate = make_game(
            opponent=cell["opponent"],
            seed=cell["seed"],
            seat=cell["candidate_seat"],
            arm="candidate",
            own=100,
            rival=90,
            action_changed=False,
            prefix_drift=True,
        )
        cell["candidate"] = {"primary": candidate, "replay": deepcopy(candidate)}
        with self.assertRaisesRegex(ledger.EvidenceError, "diverged before"):
            ledger.analyze_panel(panel)

    def test_same_runtime_tree_cannot_masquerade_as_two_arms(self):
        panel = make_panel()
        panel["provenance"]["candidate_runtime_tree_sha256"] = panel["provenance"][
            "control_runtime_tree_sha256"
        ]
        with self.assertRaisesRegex(ledger.EvidenceError, "runtime-tree digests must differ"):
            ledger.analyze_panel(panel)

    def test_missing_grid_cell_is_rejected(self):
        panel = make_panel()
        panel["cells"].pop()
        with self.assertRaisesRegex(ledger.EvidenceError, "exact grid"):
            ledger.analyze_panel(panel)

    def test_duplicate_cell_key_is_rejected(self):
        panel = make_panel()
        panel["cells"][-1] = deepcopy(panel["cells"][0])
        with self.assertRaisesRegex(ledger.EvidenceError, "duplicate cell key"):
            ledger.analyze_panel(panel)

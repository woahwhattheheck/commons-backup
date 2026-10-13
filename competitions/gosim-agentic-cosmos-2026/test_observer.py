from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from demo import fixture_snapshot, replay_fixture
from observer import ContractError, default_policy, choose_action, strict_json_loads, verify_decision
from package import build as build_package
from replay import run_replay


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.s = fixture_snapshot()
        self.p = default_policy()

    def test_acceptance_decision_verifies(self):
        r = choose_action(self.s, self.p)
        self.assertTrue(verify_decision(r, self.s, self.p))
        self.assertFalse(r["official_score_claimed"])
        self.assertFalse(r["submission_claimed"])
        self.assertEqual(r["causal_boundary"], "CURRENT_OBSERVATIONS_PLUS_EXPLICIT_FORECASTS_ONLY")

    def test_deterministic_order_independent_candidates(self):
        a = choose_action(self.s, self.p)
        s = copy.deepcopy(self.s); s["candidates"].reverse()
        b = choose_action(s, self.p)
        self.assertEqual(a, b)

    def test_exact_900_seconds_required(self):
        s = copy.deepcopy(self.s); s["tick_seconds"] = 899
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_bool_tick_rejected(self):
        s = copy.deepcopy(self.s); s["tick_index"] = True
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_future_realized_field_rejected(self):
        s = copy.deepcopy(self.s); s["candidates"][0]["forecast"][0]["realized_success"] = True
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_unknown_snapshot_field_rejected(self):
        s = copy.deepcopy(self.s); s["official_rank"] = 1
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_duplicate_candidate_rejected(self):
        s = copy.deepcopy(self.s); s["candidates"].append(copy.deepcopy(s["candidates"][0]))
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_forecast_offset_duplicate_rejected(self):
        s = copy.deepcopy(self.s); s["candidates"][0]["forecast"][1]["offset_ticks"] = 1
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_forecast_beyond_policy_horizon_rejected(self):
        p = dict(self.p, horizon_ticks=2)
        with self.assertRaises(ContractError): choose_action(self.s, p)

    def test_history_future_tick_rejected(self):
        s = copy.deepcopy(self.s); s["recent_observations"][0]["tick_index"] = s["tick_index"]
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_history_unsorted_rejected(self):
        s = copy.deepcopy(self.s); s["recent_observations"].reverse()
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_secret_shaped_target_rejected(self):
        s = copy.deepcopy(self.s); s["candidates"][0]["target_id"] = "token=abcdef"
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_email_shaped_episode_rejected(self):
        s = copy.deepcopy(self.s); s["episode_id"] = "person@example.test"
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_float_budget_rejected(self):
        s = copy.deepcopy(self.s); s["remaining_budget"] = 100.0
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_probability_over_ppm_rejected(self):
        s = copy.deepcopy(self.s); s["candidates"][0]["now"]["visibility_ppm"] = 1000001
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_no_budget_idles(self):
        s = copy.deepcopy(self.s); s["remaining_budget"] = 0
        r = choose_action(s, self.p)
        self.assertEqual(r["action"], {"kind": "IDLE", "target_id": None})

    def test_all_unavailable_idles(self):
        s = copy.deepcopy(self.s)
        for c in s["candidates"]:
            c["now"]["available"] = False
            for f in c["forecast"]: f["available"] = False
        r = choose_action(s, self.p)
        self.assertEqual(r["action"]["kind"], "IDLE")

    def test_policy_tamper_changes_receipt(self):
        r = choose_action(self.s, self.p)
        self.assertFalse(verify_decision(r, self.s, dict(self.p, new_tag_bonus=self.p["new_tag_bonus"] + 1)))

    def test_snapshot_tamper_changes_receipt(self):
        r = choose_action(self.s, self.p)
        s = copy.deepcopy(self.s); s["remaining_budget"] -= 1
        self.assertFalse(verify_decision(r, s, self.p))

    def test_receipt_tamper_rejected(self):
        r = choose_action(self.s, self.p); r["official_score_claimed"] = True
        self.assertFalse(verify_decision(r, self.s, self.p))

    def test_replay_foundation_truth(self):
        snapshots, outcomes, p = replay_fixture()
        r = run_replay(snapshots, outcomes, p)
        self.assertTrue(r["foundation_evaluation_only"])
        self.assertFalse(r["official_score_claimed"])
        self.assertEqual(r["ticks"], 4)

    def test_replay_missing_chosen_outcome_fails(self):
        snapshots, outcomes, p = replay_fixture()
        chosen = choose_action(snapshots[0], p)["action"]
        outcomes = [o for o in outcomes if not (o["tick_index"] == snapshots[0]["tick_index"] and o["target_id"] == chosen["target_id"])]
        with self.assertRaises(ContractError): run_replay(snapshots, outcomes, p)

    def test_replay_cross_episode_transplant_fails(self):
        snapshots, outcomes, p = replay_fixture(); snapshots[1]["episode_id"] = "OTHER"
        with self.assertRaises(ContractError): run_replay(snapshots, outcomes, p)

    def test_replay_noncontiguous_ticks_fails(self):
        snapshots, outcomes, p = replay_fixture(); snapshots[1]["tick_index"] += 2
        with self.assertRaises(ContractError): run_replay(snapshots, outcomes, p)

    def test_duplicate_outcome_key_fails(self):
        snapshots, outcomes, p = replay_fixture(); outcomes.append(copy.deepcopy(outcomes[0]))
        with self.assertRaises(ContractError): run_replay(snapshots, outcomes, p)

    def test_outcome_unknown_field_fails(self):
        snapshots, outcomes, p = replay_fixture(); outcomes[0]["weather"] = "clear"
        with self.assertRaises(ContractError): run_replay(snapshots, outcomes, p)

    def test_json_duplicate_key_rejected(self):
        with self.assertRaises(ContractError): strict_json_loads('{"a":1,"a":2}')

    def test_json_nonfinite_rejected(self):
        with self.assertRaises(ContractError): strict_json_loads('{"a":NaN}')

    def test_policy_bool_horizon_rejected(self):
        with self.assertRaises(ContractError): choose_action(self.s, dict(self.p, horizon_ticks=True))

    def test_policy_excessive_beam_rejected(self):
        with self.assertRaises(ContractError): choose_action(self.s, dict(self.p, beam_width=999999))


    def test_replay_timestamp_cadence_fails_closed(self):
        snapshots, outcomes, p = replay_fixture(); snapshots[1]["timestamp_utc"] = "2026-09-15T00:16:00Z"
        with self.assertRaises(ContractError): run_replay(snapshots, outcomes, p)

    def test_planned_new_tag_bonus_is_not_reawarded_forever(self):
        p = dict(self.p, horizon_ticks=4, new_tag_bonus=1000000, repeat_penalty=0, revisit_bonus_cap=0, revisit_bonus_per_tick=0)
        r = choose_action(self.s, p)
        # A new-tag target may be selected, but the planner must not treat that tag
        # as new on every future occurrence; receipt remains deterministic/verifiable.
        self.assertTrue(verify_decision(r, self.s, p))
        self.assertEqual(len(r["planned_schedule"]), 4)

    def test_bad_timestamp_rejected(self):
        s = copy.deepcopy(self.s); s["timestamp_utc"] = "2026-09-15T00:00:00+00:00"
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_history_duplicate_tags_rejected(self):
        s = copy.deepcopy(self.s); s["recent_observations"][0]["tags"] = ["X", "X"]
        with self.assertRaises(ContractError): choose_action(s, self.p)

    def test_package_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = build_package(Path(tmp) / "a"); b = build_package(Path(tmp) / "b")
            self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()

"""Synthetic contract tests; these are not real TITAN/engine games."""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

import gauntlet_audit as ga

PYTHON = [sys.executable] + (["-O"] if sys.flags.optimize else [])


def panel():
    d = {"schema": "titan.gauntlet.paired.v1",
         "artifacts": {"baseline": "a"*64, "candidate": "b"*64},
         "engine_sha256": "e"*64, "expected_callbacks": 3,
         "opponents": [{"id": "synthetic-rival", "kind": "recorded_trace"}],
         "cells": [], "games": []}
    for seed in (11, 12):
        for seat in (0, 1):
            cell = {"id": f"{seed}/{seat}", "opponent_id": "synthetic-rival",
                    "seed": seed, "seat": seat, "replicate": 0,
                    "split": "holdout", "opponent_sha256": "c"*64}
            d["cells"].append(cell)
            for arm in ga.ARMS:
                bank = [120, 100] if arm == "baseline" else [130, 125]
                # Same own/rival values in both seats: own+10, rival+25, margin-15.
                if seat == 1:
                    bank.reverse()
                d["games"].append({"cell_id": cell["id"],
                    **{k: v for k, v in cell.items() if k != "id"},
                    "arm": arm, "agent_sha256": d["artifacts"][arm],
                    "engine_sha256": d["engine_sha256"], "status": "complete",
                    "completed_callbacks": 3, "fallbacks": 0, "banks": bank})
    return d


def summary():
    return {"schema": "titan.gauntlet.summary.v1", "source": "synthetic-fixture",
            "candidate_label": "synthetic-not-gameplay", "opponents": [
                {"id": "weak", "kind": "recorded_trace", "wins": 2, "losses": 4,
                 "draws": 0, "reported_total_margin": "−20k", "approximate": True},
                {"id": "milk", "kind": "archetype", "wins": 1, "losses": 5,
                 "draws": 0, "reported_total_margin": "-53", "approximate": False},
                {"id": "wheat", "kind": "archetype", "wins": 6, "losses": 0,
                 "draws": 0, "reported_total_margin": "+4.8k", "approximate": True},
                {"id": "mirror", "kind": "mirror", "wins": 1, "losses": 1,
                 "draws": 4, "reported_total_margin": "0", "approximate": False}],
            "declared_totals": {"wins": 10, "losses": 10, "draws": 4, "games": 24}}


class AuditTests(unittest.TestCase):
    def test_paired_margin_not_own_bank_gain(self):
        r = ga.audit(panel())
        self.assertTrue(r["runtime_clean"])
        self.assertEqual(r["complete_pairs"], 4)
        self.assertEqual({p["delta_margin"] for p in r["pairs"]}, {-15})
        self.assertEqual({p["delta_own"] for p in r["pairs"]}, {10})
        self.assertEqual({p["delta_rival"] for p in r["pairs"]}, {25})
        self.assertEqual(r["promotion_decision"], "NOT_ASSESSED")

    def test_seed_not_replicate_or_seat_independence(self):
        r = ga.audit(panel())["groups"][0]
        self.assertEqual(r["seed_clusters"], 2)
        self.assertEqual(r["delta_margin"]["n"], 4)
        self.assertEqual([s["pairs"] for s in r["seed_cluster_means"]], [2, 2])

    def test_1000_cash_algebra_trials_both_seats(self):
        rng = random.Random(9600911)
        for trial in range(1000):
            d = panel()
            for seed in (11, 12):
                a, b, x, y = [rng.randrange(200_000) for _ in range(4)]
                for game in d["games"]:
                    if game["seed"] == seed:
                        bank = [a, b] if game["arm"] == "baseline" else [x, y]
                        game["banks"] = bank if game["seat"] == 0 else bank[::-1]
            r = ga.audit(d)
            for p in r["pairs"]:
                aa = next(g for g in d["games"] if g["cell_id"] == p["id"] and g["arm"] == "baseline")
                bb = next(g for g in d["games"] if g["cell_id"] == p["id"] and g["arm"] == "candidate")
                seat = p["seat"]
                expected = (bb["banks"][seat] - bb["banks"][1-seat]) - (aa["banks"][seat] - aa["banks"][1-seat])
                self.assertEqual(p["delta_margin"], expected, (trial, seat))

    def test_new_loss_lost_win_and_mirror_separation(self):
        d = panel()
        d["opponents"][0]["kind"] = "mirror"
        d["games"][1]["banks"] = [99, 100]
        r = ga.audit(d)
        self.assertEqual(r["groups"][0]["new_losses"], 1)
        self.assertEqual(r["groups"][0]["lost_wins"], 1)
        self.assertEqual(r["groups"][0]["kind"], "mirror")

    def test_missing_row_blocks_coverage(self):
        d = panel(); d["games"].pop()
        r = ga.audit(d)
        self.assertFalse(r["coverage_complete"])
        self.assertEqual(len(r["missing"]), 1)
        self.assertEqual(r["complete_pairs"], 3)

    def test_no_games_never_passes(self):
        d = panel(); d["games"] = []
        r = ga.audit(d)
        self.assertFalse(r["runtime_clean"])
        self.assertEqual(len(r["missing"]), 8)

    def test_failed_and_incomplete_games_not_zero_gain(self):
        for status in ("error", "timeout", "incomplete"):
            with self.subTest(status=status):
                d = panel(); d["games"][0].update(status=status, completed_callbacks=2, banks=None)
                r = ga.audit(d)
                self.assertFalse(r["coverage_complete"])
                self.assertEqual(r["complete_pairs"], 3)
                self.assertEqual(r["failed"][0]["status"], status)

    def test_fallbacks_retained_in_economics_but_not_runtime_green(self):
        d = panel(); d["games"][0]["fallbacks"] = 1
        r = ga.audit(d)
        self.assertTrue(r["coverage_complete"])
        self.assertFalse(r["runtime_clean"])
        self.assertEqual(r["complete_pairs"], 4)
        self.assertEqual(r["fallbacks"][0]["count"], 1)

    def test_duplicate_result_is_error_not_last_wins(self):
        d = panel(); d["games"].append(copy.deepcopy(d["games"][0]))
        with self.assertRaisesRegex(ga.AuditError, "duplicate result"):
            ga.audit(d)

    def test_source_and_coordinate_drift_rejected(self):
        changes = {"agent_sha256": "f"*64, "engine_sha256": "f"*64,
                   "opponent_sha256": "f"*64, "seed": 99, "seat": 1,
                   "replicate": 2, "split": "tuning", "opponent_id": "other"}
        for field, value in changes.items():
            with self.subTest(field=field):
                d = panel(); d["games"][0][field] = value
                with self.assertRaises(ga.AuditError): ga.audit(d)

    def test_bool_float_string_integers_not_coerced(self):
        for field in ("seed", "seat", "replicate", "fallbacks", "completed_callbacks"):
            for value in (True, 1.0, "1"):
                with self.subTest(field=field, value=value):
                    d = panel(); d["games"][0][field] = value
                    with self.assertRaises(ga.AuditError): ga.audit(d)

    def test_banks_finite_exact_two_integers(self):
        for value in (None, [1], [1, 2, 3], [True, 2], [1.0, 2], [float('nan'), 2], [float('inf'), 2]):
            with self.subTest(value=value):
                d = panel(); d["games"][0]["banks"] = value
                with self.assertRaises(ga.AuditError): ga.audit(d)

    def test_false_complete_and_impossible_fallbacks_rejected(self):
        for change in ({"completed_callbacks": 2}, {"completed_callbacks": 4}, {"fallbacks": 4}, {"status": "success"}):
            d = panel(); d["games"][0].update(change)
            with self.assertRaises(ga.AuditError): ga.audit(d)

    def test_duplicate_plan_and_unplanned_games(self):
        d = panel(); d["cells"].append(copy.deepcopy(d["cells"][0]))
        with self.assertRaisesRegex(ga.AuditError, "duplicate cell"): ga.audit(d)
        d = panel(); d["cells"].append({**d["cells"][0], "id": "new-name"})
        with self.assertRaisesRegex(ga.AuditError, "duplicate planned"): ga.audit(d)
        d = panel(); d["games"][0]["cell_id"] = "unknown"
        with self.assertRaisesRegex(ga.AuditError, "unplanned"): ga.audit(d)

    def test_unbalanced_plan_and_missing_opponent_rejected(self):
        d = panel(); d["cells"].pop()
        with self.assertRaisesRegex(ga.AuditError, "balanced"): ga.audit(d)
        d = panel(); d["opponents"].append({"id": "unrun", "kind": "live_agent"})
        with self.assertRaisesRegex(ga.AuditError, "missing from plan"): ga.audit(d)

    def test_tuning_holdout_overlap_rejected(self):
        d = panel()
        for c in d["cells"]:
            if c["seed"] == 12: c.update(seed=11, split="tuning")
        with self.assertRaisesRegex(ga.AuditError, "overlap"): ga.audit(d)

    def test_cross_opponent_seed_leakage_rejected(self):
        d = panel()
        d["opponents"].append({"id": "second-rival", "kind": "archetype"})
        for c in d["cells"]:
            if c["seed"] == 12:
                c.update(seed=11, opponent_id="second-rival", split="tuning")
        with self.assertRaisesRegex(ga.AuditError, "overlap"):
            ga.audit(d)

    def test_wholly_missing_groups_remain_visible(self):
        d = panel(); d["games"] = []
        r = ga.audit(d)
        self.assertEqual(len(r["groups"]), 1)
        self.assertEqual(r["groups"][0]["expected_pairs"], 4)
        self.assertEqual(r["groups"][0]["observed_pairs"], 0)
        self.assertIsNone(r["groups"][0]["delta_margin"]["mean"])
        self.assertFalse(r["coverage_complete"])

    def test_tuning_holdout_separate(self):
        d = panel()
        for c in d["cells"]:
            if c["seed"] == 11: c["split"] = "tuning"
        for g in d["games"]:
            if g["seed"] == 11: g["split"] = "tuning"
        self.assertEqual({g["split"] for g in ga.audit(d)["groups"]}, {"holdout", "tuning"})

    def test_order_invariant_and_input_not_mutated(self):
        d = panel(); before = copy.deepcopy(d)
        r = ga.audit(d)
        self.assertEqual(d, before)
        d["games"].reverse(); d["cells"].reverse()
        self.assertEqual(r, ga.audit(d))

    def test_summary_rank_not_three_losers(self):
        r = ga.audit(summary())
        self.assertEqual([x["id"] for x in r["weakest_nonmirror"]], ["weak", "milk", "wheat"])
        self.assertEqual([x["net_losing"] for x in r["weakest_nonmirror"]], [True, True, False])
        self.assertEqual(r["totals"]["games"], 24)
        self.assertFalse(r["paired_evidence_available"])
        self.assertEqual(r["promotion_decision"], "NOT_ASSESSED")
        self.assertEqual(len(r["mirror_controls"]), 1)

    def test_summary_totals_must_reconcile(self):
        d = summary(); d["declared_totals"]["wins"] += 1
        with self.assertRaisesRegex(ga.AuditError, "mismatch"): ga.audit(d)

    def test_summary_abbreviations_always_approximate(self):
        d = summary(); d["opponents"][0]["approximate"] = False
        self.assertTrue(ga.audit(d)["weakest_nonmirror"][0]["approximate"])

    def test_summary_invalid_numbers_duplicates_empty_rejected(self):
        for value in ("NaN", "Infinity", "1e20", "twenty", "", "01", "1kk"):
            with self.subTest(value=value):
                d = summary(); d["opponents"][0]["reported_total_margin"] = value
                with self.assertRaises(ga.AuditError): ga.audit(d)
        d = summary(); d["opponents"].append(copy.deepcopy(d["opponents"][0]))
        with self.assertRaisesRegex(ga.AuditError, "duplicate"): ga.audit(d)
        for d in ({}, [], {"schema": "titan.gauntlet.paired.v1"}, {"schema": "titan.gauntlet.summary.v1"}):
            with self.assertRaises(ga.AuditError): ga.audit(d)

    def test_cli_exit_codes_hash_and_output(self):
        with tempfile.TemporaryDirectory() as td:
            p, o = Path(td)/"input.json", Path(td)/"report.json"
            for d, code in ((panel(), 0), (summary(), 3)):
                p.write_text(json.dumps(d), encoding="utf-8")
                cp = subprocess.run(PYTHON + [str(Path(ga.__file__)), str(p), "--output", str(o)], capture_output=True)
                self.assertEqual(cp.returncode, code, cp.stderr)
                r = json.loads(o.read_text())
                self.assertEqual(r["input_sha256"], ga.hashlib.sha256(p.read_bytes()).hexdigest())
            d = panel(); d["games"].pop(); p.write_text(json.dumps(d))
            self.assertEqual(ga.main([str(p), "--output", str(o)]), 1)

    def test_cli_bad_json_and_input_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            p, o = Path(td)/"input.json", Path(td)/"report.json"
            for invalid in ('{"schema":"x","schema":"y"}', '{"x":NaN}', '{"x":Infinity}', '[]', '{}'):
                p.write_text(invalid)
                cp = subprocess.run(PYTHON + [str(Path(ga.__file__)), str(p), "--output", str(o)], capture_output=True)
                self.assertEqual(cp.returncode, 2, cp.stderr)
                self.assertFalse(o.exists())
            p.write_text(json.dumps(panel())); before = p.read_bytes()
            cp = subprocess.run(PYTHON + [str(Path(ga.__file__)), str(p), "--output", str(p)], capture_output=True)
            self.assertEqual(cp.returncode, 2)
            self.assertEqual(p.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

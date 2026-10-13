"""Run against real hash-pinned reporter bytes; no scorer test double."""
from copy import deepcopy
import contextlib
from dataclasses import replace
import io
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

import paired_field_gate as gate


def fixture(counts=None, deltas=None):
    counts = {"mirror": 8, "dairy": 8} if counts is None else counts
    deltas = {} if deltas is None else deltas
    panel = {"schema_version": 1, "opponents": {n: list(range(c)) for n, c in counts.items()}}
    rows = []
    for name, seeds in panel["opponents"].items():
        for seed in seeds:
            for seat in (0, 1):
                delta = deltas.get((name, seat), deltas.get(name, 1))
                rows.append({"opponent": name, "seed": seed, "candidate_seat": seat,
                             "baseline": {"own": 1000, "rival": 900},
                             "candidate": {"own": 1000 + delta, "rival": 900}})
    return rows, panel


class FieldTests(unittest.TestCase):
    def test_real_dependency_is_exact(self):
        self.assertEqual(gate.git_blob(gate.DEFAULT_REPORTER.read_bytes()), gate.REPORTER_BLOB)

    def test_all_improvement_passes_exact_boundary(self):
        rows, panel = fixture()
        out = gate.evaluate(rows, panel)
        self.assertEqual(out["verdict"], "PASS")
        self.assertEqual(out["coverage"]["actual_cells"], 32)
        self.assertEqual(out["opponent_balanced_mean_delta_m"], 1)

    def test_pooled_positive_masks_field_regression(self):
        rows, panel = fixture({"mirror": 32, "dairy": 8}, {"mirror": 10, "dairy": -30})
        out = gate.evaluate(rows, panel)
        self.assertEqual(out["pooled_mean_delta_m"], 2)
        self.assertEqual(out["opponent_balanced_mean_delta_m"], -10)
        self.assertEqual(out["verdict"], "FAIL")
        self.assertEqual(out["distribution"]["outcomes"]["new_losses"], [])
        # Predecessor's pooled default policy would pass this exact witness.
        predecessor = gate.load_reporter()
        self.assertEqual(predecessor.policy_failures(out["distribution"], min_mean_delta=0), [])

    def test_positive_balanced_gain_still_cannot_hide_bad_opponent(self):
        rows, panel = fixture(deltas={"mirror": 40, "dairy": -10})
        out = gate.evaluate(rows, panel)
        self.assertGreater(out["opponent_balanced_mean_delta_m"], 0)
        self.assertEqual(out["verdict"], "FAIL")
        self.assertTrue(any("dairy:" in f for f in out["failures"]))

    def test_seat_pair_gain_cannot_hide_losing_seat(self):
        rows, panel = fixture(deltas={("mirror", 0): 100, ("mirror", 1): -10})
        out = gate.evaluate(rows, panel)
        self.assertGreater(out["by_opponent"]["mirror"]["mean_delta_m"], 0)
        self.assertTrue(any("mirror/seat1:" in f for f in out["failures"]))
        self.assertEqual(out["verdict"], "FAIL")

    def test_one_opponent_is_not_default_field(self):
        rows, panel = fixture({"mirror": 8})
        self.assertEqual(gate.evaluate(rows, panel)["verdict"], "FAIL")

    def test_missing_opponent_is_bad_data(self):
        rows, panel = fixture()
        with self.assertRaisesRegex(gate.DataError, "coverage"):
            gate.evaluate([r for r in rows if r["opponent"] != "dairy"], panel)

    def test_missing_seat_is_bad_data(self):
        rows, panel = fixture()
        with self.assertRaisesRegex(gate.DataError, "coverage"):
            gate.evaluate(rows[:-1], panel)

    def test_missing_seed_pair_is_bad_data(self):
        rows, panel = fixture()
        with self.assertRaisesRegex(gate.DataError, "coverage"):
            gate.evaluate(rows[:-2], panel)

    def test_unexpected_cell_is_bad_data(self):
        rows, panel = fixture()
        extra = deepcopy(rows[0]); extra["seed"] = 999
        with self.assertRaisesRegex(gate.DataError, "coverage"):
            gate.evaluate(rows + [extra], panel)

    def test_duplicate_logical_cell_is_bad_data(self):
        rows, panel = fixture()
        extra = deepcopy(rows[0]); extra["seed"] = str(extra["seed"])
        with self.assertRaisesRegex(gate.DataError, "duplicate"):
            gate.evaluate(rows + [extra], panel)

    def test_insufficient_planned_pairs_fails_policy(self):
        rows, panel = fixture({"mirror": 7, "dairy": 8})
        out = gate.evaluate(rows, panel)
        self.assertEqual(out["verdict"], "FAIL")
        self.assertTrue(any("7 seed pairs < 8" in f for f in out["failures"]))

    def test_panel_seed_alias_collisions(self):
        rows, panel = fixture()
        panel["opponents"]["mirror"].append(" 0 ")
        with self.assertRaisesRegex(gate.DataError, "duplicate"):
            gate.evaluate(rows, panel)

    def test_panel_opponent_name_collisions(self):
        rows, panel = fixture()
        panel["opponents"][" mirror "] = [0]
        with self.assertRaisesRegex(gate.DataError, "duplicate"):
            gate.evaluate(rows, panel)

    def test_bad_panel_shapes(self):
        rows, good = fixture()
        bad = [None, [], {}, {**good, "schema_version": True},
               {**good, "extra": 1}, {**good, "opponents": {}},
               {"schema_version": 1, "opponents": {"x": [True]}},
               {"schema_version": 1, "opponents": {"x": [1.5]}},
               {"schema_version": 1, "opponents": {"x": [""]}}]
        for panel in bad:
            with self.subTest(panel=panel), self.assertRaises(gate.DataError):
                gate.evaluate(rows, panel)

    def test_own_gain_not_competitive_gain(self):
        rows, panel = fixture()
        for row in rows:
            row["candidate"] = {"own": 1100, "rival": 1100}
        out = gate.evaluate(rows, panel)
        self.assertEqual(out["pooled_mean_delta_m"], -100)
        self.assertEqual(out["verdict"], "FAIL")

    def test_seat1_nested_player_order(self):
        rows, panel = fixture()
        for row in rows:
            for arm in ("baseline", "candidate"):
                pair = [row[arm]["own"], row[arm]["rival"]]
                row[arm] = {"scores": pair if row["candidate_seat"] == 0 else pair[::-1]}
        out = gate.evaluate(rows, panel)
        self.assertEqual(out["opponent_balanced_mean_delta_m"], 1)
        self.assertEqual(out["verdict"], "PASS")

    def test_flat_vectors_are_rejected_not_guessed(self):
        rows, panel = fixture()
        rows[0]["baseline_scores"] = [1000, 900]
        with self.assertRaisesRegex(gate.DataError, "ambiguous"):
            gate.evaluate(rows, panel)

    def test_container_aliases_cannot_mask_bool_int_poison(self):
        rows, panel = fixture()
        hidden = deepcopy(rows); hidden[0]["candidate_seat"] = False
        with self.assertRaisesRegex(gate.DataError, "one paired-container"):
            gate.evaluate({"cells": rows, "results": hidden}, panel)

    def test_separate_arms_match_same_report(self):
        rows, panel = fixture()
        arms = {a: [{**{k: r[k] for k in ("opponent", "seed", "candidate_seat")}, **r[a]}
                    for r in rows] for a in ("baseline", "candidate")}
        self.assertEqual(gate.evaluate(rows, panel), gate.evaluate(arms, panel))

    def test_mixed_arm_and_cells_reject(self):
        rows, panel = fixture()
        with self.assertRaises(gate.DataError):
            gate.evaluate({"baseline": rows, "candidate": rows, "cells": rows}, panel)

    def test_separate_arm_missing_cell_reject(self):
        rows, panel = fixture()
        arms = {a: [{**{k: r[k] for k in ("opponent", "seed", "candidate_seat")}, **r[a]}
                    for r in rows] for a in ("baseline", "candidate")}
        arms["candidate"].pop()
        with self.assertRaisesRegex(gate.DataError, "cell sets differ"):
            gate.evaluate(arms, panel)

    def test_supplied_delta_cannot_override_scores(self):
        rows, panel = fixture()
        rows[0]["delta_m"] = 999
        out = gate.evaluate(rows, panel)
        self.assertEqual(out["pooled_mean_delta_m"], 1)
        self.assertEqual(out["verdict"], "FAIL")
        self.assertTrue(any("supplied delta" in f for f in out["failures"]))

    def test_number_poison_and_derived_overflow(self):
        original, panel = fixture()
        for value in (True, float("nan"), float("inf"), 10**1000):
            rows = deepcopy(original); rows[0]["candidate"]["own"] = value
            with self.subTest(value_type=type(value).__name__), self.assertRaises(gate.DataError):
                gate.evaluate(rows, panel)
        rows = deepcopy(original)
        rows[0]["candidate"] = {"own": 1.7e308, "rival": -1.7e308}
        with self.assertRaises(gate.DataError):
            gate.evaluate(rows, panel)

    def test_new_loss_and_lost_win_budgets(self):
        rows, panel = fixture()
        rows[0]["candidate"]["own"] = 899
        policy = gate.Policy(min_balanced_delta=-1000, min_opponent_delta=-1000,
                             min_opponent_seat_delta=-1000)
        out = gate.evaluate(rows, panel, policy)
        self.assertEqual(out["verdict"], "FAIL")
        self.assertIn("new_losses: 1 > 0", out["failures"])
        self.assertIn("lost_wins: 1 > 0", out["failures"])
        out = gate.evaluate(rows, panel, replace(policy, max_new_losses=1, max_lost_wins=1))
        self.assertEqual(out["verdict"], "PASS")

    def test_win_to_tie_only_lost_win(self):
        rows, panel = fixture(); rows[0]["candidate"]["own"] = 900
        out = gate.evaluate(rows, panel, gate.Policy(min_balanced_delta=-1000,
            min_opponent_delta=-1000, min_opponent_seat_delta=-1000))
        self.assertEqual(len(out["distribution"]["outcomes"]["new_losses"]), 0)
        self.assertEqual(len(out["distribution"]["outcomes"]["lost_wins"]), 1)

    def test_policy_poison(self):
        rows, panel = fixture()
        for field in ("min_seed_pairs", "min_opponents", "max_new_losses", "max_lost_wins"):
            for value in (True, -1, 1.5):
                with self.subTest(field=field, value=value), self.assertRaises(gate.DataError):
                    gate.evaluate(rows, panel, replace(gate.Policy(), **{field: value}))
        for field in ("min_balanced_delta", "min_opponent_delta", "min_opponent_seat_delta"):
            for value in (True, math.nan, math.inf, 10**1000):
                with self.subTest(field=field), self.assertRaises(gate.DataError):
                    gate.evaluate(rows, panel, replace(gate.Policy(), **{field: value}))

    def test_zero_delta_is_only_nonregression(self):
        rows, panel = fixture(deltas={"mirror": 0, "dairy": 0})
        out = gate.evaluate(rows, panel)
        self.assertEqual(out["verdict"], "PASS")
        self.assertEqual(out["scope"], "EMPIRICAL_SCREEN_ONLY_NOT_PROMOTION_AUTHORITY")
        self.assertEqual(gate.evaluate(rows, panel, gate.Policy(min_balanced_delta=0.01))["verdict"], "FAIL")

    def test_no_input_mutation(self):
        rows, panel = fixture(); before = deepcopy((rows, panel))
        gate.evaluate(rows, panel)
        self.assertEqual((rows, panel), before)

    def test_seeded_permutation_invariance(self):
        rows, panel = fixture(deltas={"mirror": 3, "dairy": -1})
        expected = gate.evaluate(rows, panel)
        rng = random.Random(7411)
        for _ in range(20):
            shuffled = deepcopy(rows); rng.shuffle(shuffled)
            other = deepcopy(panel)
            other["opponents"] = dict(reversed(list(other["opponents"].items())))
            for seeds in other["opponents"].values(): rng.shuffle(seeds)
            self.assertEqual(gate.evaluate(shuffled, other), expected)

    def test_reporter_drift_rejected_before_execution(self):
        rows, panel = fixture()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "reporter.py"
            path.write_text("raise SystemExit(0)\n")
            with self.assertRaisesRegex(gate.DataError, "custody mismatch"):
                gate.evaluate(rows, panel, reporter_path=path)

    def test_strict_json_duplicates_and_nonfinite(self):
        for data in (b'{"a":1,"a":2}', b'{"x":{"a":1,"a":1}}', b'[NaN]', b'[Infinity]', b'\xff'):
            with self.subTest(data=data), self.assertRaises(gate.DataError):
                gate.strict_json(data)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        rows, panel = fixture()
        self.evidence = self.root / "evidence.json"; self.evidence.write_text(json.dumps(rows))
        self.panel = self.root / "panel.json"; self.panel.write_text(json.dumps(panel))
        self.output = self.root / "out.json"
        self.args = [str(self.evidence), "--panel", str(self.panel)]

    def run_cli(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = gate.main(self.args + list(extra))
        return code, out.getvalue(), err.getvalue()

    def test_pass_and_hash_bound_output(self):
        code, out, err = self.run_cli("--output", str(self.output))
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.output.read_text(), out)
        report = json.loads(out)
        self.assertEqual(len(report["provenance"]["panel_sha256"]), 64)

    def test_policy_failure_still_emits_report(self):
        code, out, err = self.run_cli("--min-balanced-delta", "2")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["verdict"], "FAIL")

    def test_invalid_data_preserves_existing_output(self):
        self.evidence.write_text('[NaN]'); self.output.write_text("sentinel")
        code, out, err = self.run_cli("--output", str(self.output))
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(self.output.read_text(), "sentinel")
        self.assertIn("DATA ERROR", err)

    def test_input_alias_paths_rejected(self):
        original = self.evidence.read_bytes()
        for target in (self.evidence, self.panel, gate.DEFAULT_REPORTER):
            code, out, err = self.run_cli("--output", str(target))
            self.assertEqual((code, out), (2, ""))
        self.assertEqual(self.evidence.read_bytes(), original)

    def test_hardlink_and_symlink_input_alias_rejected(self):
        for kind in ("hard", "symbolic"):
            alias = self.root / kind
            if kind == "hard": os.link(self.evidence, alias)
            else: alias.symlink_to(self.evidence)
            code, out, err = self.run_cli("--output", str(alias))
            self.assertEqual((code, out), (2, ""))

    def test_nonfinite_threshold_rejected(self):
        self.assertEqual(self.run_cli("--min-balanced-delta", "nan")[:2], (2, ""))

    def test_missing_input_rejected(self):
        self.evidence.unlink()
        self.assertEqual(self.run_cli()[:2], (2, ""))

    def test_output_failure_does_not_print_pass(self):
        path = self.root / "missing" / "out.json"
        self.assertEqual(self.run_cli("--output", str(path))[:2], (2, ""))

    def test_normal_and_optimized_entrypoint(self):
        for options in ([], ["-O"]):
            run = subprocess.run([sys.executable, *options, str(Path(gate.__file__)), *self.args],
                                 capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()

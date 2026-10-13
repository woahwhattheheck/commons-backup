# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import os
import statistics
import subprocess
import sys
import tempfile
import unittest

import intersection_gate as gate


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


LEGACY_POLICY = {
    "min_mean_own_delta": 0.0,
    "min_median_own_delta": 0.0,
    "min_mean_margin_delta": 0.0,
    "min_positive_cell_fraction": 0.5,
    "min_positive_pair_fraction": 0.5,
    "max_result_regressions": 0,
    "max_baseline_win_regressions": 0,
    "max_new_losses": 0,
    "max_negative_opponent_strata": 0,
    "max_negative_seat_strata": 0,
    "min_worst_cell_own_delta": None,
    "require_any_change": True,
}


def _mean(values):
    return statistics.fmean(values)


def _summary(values):
    return {
        "n": len(values),
        "mean": _mean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "positive": sum(value > 0 for value in values),
        "zero": sum(value == 0 for value in values),
        "negative": sum(value < 0 for value in values),
    }


def _legacy_parent_metrics(cells):
    pair_values = {}
    opponent_values = {}
    seat_values = {}
    own_deltas = []
    margin_deltas = []
    regressions = []
    for cell in cells:
        opponent, seed, seat = cell["key"]
        own = cell["own_delta"]
        margin = cell["margin_delta"]
        own_deltas.append(own)
        margin_deltas.append(margin)
        pair_values.setdefault((opponent, seed), []).append(own)
        opponent_values.setdefault(opponent, []).append(own)
        seat_values.setdefault(seat, []).append(own)
        rank = {"L": 0, "T": 1, "W": 2}
        if rank[cell["candidate_result"]] < rank[cell["baseline_result"]]:
            regressions.append(cell)

    pairs = []
    pair_means = []
    for (opponent, seed), values in sorted(pair_values.items()):
        value = _mean(values)
        pair_means.append(value)
        pairs.append(
            {
                "opponent": opponent,
                "seed": seed,
                "seat_mean_own_delta": value,
                "seat_deltas": values,
            }
        )
    per_opponent = {
        key: _summary(values) for key, values in sorted(opponent_values.items())
    }
    per_seat = {
        str(key): _summary(values) for key, values in sorted(seat_values.items())
    }
    aggregate = {
        "cells": len(cells),
        "pairs": len(pairs),
        "own_delta": _summary(own_deltas),
        "margin_delta": _summary(margin_deltas),
        "positive_cell_fraction": sum(value > 0 for value in own_deltas) / len(own_deltas),
        "nonnegative_cell_fraction": sum(value >= 0 for value in own_deltas) / len(own_deltas),
        "positive_pair_fraction": sum(value > 0 for value in pair_means) / len(pair_means),
        "nonnegative_pair_fraction": sum(value >= 0 for value in pair_means) / len(pair_means),
        "changed_cells": sum(
            cell["baseline_scores"] != cell["candidate_scores"] for cell in cells
        ),
        "result_regressions": len(regressions),
        "baseline_win_regressions": sum(
            cell["baseline_result"] == "W" for cell in regressions
        ),
        "new_losses": sum(
            cell["candidate_result"] == "L" and cell["baseline_result"] != "L"
            for cell in regressions
        ),
        "negative_opponent_strata": sum(
            value["mean"] < 0 for value in per_opponent.values()
        ),
        "negative_seat_strata": sum(
            value["mean"] < 0 for value in per_seat.values()
        ),
    }
    return {
        "cells": cells,
        "pairs": pairs,
        "aggregate": aggregate,
        "per_opponent": per_opponent,
        "per_seat": per_seat,
    }


def _legacy_checks(metrics):
    aggregate = metrics["aggregate"]
    policy = LEGACY_POLICY
    checks = []

    def check(name, actual, op, threshold):
        passed = actual >= threshold if op == ">=" else actual <= threshold
        checks.append(
            {
                "name": name,
                "actual": actual,
                "op": op,
                "threshold": threshold,
                "pass": passed,
            }
        )

    check("mean_own_delta", aggregate["own_delta"]["mean"], ">=", policy["min_mean_own_delta"])
    check(
        "median_own_delta",
        aggregate["own_delta"]["median"],
        ">=",
        policy["min_median_own_delta"],
    )
    check(
        "mean_margin_delta",
        aggregate["margin_delta"]["mean"],
        ">=",
        policy["min_mean_margin_delta"],
    )
    check(
        "positive_cell_fraction",
        aggregate["positive_cell_fraction"],
        ">=",
        policy["min_positive_cell_fraction"],
    )
    check(
        "positive_pair_fraction",
        aggregate["positive_pair_fraction"],
        ">=",
        policy["min_positive_pair_fraction"],
    )
    for name in (
        "result_regressions",
        "baseline_win_regressions",
        "new_losses",
        "negative_opponent_strata",
        "negative_seat_strata",
    ):
        check(name, aggregate[name], "<=", policy[f"max_{name}"])
    checks.append(
        {
            "name": "any_score_change",
            "actual": aggregate["changed_cells"],
            "op": "> 0",
            "threshold": 0,
            "pass": aggregate["changed_cells"] > 0,
        }
    )
    return checks


def make_parent(opponents, seeds, own, margin, *, verdict=None):
    cells = []
    for opponent in opponents:
        for seed in seeds:
            for seat in (0, 1):
                own_delta = float(own[(opponent, seed, seat)])
                margin_delta = float(margin[(opponent, seed, seat)])
                base_own, base_rival = 1000.0, 500.0
                rival_delta = own_delta - margin_delta
                candidate_own = base_own + own_delta
                candidate_rival = base_rival + rival_delta
                if seat == 0:
                    baseline_scores = [base_own, base_rival]
                    candidate_scores = [candidate_own, candidate_rival]
                else:
                    baseline_scores = [base_rival, base_own]
                    candidate_scores = [candidate_rival, candidate_own]
                baseline_margin = base_own - base_rival
                candidate_margin = candidate_own - candidate_rival
                cells.append(
                    {
                        "key": [opponent, seed, seat],
                        "baseline_scores": baseline_scores,
                        "candidate_scores": candidate_scores,
                        "baseline_result": "W" if baseline_margin > 0 else "L",
                        "candidate_result": "W" if candidate_margin > 0 else "L",
                        "own_delta": own_delta,
                        "rival_delta": rival_delta,
                        "margin_delta": margin_delta,
                    }
                )
    metrics = _legacy_parent_metrics(cells)
    checks = _legacy_checks(metrics)
    computed_verdict = "PROMOTE" if all(item["pass"] for item in checks) else "REJECT"
    return {
        "verdict": computed_verdict if verdict is None else verdict,
        "checks": checks,
        "metrics": metrics,
    }


def make_contract(parent_bytes, opponents, seeds, **policy_overrides):
    policy = {
        "require_parent_promote": True,
        "min_positive_margin_pair_fraction": 1.0,
        "max_negative_opponent_seat_own_strata": 0,
        "max_negative_opponent_seat_margin_strata": 0,
        "min_worst_pair_margin_delta": 0.0,
        "min_worst_opponent_seat_own_mean": 0.0,
        "min_worst_opponent_seat_margin_mean": 0.0,
    }
    policy.update(policy_overrides)
    return {
        "schema_version": 1,
        "panel_id": "synthetic-intersection-panel",
        "parent_report_sha256": hashlib.sha256(parent_bytes).hexdigest(),
        "opponents": opponents,
        "seeds": seeds,
        "seats": [0, 1],
        "expected_cells": len(opponents) * len(seeds) * 2,
        "policy": policy,
    }


class Harness:
    def __init__(self, root: Path, parent, contract_mutator=None):
        self.root = root
        self.parent_path = root / "PARENT.json"
        self.contract_path = root / "CONTRACT.json"
        self.output_path = root / "RESULT.json"
        parent_bytes = canonical(parent)
        self.parent_path.write_bytes(parent_bytes)
        opponents = sorted({cell["key"][0] for cell in parent["metrics"]["cells"]})
        seeds = sorted({cell["key"][1] for cell in parent["metrics"]["cells"]})
        contract = make_contract(parent_bytes, opponents, seeds)
        if contract_mutator:
            contract_mutator(contract)
        self.contract_path.write_bytes(canonical(contract))

    def run(self):
        return gate.run_gate(self.contract_path, self.parent_path, self.output_path)


class IntersectionGateTests(unittest.TestCase):
    def test_uniform_positive_panel_promotes(self):
        opponents, seeds = ["arlene", "apex"], [11, 29]
        own = {(o, s, seat): 10 for o in opponents for s in seeds for seat in (0, 1)}
        margin = {(o, s, seat): 4 for o in opponents for s in seeds for seat in (0, 1)}
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(Path(td), make_parent(opponents, seeds, own, margin)).run()
        self.assertEqual((code, report["verdict"]), (0, "PROMOTE"))
        self.assertEqual(report["metrics"]["aggregate"]["positive_margin_pair_fraction"], 1.0)
        self.assertTrue(all(check["pass"] for check in report["checks"]))

    def test_simpson_masked_own_cash_rejects(self):
        opponents, seeds = ["arlene", "apex"], [7]
        own = {
            ("arlene", 7, 0): -3,
            ("arlene", 7, 1): 5,
            ("apex", 7, 0): 5,
            ("apex", 7, 1): 1,
        }
        margin = {key: 2 for key in own}
        parent = make_parent(opponents, seeds, own, margin)
        self.assertEqual(parent["verdict"], "PROMOTE")
        self.assertTrue(all(check["pass"] for check in parent["checks"]))
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(Path(td), parent).run()
        self.assertEqual((code, report["verdict"]), (3, "REJECT"))
        aggregate = report["metrics"]["aggregate"]
        self.assertEqual(aggregate["negative_opponent_seat_own_strata"], 1)
        self.assertEqual(aggregate["worst_opponent_seat_own_mean"], -3.0)

    def test_simpson_masked_margin_rejects(self):
        opponents, seeds = ["arlene", "apex"], [7]
        own = {(o, 7, seat): 20 for o in opponents for seat in (0, 1)}
        margin = {
            ("arlene", 7, 0): -10,
            ("arlene", 7, 1): 15,
            ("apex", 7, 0): 15,
            ("apex", 7, 1): 5,
        }
        parent = make_parent(opponents, seeds, own, margin)
        self.assertEqual(parent["verdict"], "PROMOTE")
        self.assertTrue(all(check["pass"] for check in parent["checks"]))
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(Path(td), parent).run()
        self.assertEqual((code, report["verdict"]), (3, "REJECT"))
        self.assertEqual(
            report["metrics"]["aggregate"]["negative_opponent_seat_margin_strata"],
            1,
        )

    def test_negative_pair_margin_hidden_by_intersection_means_rejects(self):
        opponents, seeds = ["arlene"], [1, 2]
        own = {("arlene", s, seat): 20 for s in seeds for seat in (0, 1)}
        margin = {
            ("arlene", 1, 0): -10,
            ("arlene", 1, 1): -10,
            ("arlene", 2, 0): 20,
            ("arlene", 2, 1): 20,
        }
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(Path(td), make_parent(opponents, seeds, own, margin)).run()
        self.assertEqual((code, report["verdict"]), (3, "REJECT"))
        aggregate = report["metrics"]["aggregate"]
        self.assertEqual(aggregate["negative_opponent_seat_margin_strata"], 0)
        self.assertEqual(aggregate["positive_margin_pair_fraction"], 0.5)
        self.assertEqual(aggregate["worst_pair_margin_delta"], -10.0)

    def test_parent_reject_cannot_be_promoted(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = {("arlene", 1, seat): 10 for seat in (0, 1)}
        parent = make_parent(opponents, seeds, own, margin, verdict="REJECT")
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(Path(td), parent).run()
        self.assertEqual((code, report["verdict"]), (3, "REJECT"))
        failed = [check for check in report["checks"] if not check["pass"]]
        self.assertEqual([item["name"] for item in failed], ["parent_promote_coherent"])

    def test_digest_mismatch_is_invalid(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        parent = make_parent(opponents, seeds, own, margin)
        with tempfile.TemporaryDirectory() as td:
            harness = Harness(Path(td), parent)
            harness.parent_path.write_bytes(harness.parent_path.read_bytes() + b" ")
            code, report = harness.run()
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("digest mismatch", report["error"])

    def test_duplicate_and_missing_cells_are_invalid(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        parent = make_parent(opponents, seeds, own, margin)
        parent["metrics"]["cells"][1] = deepcopy(parent["metrics"]["cells"][0])
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(Path(td), parent).run()
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("duplicate cell", report["error"])

    def test_reported_delta_contradiction_is_invalid(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        parent = make_parent(opponents, seeds, own, margin)
        parent["metrics"]["cells"][0]["margin_delta"] = 999
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(Path(td), parent).run()
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("recomputed", report["error"])

    def test_nonfinite_score_is_invalid(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        parent = make_parent(opponents, seeds, own, margin)
        parent["metrics"]["cells"][0]["candidate_scores"][0] = 1e309
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(Path(td), parent).run()
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("finite", report["error"])

    def test_contract_unknown_key_is_invalid(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        parent = make_parent(opponents, seeds, own, margin)
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(
                Path(td), parent, lambda contract: contract.__setitem__("typo", True)
            ).run()
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("key mismatch", report["error"])


    def test_contract_cannot_disable_parent_promotion_requirement(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        parent = make_parent(opponents, seeds, own, margin)
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(
                Path(td),
                parent,
                lambda contract: contract["policy"].__setitem__(
                    "require_parent_promote", False
                ),
            ).run()
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("literal true", report["error"])

    def test_promote_with_failed_parent_check_is_invalid(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        parent = make_parent(opponents, seeds, own, margin)
        parent["checks"][0]["pass"] = False
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(Path(td), parent).run()
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("failed/malformed check", report["error"])


    def test_parent_invalid_is_invalid_not_reject(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        parent = make_parent(opponents, seeds, own, margin, verdict="INVALID")
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(Path(td), parent).run()
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("parent report is INVALID", report["error"])

    def test_missing_parent_produces_persisted_invalid_report(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parent_bytes = canonical(make_parent(opponents, seeds, own, margin))
            contract_path = root / "CONTRACT.json"
            output_path = root / "RESULT.json"
            contract_path.write_bytes(canonical(make_contract(parent_bytes, opponents, seeds)))
            code, report = gate.run_gate(
                contract_path, root / "MISSING.json", output_path
            )
            persisted = json.loads(output_path.read_text())
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertEqual(persisted, report)
        self.assertIn("cannot open regular input", report["error"])
        self.assertIsNone(report["inputs"]["parent_report_sha256"])

    def test_output_cannot_alias_parent_evidence(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        with tempfile.TemporaryDirectory() as td:
            harness = Harness(Path(td), make_parent(opponents, seeds, own, margin))
            before = harness.parent_path.read_bytes()
            code, report = gate.run_gate(
                harness.contract_path, harness.parent_path, harness.parent_path
            )
            after = harness.parent_path.read_bytes()
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("output aliases parent report", report["error"])
        self.assertEqual(after, before)

    def test_finite_endpoint_subtraction_overflow_is_invalid(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        parent = make_parent(opponents, seeds, own, margin)
        parent["metrics"]["cells"][0]["baseline_scores"] = [1.7e308, -1.7e308]
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(Path(td), parent).run()
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("finite", report["error"])

    def test_boolean_score_is_invalid(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        parent = make_parent(opponents, seeds, own, margin)
        parent["metrics"]["cells"][0]["candidate_scores"][0] = True
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(Path(td), parent).run()
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("finite number", report["error"])


    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "O_NOFOLLOW unavailable")
    def test_symlink_parent_input_is_invalid(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parent_bytes = canonical(make_parent(opponents, seeds, own, margin))
            real_parent = root / "REAL-PARENT.json"
            symlink_parent = root / "PARENT.json"
            contract_path = root / "CONTRACT.json"
            output_path = root / "RESULT.json"
            real_parent.write_bytes(parent_bytes)
            symlink_parent.symlink_to(real_parent)
            contract_path.write_bytes(canonical(make_contract(parent_bytes, opponents, seeds)))
            code, report = gate.run_gate(contract_path, symlink_parent, output_path)
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("cannot open regular input", report["error"])

    def test_duplicate_contract_key_is_invalid(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parent_bytes = canonical(make_parent(opponents, seeds, own, margin))
            contract_bytes = canonical(make_contract(parent_bytes, opponents, seeds))
            contract_bytes = contract_bytes.replace(
                b'"schema_version":1',
                b'"schema_version":1,"schema_version":1',
                1,
            )
            contract_path = root / "CONTRACT.json"
            parent_path = root / "PARENT.json"
            output_path = root / "RESULT.json"
            contract_path.write_bytes(contract_bytes)
            parent_path.write_bytes(parent_bytes)
            code, report = gate.run_gate(contract_path, parent_path, output_path)
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("duplicate JSON key", report["error"])

    def test_parent_promote_requires_nonempty_checks(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        parent = make_parent(opponents, seeds, own, margin)
        parent["checks"] = []
        with tempfile.TemporaryDirectory() as td:
            code, report = Harness(Path(td), parent).run()
        self.assertEqual((code, report["verdict"]), (2, "INVALID"))
        self.assertIn("non-empty checks list", report["error"])

    def test_cli_exit_codes_are_stable(self):
        script = Path(gate.__file__)
        opponents, seeds = ["arlene", "apex"], [7]
        positive_own = {(o, 7, seat): 10 for o in opponents for seat in (0, 1)}
        positive_margin = {(o, 7, seat): 4 for o in opponents for seat in (0, 1)}
        masked_own = {
            ("arlene", 7, 0): -3,
            ("arlene", 7, 1): 5,
            ("apex", 7, 0): 5,
            ("apex", 7, 1): 1,
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cases = [
                (
                    "promote",
                    make_parent(opponents, seeds, positive_own, positive_margin),
                    0,
                    "PROMOTE",
                ),
                (
                    "reject",
                    make_parent(opponents, seeds, masked_own, positive_margin),
                    3,
                    "REJECT",
                ),
            ]
            for name, parent, expected_code, expected_word in cases:
                parent_bytes = canonical(parent)
                parent_path = root / f"{name}-parent.json"
                contract_path = root / f"{name}-contract.json"
                output_path = root / f"{name}-output.json"
                parent_path.write_bytes(parent_bytes)
                contract_path.write_bytes(canonical(make_contract(parent_bytes, opponents, seeds)))
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(script),
                        "--contract",
                        str(contract_path),
                        "--parent-report",
                        str(parent_path),
                        "--output",
                        str(output_path),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, expected_code)
                self.assertEqual(completed.stdout.strip(), expected_word)
                self.assertEqual(json.loads(output_path.read_text())["verdict"], expected_word)

            invalid_parent = root / "missing-parent.json"
            contract_path = root / "invalid-contract.json"
            output_path = root / "invalid-output.json"
            dummy_parent = canonical(make_parent(opponents, seeds, positive_own, positive_margin))
            contract_path.write_bytes(canonical(make_contract(dummy_parent, opponents, seeds)))
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--contract",
                    str(contract_path),
                    "--parent-report",
                    str(invalid_parent),
                    "--output",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(completed.stdout.strip(), "INVALID")
            self.assertEqual(json.loads(output_path.read_text())["verdict"], "INVALID")

    def test_output_is_byte_deterministic(self):
        opponents, seeds = ["arlene"], [1]
        own = {("arlene", 1, seat): 10 for seat in (0, 1)}
        margin = dict(own)
        with tempfile.TemporaryDirectory() as td:
            harness = Harness(Path(td), make_parent(opponents, seeds, own, margin))
            first_code, first_report = harness.run()
            first_bytes = harness.output_path.read_bytes()
            second_code, second_report = harness.run()
            second_bytes = harness.output_path.read_bytes()
        self.assertEqual((first_code, first_report), (second_code, second_report))
        self.assertEqual(first_bytes, second_bytes)

    def test_target_hygiene_ignores_unrelated_repo_pycache(self):
        """Repo-wide __pycache__ find is not a gate or materializer contract.

        Run 34528577244 reconstructed the exact patch, verified both SHA-256
        digests, and passed 22/22 tests, then died silently on
        `test -z "$(find . -type d -name __pycache__ -print -quit)"` because
        committed muhl/desktop bytecode directories already exist on main.
        Hygiene must be scoped to the gate subtree.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "titan-v3-intersection-gate"
            target.mkdir()
            (target / "intersection_gate.py").write_text("x = 1\n")
            unrelated = root / "muhl" / "desktop" / "WEATHER" / "__pycache__"
            unrelated.mkdir(parents=True)
            (unrelated / "run.cpython-312.pyc").write_bytes(b"\0")
            scoped = subprocess.run(
                [
                    "bash",
                    "-c",
                    'test -z "$(find "$1" -type d -name __pycache__ -print -quit)"',
                    "_",
                    str(target),
                ],
                check=False,
            )
            unscoped = subprocess.run(
                [
                    "bash",
                    "-c",
                    'test -z "$(find "$1" -type d -name __pycache__ -print -quit)"',
                    "_",
                    str(root),
                ],
                check=False,
            )
        self.assertEqual(scoped.returncode, 0)
        self.assertEqual(unscoped.returncode, 1)


if __name__ == "__main__":
    unittest.main()

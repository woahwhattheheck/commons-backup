"""Deterministic tests; all scores and worlds here are SYNTHETIC fixtures."""
from copy import deepcopy
from itertools import product
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

import audit_paired_panel as audit


def manifest(seeds=(1, 2), purpose="explore", priors=()):
    return {
        "schema": audit.SCHEMA, "panel_id": "SYNTHETIC-PANEL", "purpose": purpose,
        "engine_sha256": "a" * 64, "environment_sha256": "b" * 64,
        "baseline_sha256": "c" * 64, "candidate_sha256": "d" * 64,
        "opponents": {"fixture-opponent": "e" * 64}, "seeds": list(seeds),
        "seats": [0, 1], "prior_plan_sha256": [audit.plan_digest(p) for p in priors],
    }


def rows_for(plan):
    rows = []
    for opponent, seed, seat, arm in product(plan["opponents"], plan["seeds"],
                                            plan["seats"], audit.ARMS):
        scores = [100, 100]
        if arm == "candidate":
            scores[seat] = 110
        rows.append({
            "plan_sha256": audit.plan_digest(plan), "opponent": opponent,
            "seed": seed, "candidate_seat": seat, "arm": arm, "status": "complete",
            "scores": scores, "agent_sha256": plan[arm + "_sha256"],
            "opponent_sha256": plan["opponents"][opponent],
            "engine_sha256": plan["engine_sha256"],
            "environment_sha256": plan["environment_sha256"],
        })
    return rows


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.plan = manifest()
        self.rows = rows_for(self.plan)

    def rejected(self, rows, code, plan=None, priors=None):
        result = audit.audit_panel(plan or self.plan, rows, priors)
        self.assertFalse(result["ok"])
        self.assertNotIn("paired_evidence", result)
        self.assertIn(code, [entry["code"] for entry in result["errors"]])
        return result

    def test_complete_and_both_seats(self):
        result = audit.audit_panel(self.plan, self.rows)
        self.assertTrue(result["ok"])
        self.assertEqual(result["expected_pairs"], 4)
        self.assertEqual(result["complete_pairs"], 4)
        self.assertEqual(result["successful_unique_rows"], 8)

    def test_nested_export_is_player_ordered_not_own_rival(self):
        cells = audit.audit_panel(self.plan, self.rows)["paired_evidence"]["cells"]
        for cell in cells:
            self.assertEqual(cell["candidate"]["scores"][cell["candidate_seat"]], 110)
            self.assertEqual(cell["candidate"]["scores"][1 - cell["candidate_seat"]], 100)

    def test_missing_both_arms_is_not_invisible(self):
        self.rejected(self.rows[2:], "missing_cell")

    def test_omitted_collapse_cannot_become_seven_positive_cells(self):
        plan = manifest(seeds=(1, 2, 3, 4))
        rows = rows_for(plan)
        rows[-1]["scores"][rows[-1]["candidate_seat"]] = 0
        full = audit.audit_panel(plan, rows)
        self.assertTrue(full["ok"])
        # The eighth outcome is preserved; complete evidence need not be a win.
        self.assertEqual(len(full["paired_evidence"]["cells"]), 8)
        self.rejected(rows[:-2], "missing_cell", plan=plan)
        self.rejected(rows[:-1], "missing_cell", plan=plan)

    def test_each_single_missing_row_is_rejected(self):
        plan = manifest(seeds=tuple(range(8)))
        plan["opponents"]["second-opponent"] = "f" * 64
        rows = rows_for(plan)
        for index in range(len(rows)):
            with self.subTest(index=index):
                self.rejected(rows[:index] + rows[index + 1:], "missing_cell", plan=plan)

    def test_identical_duplicate_is_not_extra_evidence(self):
        self.rejected(self.rows + [deepcopy(self.rows[0])], "duplicate_cell")

    def test_disagreeing_duplicate_never_picks_best_or_last(self):
        duplicate = deepcopy(self.rows[-1])
        duplicate["scores"] = [0, 10000]
        for rows in (self.rows + [duplicate], [duplicate] + self.rows):
            self.rejected(rows, "duplicate_cell")

    def test_failed_games_all_remain_failures(self):
        for status in ("error", "timeout", "cancelled"):
            rows = deepcopy(self.rows)
            rows[1]["status"] = status
            del rows[1]["scores"]
            with self.subTest(status=status):
                self.rejected(rows, "failed_game")

    def test_retry_cannot_erase_failure(self):
        failure = deepcopy(self.rows[1])
        failure["status"] = "timeout"
        del failure["scores"]
        out = self.rejected([failure] + self.rows, "failed_game")
        self.assertIn("duplicate_cell", [e["code"] for e in out["errors"]])

    def test_all_pin_mismatches_are_rejected(self):
        for pin in ("plan_sha256", "engine_sha256", "environment_sha256",
                    "agent_sha256", "opponent_sha256"):
            rows = deepcopy(self.rows)
            rows[0][pin] = "0" * 64
            with self.subTest(pin=pin):
                self.rejected(rows, "pin_mismatch")

    def test_label_cannot_hide_opponent_artifact_change(self):
        rows = deepcopy(self.rows)
        rows[-1]["opponent_sha256"] = "1" * 64
        self.rejected(rows, "pin_mismatch")

    def test_unexpected_seed_opponent_and_seat_arm_domain(self):
        for key, value in (("seed", 999), ("opponent", "extra-opponent")):
            rows = deepcopy(self.rows)
            rows[-1][key] = value
            self.rejected(rows, "unexpected_cell")
        for key, value in (("candidate_seat", 2), ("candidate_seat", True),
                           ("seed", True), ("seed", "1"), ("arm", "best")):
            rows = deepcopy(self.rows)
            rows[-1][key] = value
            self.rejected(rows, "invalid_row")

    def test_malformed_result_does_not_disappear(self):
        for bad in (None, [], "ignored", {}, {"scores": [100, 200]}):
            self.rejected(self.rows + [bad], "invalid_row")

    def test_unknown_fields_and_score_aliases_reject(self):
        rows = deepcopy(self.rows)
        rows[0]["own_score"] = 1000
        self.rejected(rows, "invalid_row")

    def test_complete_requires_valid_scores(self):
        for scores in (None, [], [1], [1, 2, 3], [True, 2], ["1", 2],
                       [float("nan"), 1], [float("inf"), 1], [10 ** 400, 1]):
            rows = deepcopy(self.rows)
            rows[0]["scores"] = scores
            self.rejected(rows, "invalid_row")

    def test_complete_cannot_also_report_error(self):
        rows = deepcopy(self.rows)
        rows[0]["error"] = "runtime crash"
        self.rejected(rows, "invalid_row")

    def test_activation_counts_not_fabricated(self):
        cells = audit.audit_panel(self.plan, self.rows)["paired_evidence"]["cells"]
        self.assertTrue(all("activations" not in c for c in cells))
        self.rows[1]["activations"] = {"fixture-lane": 0}
        cells = audit.audit_panel(self.plan, self.rows)["paired_evidence"]["cells"]
        self.assertEqual(cells[0]["activations"], {"fixture-lane": 0})
        self.assertTrue(all("activations" not in c for c in cells[1:]))
        self.rows[1]["activations"] = {"fixture-lane": True}
        self.rejected(self.rows, "invalid_row")

    def test_empty_evidence_is_incomplete(self):
        result = self.rejected([], "missing_cell")
        self.assertEqual(result["complete_pairs"], 0)

    def test_invalid_manifests_reject(self):
        cases = [("seeds", []), ("seeds", [True, 2]), ("seeds", [1, 1]),
                 ("seats", [0]), ("seats", [False, 1]), ("seats", [0, 1, 1]),
                 ("opponents", {}), ("opponents", {" padded ": "e" * 64}),
                 ("engine_sha256", "main"), ("purpose", "win"),
                 ("prior_plan_sha256", ["a" * 64, "a" * 64])]
        for key, value in cases:
            plan = deepcopy(self.plan)
            plan[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(audit.EvidenceError):
                audit.audit_panel(plan, [])

    def test_plan_unknown_replication_field_not_silently_ignored(self):
        self.plan["replicates"] = 3
        with self.assertRaises(audit.EvidenceError):
            audit.audit_panel(self.plan, self.rows)

    def test_order_invariance_128_permutations(self):
        original = audit.audit_panel(self.plan, self.rows)
        rng = random.Random(814211)
        for _ in range(128):
            shuffled = deepcopy(self.rows)
            rng.shuffle(shuffled)
            self.assertEqual(audit.audit_panel(self.plan, shuffled), original)

    def test_inputs_and_export_are_detached(self):
        originals = deepcopy((self.plan, self.rows))
        result = audit.audit_panel(self.plan, self.rows)
        self.assertEqual((self.plan, self.rows), originals)
        result["paired_evidence"]["cells"][0]["baseline"]["scores"][0] = -1
        result["paired_evidence"]["panel_manifest"]["seeds"][0] = 999
        self.assertEqual((self.plan, self.rows), originals)

    def test_confirmation_requires_pinned_prior(self):
        plan = manifest(purpose="confirm")
        with self.assertRaises(audit.EvidenceError):
            audit.audit_panel(plan, rows_for(plan))

    def test_confirmation_reuses_world_under_other_opponent_rejects(self):
        prior = self.plan
        plan = manifest(seeds=(2, 3), purpose="confirm", priors=[prior])
        plan["opponents"] = {"new-opponent": "f" * 64}
        self.rejected(rows_for(plan), "confirmation_seed_overlap", plan, [prior])

    def test_confirmation_disjoint_worlds_pass(self):
        prior = self.plan
        plan = manifest(seeds=(3, 4), purpose="confirm", priors=[prior])
        self.assertTrue(audit.audit_panel(plan, rows_for(plan), [prior])["ok"])

    def test_confirmation_missing_drifted_duplicate_prior_reject(self):
        prior = self.plan
        plan = manifest(seeds=(3, 4), purpose="confirm", priors=[prior])
        changed = deepcopy(prior)
        changed["panel_id"] = "changed"
        for priors in ([], [changed], [prior, prior]):
            with self.assertRaises(audit.EvidenceError):
                audit.audit_panel(plan, rows_for(plan), priors)

    def test_transitive_tuning_history_cannot_disappear(self):
        first = self.plan
        second = manifest(seeds=(3, 4), purpose="confirm", priors=[first])
        third = manifest(seeds=(1, 5), purpose="confirm", priors=[second])
        with self.assertRaises(audit.EvidenceError):
            audit.audit_panel(third, rows_for(third), [second])
        third["prior_plan_sha256"].append(audit.plan_digest(first))
        self.rejected(rows_for(third), "confirmation_seed_overlap", third, [first, second])

    def test_strict_json_duplicate_key_and_constants(self):
        for text in ('{"seed":1,"seed":2}', '{"nested":{"a":1,"a":2}}',
                     '[NaN]', '[Infinity]', '[-Infinity]', '{bad'):
            with self.assertRaises(audit.EvidenceError):
                audit.loads(text)

    def test_manifest_digest_is_whitespace_and_key_order_independent(self):
        reverse = dict(reversed(list(self.plan.items())))
        self.assertEqual(audit.plan_digest(self.plan), audit.plan_digest(reverse))
        self.assertEqual(audit.plan_digest(self.plan),
                         audit.plan_digest(audit.loads(json.dumps(self.plan, indent=4))))

    def test_cli_success_exports_only_valid_nested_cells(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_files(root, self.rows)
            result = self.cli(root, "--paired-out", str(root / "paired.json"))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads(result.stdout)["ok"])
            evidence = json.loads((root / "paired.json").read_text())
            self.assertEqual(len(evidence["cells"]), 4)
            self.assertNotIn("paired_evidence", json.loads(result.stdout))

    def test_cli_failed_audit_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_files(root, self.rows[:-1])
            output = root / "paired.json"
            output.write_text("DO NOT REPLACE")
            result = self.cli(root, "--paired-out", str(output))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_text(), "DO NOT REPLACE")
            self.assertFalse(json.loads(result.stdout)["ok"])

    def test_cli_bad_json_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_files(root, self.rows)
            (root / "rows.jsonl").write_text('{"seed":1,"seed":2}\n')
            output = root / "paired.json"
            output.write_text("UNCHANGED")
            result = self.cli(root, "--paired-out", str(output))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_text(), "UNCHANGED")
            self.assertEqual(json.loads(result.stdout)["errors"][0]["code"], "input_error")

    def test_cli_never_overwrites_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_files(root, self.rows)
            original = (root / "plan.json").read_bytes()
            result = self.cli(root, "--paired-out", str(root / "plan.json"))
            self.assertEqual(result.returncode, 2)
            self.assertEqual((root / "plan.json").read_bytes(), original)

    def test_cli_confirmation_reads_exact_prior(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prior = self.plan
            plan = manifest(seeds=(3, 4), purpose="confirm", priors=[prior])
            self.write_files(root, rows_for(plan), plan)
            (root / "prior.json").write_text(json.dumps(prior))
            result = self.cli(root, "--prior-plan", str(root / "prior.json"))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def write_files(self, root, rows, plan=None):
        (root / "plan.json").write_text(json.dumps(plan or self.plan))
        (root / "rows.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    def cli(self, root, *args):
        options = ["-O"] if sys.flags.optimize else []
        return subprocess.run([sys.executable, *options, str(Path(audit.__file__)),
                               str(root / "plan.json"), str(root / "rows.jsonl"), *args],
                              capture_output=True, text=True, timeout=15)


if __name__ == "__main__":
    unittest.main()

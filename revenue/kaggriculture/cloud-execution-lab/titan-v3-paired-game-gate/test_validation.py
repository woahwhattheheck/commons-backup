# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import hashlib
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import gate
from test_support import Harness, contract, evidence, rows


class ValidEvidenceTests(unittest.TestCase):
    def test_complete_aligned_panel_promotes(self):
        with tempfile.TemporaryDirectory() as td:
            report, code = Harness(Path(td)).run()
        self.assertEqual((code, report["verdict"]), (0, "PROMOTE"))
        self.assertEqual(report["grid"]["observed_candidate_cells"], 8)
        self.assertEqual(report["metrics"]["aggregate"]["own_delta"]["mean"], 10.0)
        self.assertEqual(report["metrics"]["aggregate"]["positive_pair_fraction"], 1.0)
        self.assertEqual(report["metrics"]["aggregate"]["candidate_results"], {"W": 8, "T": 0, "L": 0})
        self.assertTrue(all(item["pass"] for item in report["checks"]))

    def test_both_seats_are_paired_per_seed_opponent(self):
        with tempfile.TemporaryDirectory() as td:
            report, _ = Harness(Path(td)).run()
        self.assertEqual(len(report["metrics"]["pairs"]), 4)
        self.assertTrue(all(pair["seat_deltas"] == [10.0, 10.0] for pair in report["metrics"]["pairs"]))

    def test_report_is_deterministic(self):
        with tempfile.TemporaryDirectory() as td:
            harness = Harness(Path(td))
            first, code1 = harness.run()
            second, code2 = harness.run()
        self.assertEqual((first, code1), (second, code2))

    def test_64_character_git_object_ids_are_accepted(self):
        value = contract()
        value["provenance"]["engine_commit"] = "c" * 64
        value["provenance"]["runner_commit"] = "d" * 64
        with tempfile.TemporaryDirectory() as td:
            report, code = Harness(
                Path(td), contract_value=value, evidence_value=evidence(value["provenance"])
            ).run()
        self.assertEqual(code, 0)
        self.assertEqual(report["provenance"]["engine_commit"], "c" * 64)

    def test_hash_and_parser_share_one_immutable_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            harness = Harness(Path(td))
            candidate_preimage = harness.candidate.read_bytes()
            real_snapshot = gate.snapshot_regular_file

            def mutate_after_snapshot(path, **kwargs):
                snapshot = real_snapshot(path, **kwargs)
                if Path(path) == harness.candidate:
                    harness.candidate.write_text("", encoding="utf-8")
                return snapshot

            with mock.patch.object(gate, "snapshot_regular_file", side_effect=mutate_after_snapshot):
                report, code = harness.run()

        self.assertEqual((code, report["verdict"]), (0, "PROMOTE"))
        self.assertEqual(
            report["input_sha256"]["candidate_games"],
            hashlib.sha256(candidate_preimage).hexdigest(),
        )
        self.assertEqual(report["input_bytes"]["candidate_games"], len(candidate_preimage))
        self.assertEqual(report["metrics"]["aggregate"]["own_delta"]["mean"], 10.0)


class StructuralInvalidityTests(unittest.TestCase):
    def assert_invalid(self, mutate, expected):
        baseline, candidate = rows()
        contract_value = contract()
        evidence_value = evidence(contract_value["provenance"])
        mutate(contract_value, evidence_value, baseline, candidate)
        with tempfile.TemporaryDirectory() as td:
            harness = Harness(
                Path(td), contract_value=contract_value, evidence_value=evidence_value,
                baseline=baseline, candidate=candidate,
            )
            with self.assertRaisesRegex(gate.GateError, expected):
                harness.run()

    def test_missing_cell_is_invalid_not_a_smaller_sample(self):
        self.assert_invalid(lambda _c, _e, _b, candidate: candidate.pop(), "missing 1 cells")

    def test_extra_cell_is_invalid(self):
        def mutate(_c, _e, _b, candidate):
            candidate.append({
                "opponent": "new", "seed": 101, "candidate_seat": 0,
                "status": "complete", "scores": [1, 0],
            })
        self.assert_invalid(mutate, "extra cell")

    def test_duplicate_cell_is_invalid(self):
        self.assert_invalid(lambda _c, _e, _b, candidate: candidate.append(deepcopy(candidate[0])), "duplicate cell")

    def test_failed_candidate_row_is_invalid(self):
        def mutate(_c, _e, _b, candidate):
            candidate[0] = {
                "opponent": "arlene", "seed": 101, "candidate_seat": 0,
                "status": "timeout", "error": "deadline",
            }
        self.assert_invalid(mutate, "non-complete cells")

    def test_failed_baseline_row_is_invalid(self):
        def mutate(_c, _e, baseline, _candidate):
            baseline[0].update(status="error", error="boom")
        self.assert_invalid(mutate, "baseline games: non-complete cells")

    def test_nonfinite_score_is_invalid(self):
        self.assert_invalid(
            lambda _c, _e, _b, candidate: candidate[0].__setitem__("scores", [math.nan, 0]),
            "non-finite JSON constant",
        )

    def test_huge_integer_score_is_invalid(self):
        self.assert_invalid(
            lambda _c, _e, _b, candidate: candidate[0].__setitem__("scores", [10 ** 400, 0]),
            "expected a finite number",
        )

    def test_wrong_score_cardinality_is_invalid(self):
        self.assert_invalid(
            lambda _c, _e, _b, candidate: candidate[0].__setitem__("scores", [1]),
            "scores must have exactly two",
        )

    def test_bad_seat_is_invalid(self):
        self.assert_invalid(
            lambda _c, _e, _b, candidate: candidate[0].__setitem__("candidate_seat", 2),
            "candidate_seat must be 0 or 1",
        )

    def test_provenance_drift_is_invalid(self):
        def mutate(_c, evidence_value, _b, _candidate):
            evidence_value["provenance"]["candidate_artifact_sha256"] = "f" * 64
        self.assert_invalid(mutate, "provenance drift")

    def test_duplicate_contract_seed_is_invalid(self):
        def mutate(contract_value, _e, _b, _candidate):
            contract_value["seeds"] = [101, 101]
        self.assert_invalid(mutate, "duplicate value 101")

    def test_contract_requires_both_seats(self):
        def mutate(contract_value, _e, _b, _candidate):
            contract_value["seats"], contract_value["expected_cells"] = [0], 4
        self.assert_invalid(mutate, "must contain exactly")

    def test_boolean_contract_schema_version_is_invalid(self):
        self.assert_invalid(
            lambda contract_value, _e, _b, _candidate: contract_value.__setitem__("schema_version", True),
            "schema_version must equal integer 1",
        )

    def test_boolean_evidence_schema_version_is_invalid(self):
        self.assert_invalid(
            lambda _c, evidence_value, _b, _candidate: evidence_value.__setitem__("schema_version", True),
            "schema_version must equal integer 1",
        )

    def test_duplicate_json_object_key_is_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            harness = Harness(Path(td))
            harness.contract.write_text('{"schema_version":1,"schema_version":1}\n', encoding="utf-8")
            with self.assertRaisesRegex(gate.GateError, "duplicate JSON object key"):
                harness.run()

    def test_symlinked_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root, harness = Path(td), Harness(Path(td))
            linked = root / "linked-candidate.jsonl"
            linked.symlink_to(harness.candidate)
            with self.assertRaisesRegex(gate.GateError, "symbolic links are not accepted"):
                gate.run_gate(
                    contract_path=harness.contract, evidence_path=harness.evidence,
                    baseline_path=harness.baseline, candidate_path=linked,
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)

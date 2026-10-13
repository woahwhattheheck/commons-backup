# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import dual_predecessor_gate as dual
from gate_common import GateError


G0, G1 = "a" * 40, "b" * 40


def _policy(**overrides):
    value = {
        "min_mean_own_delta": 1.0,
        "min_median_own_delta": 1.0,
        "min_mean_margin_delta": 1.0,
        "min_positive_cell_fraction": 0.5,
        "min_positive_pair_fraction": 0.5,
        "max_result_regressions": 0,
        "max_baseline_win_regressions": 0,
        "max_new_losses": 0,
        "max_negative_opponent_strata": 0,
        "max_negative_seat_strata": 0,
        "min_worst_cell_own_delta": -20.0,
        "require_any_change": True,
    }
    value.update(overrides)
    return value


def _rows(delta=10.0):
    baseline, candidate = [], []
    for opponent in ("arlene", "apex"):
        for seed in (101, 102):
            for seat in (0, 1):
                before = [100.0, 80.0] if seat == 0 else [80.0, 100.0]
                after = list(before)
                after[seat] += delta
                common = {
                    "opponent": opponent,
                    "seed": seed,
                    "candidate_seat": seat,
                    "status": "complete",
                }
                baseline.append({**common, "scores": before})
                candidate.append({**common, "scores": after})
    return baseline, candidate


def _write_json(path: Path, value):
    path.write_text(
        json.dumps(value, allow_nan=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, values):
    path.write_text(
        "".join(
            json.dumps(value, allow_nan=True) + "\n"
            for value in values
        ),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance(
    *,
    engine_sha: str,
    runner_sha: str,
    baseline_sha: str,
    candidate_sha: str,
):
    return {
        "engine_commit": G0,
        "engine_sha256": engine_sha,
        "runner_commit": G1,
        "runner_sha256": runner_sha,
        "baseline_artifact_sha256": baseline_sha,
        "candidate_artifact_sha256": candidate_sha,
    }


def _contract(
    *,
    panel_id: str,
    baseline_name: str,
    provenance,
):
    return {
        "schema_version": 1,
        "panel_id": panel_id,
        "baseline_name": baseline_name,
        "candidate_name": "titan-v3",
        "seeds": [101, 102],
        "opponents": ["arlene", "apex"],
        "seats": [0, 1],
        "expected_cells": 8,
        "provenance": deepcopy(provenance),
        "policy": _policy(),
    }


def _evidence(contract_value):
    return {
        "schema_version": 1,
        "panel_id": contract_value["panel_id"],
        "provenance": deepcopy(contract_value["provenance"]),
        "exact_command": (
            "python gauntlet.py --seeds 101,102 "
            "--opponents arlene,apex"
        ),
    }


def _receipt(paths, slot, contract_value, evidence_value):
    prefix = f"predecessor_{slot}"
    return {
        "schema_version": 1,
        "receipt_type": "titan-paired-run-custody/v1",
        "panel_id": contract_value["panel_id"],
        "baseline_name": contract_value["baseline_name"],
        "candidate_name": contract_value["candidate_name"],
        "exact_command": evidence_value["exact_command"],
        "provenance": deepcopy(contract_value["provenance"]),
        "grid": {
            "seeds": sorted(contract_value["seeds"]),
            "opponents": sorted(contract_value["opponents"]),
            "seats": sorted(contract_value["seats"]),
            "expected_cells": contract_value["expected_cells"],
        },
        "sha256": {
            "contract": _sha256(paths[f"{prefix}_contract_path"]),
            "evidence": _sha256(paths[f"{prefix}_evidence_path"]),
            "engine_artifact": _sha256(
                paths["engine_artifact_path"]
            ),
            "runner_artifact": _sha256(
                paths["runner_artifact_path"]
            ),
            "baseline_artifact": _sha256(
                paths[f"{prefix}_artifact_path"]
            ),
            "candidate_artifact": _sha256(
                paths["candidate_artifact_path"]
            ),
            "baseline_games": _sha256(
                paths[f"{prefix}_games_path"]
            ),
            "candidate_games": _sha256(
                paths["candidate_games_path"]
            ),
        },
    }


def _write_receipt(
    paths,
    slot,
    contract_value,
    evidence_value,
):
    _write_json(
        paths[f"predecessor_{slot}_receipt_path"],
        _receipt(
            paths,
            slot,
            contract_value,
            evidence_value,
        ),
    )


def _write_case(tmp_path: Path, *, predecessor_b_rows=None):
    baseline_rows, candidate_rows = _rows()
    second_baseline = deepcopy(baseline_rows)
    second_baseline[0]["scores"][0] -= 1.0
    if predecessor_b_rows is not None:
        second_baseline = predecessor_b_rows

    paths = {
        "predecessor_a_contract_path": (
            tmp_path / "v1-contract.json"
        ),
        "predecessor_a_evidence_path": (
            tmp_path / "v1-evidence.json"
        ),
        "predecessor_a_games_path": (
            tmp_path / "v1-games.jsonl"
        ),
        "predecessor_a_receipt_path": (
            tmp_path / "v1-receipt.json"
        ),
        "predecessor_a_artifact_path": (
            tmp_path / "v1-runtime.tar"
        ),
        "predecessor_b_contract_path": (
            tmp_path / "v2-contract.json"
        ),
        "predecessor_b_evidence_path": (
            tmp_path / "v2-evidence.json"
        ),
        "predecessor_b_games_path": (
            tmp_path / "v2-games.jsonl"
        ),
        "predecessor_b_receipt_path": (
            tmp_path / "v2-receipt.json"
        ),
        "predecessor_b_artifact_path": (
            tmp_path / "v2-runtime.tar"
        ),
        "candidate_games_path": (
            tmp_path / "v3-games.jsonl"
        ),
        "candidate_artifact_path": (
            tmp_path / "v3-runtime.tar"
        ),
        "engine_artifact_path": (
            tmp_path / "engine.bundle"
        ),
        "runner_artifact_path": (
            tmp_path / "runner.bundle"
        ),
    }
    paths["engine_artifact_path"].write_bytes(
        b"pinned engine artifact\n"
    )
    paths["runner_artifact_path"].write_bytes(
        b"pinned runner artifact\n"
    )
    paths["predecessor_a_artifact_path"].write_bytes(
        b"titan-v1 closure bundle\n"
    )
    paths["predecessor_b_artifact_path"].write_bytes(
        b"titan-v2 closure bundle\n"
    )
    paths["candidate_artifact_path"].write_bytes(
        b"titan-v3 closure bundle\n"
    )

    common = {
        "engine_sha": _sha256(paths["engine_artifact_path"]),
        "runner_sha": _sha256(paths["runner_artifact_path"]),
        "candidate_sha": _sha256(
            paths["candidate_artifact_path"]
        ),
    }
    first = _contract(
        panel_id="panel-v1",
        baseline_name="titan-v1",
        provenance=_provenance(
            baseline_sha=_sha256(
                paths["predecessor_a_artifact_path"]
            ),
            **common,
        ),
    )
    second = _contract(
        panel_id="panel-v2",
        baseline_name="titan-v2",
        provenance=_provenance(
            baseline_sha=_sha256(
                paths["predecessor_b_artifact_path"]
            ),
            **common,
        ),
    )
    first_evidence = _evidence(first)
    second_evidence = _evidence(second)

    _write_json(paths["predecessor_a_contract_path"], first)
    _write_json(
        paths["predecessor_a_evidence_path"],
        first_evidence,
    )
    _write_jsonl(
        paths["predecessor_a_games_path"],
        baseline_rows,
    )
    _write_json(paths["predecessor_b_contract_path"], second)
    _write_json(
        paths["predecessor_b_evidence_path"],
        second_evidence,
    )
    _write_jsonl(
        paths["predecessor_b_games_path"],
        second_baseline,
    )
    _write_jsonl(
        paths["candidate_games_path"],
        candidate_rows,
    )
    _write_receipt(
        paths,
        "a",
        first,
        first_evidence,
    )
    _write_receipt(
        paths,
        "b",
        second,
        second_evidence,
    )
    return (
        paths,
        first,
        second,
        first_evidence,
        second_evidence,
        baseline_rows,
        second_baseline,
        candidate_rows,
    )


def _rewrite_contract_evidence_receipt(
    paths,
    slot,
    contract_value,
):
    evidence_value = _evidence(contract_value)
    _write_json(
        paths[f"predecessor_{slot}_contract_path"],
        contract_value,
    )
    _write_json(
        paths[f"predecessor_{slot}_evidence_path"],
        evidence_value,
    )
    _write_receipt(
        paths,
        slot,
        contract_value,
        evidence_value,
    )


class DualPredecessorGateTests(unittest.TestCase):
    def setUp(self):
        self._directory = TemporaryDirectory(
            prefix="titan-v3-dual-gate-test-"
        )
        self.addCleanup(self._directory.cleanup)
        self.tmp_path = Path(self._directory.name)

    def test_promotes_same_observed_candidate_against_two_bound_predecessors(self):
        paths, *_ = _write_case(self.tmp_path)

        report, code = dual.run_dual_gate(**paths)

        self.assertEqual(code, 0)
        self.assertEqual(report["verdict"], "PROMOTE")
        self.assertEqual(
            report["mode"],
            "dual-predecessor-custody-bound",
        )
        self.assertEqual(
            report["comparison_exit_codes"],
            {"predecessor_a": 0, "predecessor_b": 0},
        )
        candidate_digest = report["input_sha256"][
            "candidate_games"
        ]
        self.assertEqual(
            report["shared"]["candidate_games_sha256"],
            candidate_digest,
        )
        self.assertEqual(
            {
                report["custody"][slot][
                    "bound_file_sha256"
                ]["candidate_games"]
                for slot in (
                    "predecessor_a",
                    "predecessor_b",
                )
            },
            {candidate_digest},
        )
        self.assertNotEqual(
            report["input_sha256"][
                "predecessor_a_games"
            ],
            report["input_sha256"][
                "predecessor_b_games"
            ],
        )

    def test_rejects_when_candidate_beats_only_one_predecessor(self):
        _, candidate_rows = _rows()
        stronger_predecessor = deepcopy(candidate_rows)
        for row in stronger_predecessor:
            row["scores"][row["candidate_seat"]] += 20.0
        paths, *_ = _write_case(
            self.tmp_path,
            predecessor_b_rows=stronger_predecessor,
        )

        report, code = dual.run_dual_gate(**paths)

        self.assertEqual(code, 3)
        self.assertEqual(report["verdict"], "REJECT")
        self.assertEqual(
            report["comparison_exit_codes"],
            {"predecessor_a": 0, "predecessor_b": 3},
        )

    def test_identical_panel_bytes_are_valid_for_distinct_closures(self):
        (
            paths,
            _,
            second,
            _,
            _,
            first_rows,
            _,
            _,
        ) = _write_case(self.tmp_path)
        _write_jsonl(
            paths["predecessor_b_games_path"],
            first_rows,
        )
        _rewrite_contract_evidence_receipt(
            paths,
            "b",
            second,
        )

        report, code = dual.run_dual_gate(**paths)

        self.assertEqual(code, 0)
        self.assertEqual(report["verdict"], "PROMOTE")
        self.assertEqual(
            report["input_sha256"]["predecessor_a_games"],
            report["input_sha256"]["predecessor_b_games"],
        )
        self.assertNotEqual(
            report["input_sha256"]["predecessor_a_artifact"],
            report["input_sha256"]["predecessor_b_artifact"],
        )

    def test_rejects_semantic_copy_with_different_jsonl_bytes(self):
        (
            paths,
            _,
            second,
            _,
            _,
            first_rows,
            _,
            _,
        ) = _write_case(self.tmp_path)
        _write_jsonl(
            paths["predecessor_b_games_path"],
            reversed(first_rows),
        )
        self.assertNotEqual(
            _sha256(paths["predecessor_a_games_path"]),
            _sha256(paths["predecessor_b_games_path"]),
        )
        _rewrite_contract_evidence_receipt(
            paths,
            "b",
            second,
        )

        with self.assertRaisesRegex(
            GateError,
            "semantically identical",
        ):
            dual.run_dual_gate(**paths)

    def test_rejects_signed_zero_semantic_copy(self):
        (
            paths,
            first,
            second,
            _,
            _,
            first_rows,
            _,
            _,
        ) = _write_case(self.tmp_path)
        first_rows = deepcopy(first_rows)
        second_rows = deepcopy(first_rows)
        first_rows[0]["scores"][0] = 0.0
        second_rows[0]["scores"][0] = -0.0
        _write_jsonl(
            paths["predecessor_a_games_path"],
            first_rows,
        )
        _write_jsonl(
            paths["predecessor_b_games_path"],
            reversed(second_rows),
        )
        self.assertNotEqual(
            _sha256(paths["predecessor_a_games_path"]),
            _sha256(paths["predecessor_b_games_path"]),
        )
        _rewrite_contract_evidence_receipt(
            paths,
            "a",
            first,
        )
        _rewrite_contract_evidence_receipt(
            paths,
            "b",
            second,
        )

        with self.assertRaisesRegex(
            GateError,
            "semantically identical",
        ):
            dual.run_dual_gate(**paths)

    def test_rejects_candidate_artifact_declaration_not_observed_bytes(self):
        (
            paths,
            first,
            second,
            *_,
        ) = _write_case(self.tmp_path)
        first["provenance"][
            "candidate_artifact_sha256"
        ] = "7" * 64
        second["provenance"][
            "candidate_artifact_sha256"
        ] = "7" * 64
        _rewrite_contract_evidence_receipt(
            paths,
            "a",
            first,
        )
        _rewrite_contract_evidence_receipt(
            paths,
            "b",
            second,
        )

        with self.assertRaisesRegex(
            GateError,
            "declared artifact digest does not match observed bytes",
        ):
            dual.run_dual_gate(**paths)

    def test_rejects_engine_declaration_not_observed_bytes(self):
        paths, first, _, *_ = _write_case(self.tmp_path)
        first["provenance"]["engine_sha256"] = "8" * 64
        _rewrite_contract_evidence_receipt(
            paths,
            "a",
            first,
        )

        with self.assertRaisesRegex(
            GateError,
            "declared artifact digest does not match observed bytes",
        ):
            dual.run_dual_gate(**paths)

    def test_rejects_two_labels_for_same_observed_predecessor_artifact(self):
        paths, _, second, *_ = _write_case(self.tmp_path)
        paths["predecessor_b_artifact_path"].write_bytes(
            paths["predecessor_a_artifact_path"].read_bytes()
        )
        second["provenance"][
            "baseline_artifact_sha256"
        ] = _sha256(
            paths["predecessor_b_artifact_path"]
        )
        _rewrite_contract_evidence_receipt(
            paths,
            "b",
            second,
        )

        with self.assertRaisesRegex(
            GateError,
            "predecessor artifacts must be distinct",
        ):
            dual.run_dual_gate(**paths)

    def test_rejects_candidate_aliasing_observed_predecessor_artifact(self):
        paths, first, _, *_ = _write_case(self.tmp_path)
        paths["predecessor_a_artifact_path"].write_bytes(
            paths["candidate_artifact_path"].read_bytes()
        )
        first["provenance"][
            "baseline_artifact_sha256"
        ] = _sha256(
            paths["predecessor_a_artifact_path"]
        )
        _rewrite_contract_evidence_receipt(
            paths,
            "a",
            first,
        )

        with self.assertRaisesRegex(
            GateError,
            "candidate_artifact_alias",
        ):
            dual.run_dual_gate(**paths)

    def test_rejects_tampered_custody_receipt(self):
        paths, *_ = _write_case(self.tmp_path)
        receipt = json.loads(
            paths["predecessor_b_receipt_path"].read_text(
                encoding="utf-8"
            )
        )
        receipt["sha256"]["baseline_games"] = "f" * 64
        _write_json(
            paths["predecessor_b_receipt_path"],
            receipt,
        )

        with self.assertRaisesRegex(
            GateError,
            "exact file SHA-256 binding drift",
        ):
            dual.run_dual_gate(**paths)

    def test_rejects_candidate_panel_substitution_after_receipts(self):
        paths, *_ = _write_case(self.tmp_path)
        with paths["candidate_games_path"].open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write("\n")

        with self.assertRaisesRegex(
            GateError,
            "exact file SHA-256 binding drift",
        ):
            dual.run_dual_gate(**paths)

    def test_rejects_wrong_receipt_exact_command(self):
        paths, *_ = _write_case(self.tmp_path)
        receipt = json.loads(
            paths["predecessor_a_receipt_path"].read_text(
                encoding="utf-8"
            )
        )
        receipt["exact_command"] = "python wrong-runner.py"
        _write_json(
            paths["predecessor_a_receipt_path"],
            receipt,
        )

        with self.assertRaisesRegex(
            GateError,
            "run identity drift",
        ):
            dual.run_dual_gate(**paths)

    def test_rejects_cached_or_wrong_inner_candidate_bytes(self):
        paths, *_ = _write_case(self.tmp_path)
        original = dual.single_gate.run_gate

        def stale_gate(**kwargs):
            report, code = original(**kwargs)
            report = deepcopy(report)
            report["input_sha256"][
                "candidate_games"
            ] = "f" * 64
            return report, code

        with patch.object(
            dual.single_gate,
            "run_gate",
            side_effect=stale_gate,
        ):
            with self.assertRaisesRegex(
                GateError,
                "input binding drift",
            ):
                dual.run_dual_gate(**paths)

    def test_cli_writes_bound_promote_report(self):
        paths, *_ = _write_case(self.tmp_path)
        report_path = self.tmp_path / "dual-report.json"

        code = dual.main([
            "--predecessor-a-contract",
            str(paths["predecessor_a_contract_path"]),
            "--predecessor-a-evidence",
            str(paths["predecessor_a_evidence_path"]),
            "--predecessor-a-games",
            str(paths["predecessor_a_games_path"]),
            "--predecessor-a-receipt",
            str(paths["predecessor_a_receipt_path"]),
            "--predecessor-a-artifact",
            str(paths["predecessor_a_artifact_path"]),
            "--predecessor-b-contract",
            str(paths["predecessor_b_contract_path"]),
            "--predecessor-b-evidence",
            str(paths["predecessor_b_evidence_path"]),
            "--predecessor-b-games",
            str(paths["predecessor_b_games_path"]),
            "--predecessor-b-receipt",
            str(paths["predecessor_b_receipt_path"]),
            "--predecessor-b-artifact",
            str(paths["predecessor_b_artifact_path"]),
            "--candidate-games",
            str(paths["candidate_games_path"]),
            "--candidate-artifact",
            str(paths["candidate_artifact_path"]),
            "--engine-artifact",
            str(paths["engine_artifact_path"]),
            "--runner-artifact",
            str(paths["runner_artifact_path"]),
            "--report",
            str(report_path),
            "--quiet",
        ])

        payload = json.loads(
            report_path.read_text(encoding="utf-8")
        )
        self.assertEqual(code, 0)
        self.assertIs(payload["valid"], True)
        self.assertEqual(payload["verdict"], "PROMOTE")
        self.assertEqual(
            payload["mode"],
            "dual-predecessor-custody-bound",
        )
        self.assertEqual(len(payload["input_sha256"]), 14)


if __name__ == "__main__":
    unittest.main()

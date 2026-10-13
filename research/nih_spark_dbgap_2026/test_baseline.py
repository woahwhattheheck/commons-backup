from __future__ import annotations

import copy
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .baseline import (
    ONT_NONE,
    ContractError,
    Corpus,
    ResourceManifest,
    build_run_receipt,
    evaluate_track1,
    evaluate_track2,
    load_json_strict,
    load_json_strict_bytes,
    scan_source_for_query_keyed_hardcoding,
    semantic_sha256,
    track1_predict,
    track2_rank,
    verify_run_receipt,
)
from .publication import PairPublicationError, publish_pair
from . import publication as publication_module

ROOT = Path(__file__).parent
FIX = ROOT / "fixtures"
REPO = ROOT.parents[1]


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.corpus_raw = load_json_strict(FIX / "synthetic_corpus.json")
        self.resources_raw = load_json_strict(FIX / "synthetic_resources.json")
        self.corpus = Corpus.from_obj(self.corpus_raw)
        self.resources = ResourceManifest.from_obj(self.resources_raw)

    def test_json_hostiles(self):
        with self.assertRaises(ContractError):
            load_json_strict_bytes(b'{"a":1,"a":2}')
        with self.assertRaises(ContractError):
            load_json_strict_bytes(b'{"a":NaN}')
        bad = copy.deepcopy(self.corpus_raw)
        bad["concepts"][0]["extra"] = True
        with self.assertRaises(ContractError):
            Corpus.from_obj(bad)
        bad = copy.deepcopy(self.corpus_raw)
        bad["variables"][0]["text"] += " changed"
        with self.assertRaises(ContractError):
            Corpus.from_obj(bad)

    def test_path_ingress_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            target, link = Path(td) / "target.json", Path(td) / "link.json"
            target.write_bytes(b'{"ok":true}')
            try:
                os.symlink(target, link)
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            with self.assertRaises(ContractError):
                load_json_strict(link)

    def test_path_ingress_rejects_ancestor_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            actual = root / "actual"
            actual.mkdir()
            (actual / "input.json").write_bytes(b'{"ok":true}')
            alias = root / "alias"
            try:
                os.symlink(actual, alias, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlink unavailable: {exc}")
            with self.assertRaises(ContractError):
                load_json_strict(alias / "input.json")

    def test_path_ingress_detects_ancestor_generation_swap(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            parent = root / "live"
            parent.mkdir()
            selected = parent / "input.json"
            selected.write_bytes(b'{"generation":"original"}')
            displaced = root / "original-parent"
            real_read = os.read
            swapped = False

            def read_and_swap(fd: int, count: int) -> bytes:
                nonlocal swapped
                data = real_read(fd, count)
                if data and not swapped:
                    swapped = True
                    parent.rename(displaced)
                    parent.mkdir()
                    (parent / "input.json").write_bytes(b'{"generation":"replacement"}')
                return data

            with patch("research.nih_spark_dbgap_2026.core.os.read", side_effect=read_and_swap):
                with self.assertRaisesRegex(ContractError, "parent directory generation changed"):
                    load_json_strict(selected)
            self.assertEqual((displaced / "input.json").read_bytes(), b'{"generation":"original"}')
            self.assertEqual((parent / "input.json").read_bytes(), b'{"generation":"replacement"}')

    def test_track1_fixture_maps_and_abstains(self):
        inp = load_json_strict(FIX / "track1_input.json")
        out = track1_predict(self.corpus, inp, abstain_coverage_bp=5000, top_k=4)
        got = {
            row["query_variable_id"]: row["predicted_concept_id"]
            for row in out["predictions"]
        }
        self.assertEqual(got["fixture-track1-bmi-001"], "C_BMI")
        self.assertEqual(got["fixture-track1-ckd-002"], "C_CKD")
        self.assertEqual(got["fixture-track1-none-003"], ONT_NONE)
        stripped = dict(out)
        claimed = stripped.pop("output_sha256")
        self.assertEqual(claimed, semantic_sha256(stripped))

    def test_track1_order_invariant_and_bool_rejected(self):
        inp = load_json_strict(FIX / "track1_input.json")
        rev = {"schema": inp["schema"], "variables": list(reversed(inp["variables"]))}
        self.assertEqual(track1_predict(self.corpus, inp), track1_predict(self.corpus, rev))
        with self.assertRaises(ContractError):
            track1_predict(
                self.corpus,
                {"schema": inp["schema"], "variables": []},
                abstain_coverage_bp=True,
            )

    def test_track1_macro_f1_includes_none(self):
        result = evaluate_track1(
            {"a": "C_AGE", "b": ONT_NONE, "c": "C_ASTHMA", "d": "C_ASTHMA"},
            {"a": "C_AGE", "b": ONT_NONE, "c": "C_AGE", "d": "C_ASTHMA"},
        )
        self.assertTrue(result["includes_ont_none"])
        self.assertGreater(result["macro_f1_scaled_1e6"], 0)

    def test_track2_fixture_intersection_and_order(self):
        inp = load_json_strict(FIX / "track2_input.json")
        out = track2_rank(self.corpus, inp, top_k=4)
        by_q = {row["query_id"]: row["ranked_studies"] for row in out["results"]}
        self.assertEqual(by_q["fixture-track2-asthma-001"][0]["study_id"], "phs001")
        self.assertEqual(by_q["fixture-track2-kidney-002"][0]["study_id"], "phs003")
        rev = {"schema": inp["schema"], "queries": list(reversed(inp["queries"]))}
        self.assertEqual(out, track2_rank(self.corpus, rev, top_k=4))

    def test_ndcg_perfect_degraded_and_duplicate(self):
        rel = {"q": {"phs001": 3, "phs002": 1, "phs003": 0}}
        perfect = evaluate_track2({"q": ["phs001", "phs002", "phs003"]}, rel, k=3)
        bad = evaluate_track2({"q": ["phs003", "phs002", "phs001"]}, rel, k=3)
        self.assertEqual(perfect["mean_ndcg_scaled_1e9"], 1_000_000_000)
        self.assertLess(bad["mean_ndcg_scaled_1e9"], perfect["mean_ndcg_scaled_1e9"])
        with self.assertRaises(ContractError):
            evaluate_track2(
                {"q": ["phs001", "phs001"]},
                {"q": {"phs001": 2}},
                k=2,
            )

    def test_receipt_binds_input_output_policy_and_resources(self):
        inp = load_json_strict(FIX / "track2_input.json")
        out = track2_rank(self.corpus, inp, top_k=2)
        policy = {"top_k": 2}
        rec = build_run_receipt(
            track=2,
            corpus=self.corpus,
            resources=self.resources,
            input_obj=inp,
            output_obj=out,
            source_version="test-v1",
            policy=policy,
        )
        self.assertTrue(
            verify_run_receipt(
                rec,
                track=2,
                corpus=self.corpus,
                resources=self.resources,
                input_obj=inp,
                output_obj=out,
                source_version="test-v1",
                policy=policy,
            )
        )
        changed = copy.deepcopy(out)
        changed["results"][0]["ranked_studies"].reverse()
        self.assertFalse(
            verify_run_receipt(
                rec,
                track=2,
                corpus=self.corpus,
                resources=self.resources,
                input_obj=inp,
                output_obj=changed,
                source_version="test-v1",
                policy=policy,
            )
        )

    def test_runtime_has_no_fixture_query_lookup_keys(self):
        runtime = "".join(
            (ROOT / name).read_text(encoding="utf-8")
            for name in [
                "core.py",
                "contracts.py",
                "track1.py",
                "track2.py",
                "baseline.py",
                "publication.py",
                "cli.py",
            ]
        )
        ids = ["fixture-track1-bmi-001", "fixture-track2-asthma-001"]
        self.assertEqual(scan_source_for_query_keyed_hardcoding(runtime, ids), [])
        self.assertEqual(
            scan_source_for_query_keyed_hardcoding(
                runtime + "# fixture-track2-asthma-001",
                ids,
            ),
            ["fixture-track2-asthma-001"],
        )

    def test_pair_publication_success_and_alias_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output, receipt = root / "output.json", root / "receipt.json"
            result = publish_pair(output, b"output\n", receipt, b"receipt\n")
            self.assertEqual(result["status"], "COMMITTED")
            self.assertEqual(output.read_bytes(), b"output\n")
            self.assertEqual(receipt.read_bytes(), b"receipt\n")
            self.assertEqual(list(root.glob(".spark-stage-*")), [])

        with tempfile.TemporaryDirectory() as td:
            same = Path(td) / "same.json"
            with self.assertRaisesRegex(ContractError, "distinct destinations"):
                publish_pair(same, b"output\n", same, b"receipt\n")
            self.assertFalse(same.exists())
            self.assertEqual(list(Path(td).glob(".spark-stage-*")), [])

    def test_pair_publication_preexisting_second_refuses_before_first_commit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output, receipt = root / "output.json", root / "receipt.json"
            receipt.write_bytes(b"foreign")
            with self.assertRaisesRegex(ContractError, "refusing to overwrite"):
                publish_pair(output, b"output\n", receipt, b"receipt\n")
            self.assertFalse(output.exists())
            self.assertEqual(receipt.read_bytes(), b"foreign")
            self.assertEqual(list(root.glob(".spark-stage-*")), [])

    def test_pair_publication_second_commit_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output, receipt = root / "output.json", root / "receipt.json"
            real_link = os.link
            calls = 0

            def fail_second_link(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    return real_link(*args, **kwargs)
                raise FileExistsError("simulated second commit race")

            with patch.object(publication_module.os, "link", side_effect=fail_second_link):
                with self.assertRaises(PairPublicationError) as ctx:
                    publish_pair(output, b"output\n", receipt, b"receipt\n")
            self.assertEqual(ctx.exception.status, "ROLLED_BACK_NO_SELECTED_OUTPUTS")
            self.assertFalse(output.exists())
            self.assertFalse(receipt.exists())
            self.assertEqual(list(root.glob(".spark-stage-*")), [])

    def test_pair_publication_foreign_replacement_is_ambiguous_and_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output, receipt = root / "output.json", root / "receipt.json"
            displaced = root / "owned-output.json"
            real_link = os.link
            calls = 0

            def replace_after_first_link(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    result = real_link(*args, **kwargs)
                    output.rename(displaced)
                    output.write_bytes(b"foreign")
                    return result
                raise FileExistsError("simulated second commit race")

            with patch.object(publication_module.os, "link", side_effect=replace_after_first_link):
                with self.assertRaises(PairPublicationError) as ctx:
                    publish_pair(output, b"owned\n", receipt, b"receipt\n")
            self.assertEqual(ctx.exception.status, "AMBIGUOUS_INSPECT_OUTPUTS")
            self.assertEqual(output.read_bytes(), b"foreign")
            self.assertEqual(displaced.read_bytes(), b"owned\n")
            self.assertFalse(receipt.exists())
            self.assertEqual(list(root.glob(".spark-stage-*")), [])

    def _cli_command(self, output: Path, receipt: Path) -> list[str]:
        return [
            sys.executable,
            "-m",
            "research.nih_spark_dbgap_2026.cli",
            "--track",
            "2",
            "--corpus",
            str(FIX / "synthetic_corpus.json"),
            "--resources",
            str(FIX / "synthetic_resources.json"),
            "--input",
            str(FIX / "track2_input.json"),
            "--output",
            str(output),
            "--receipt",
            str(receipt),
            "--source-version",
            "test-v1",
            "--top-k",
            "4",
        ]

    def test_cli_create_exclusive_pair(self):
        with tempfile.TemporaryDirectory() as td:
            out, rec = Path(td) / "out.json", Path(td) / "receipt.json"
            cmd = self._cli_command(out, rec)
            first = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn('"status": "COMMITTED"', first.stdout)
            second = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("refusing to overwrite", second.stderr)
            self.assertTrue(out.exists())
            self.assertTrue(rec.exists())

    def test_cli_same_output_and_receipt_refuses_without_publication(self):
        with tempfile.TemporaryDirectory() as td:
            same = Path(td) / "same.json"
            result = subprocess.run(
                self._cli_command(same, same),
                cwd=REPO,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("distinct destinations", result.stderr)
            self.assertFalse(same.exists())
            self.assertEqual(list(Path(td).glob(".spark-stage-*")), [])


if __name__ == "__main__":
    unittest.main()

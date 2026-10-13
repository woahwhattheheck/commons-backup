import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import kylin_memory_bench as bench

DATASET = ROOT / "sample" / "dataset.jsonl"
REFERENCE = ROOT / "sample" / "reference-agent.json"
FORGETFUL = ROOT / "sample" / "forgetful-agent.json"


class ProvenanceSingleReadTests(unittest.TestCase):
    def test_score_hashes_exact_evidence_bytes_that_were_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            evidence = tmp_path / "evidence.json"
            original = REFERENCE.read_bytes()
            evidence.write_bytes(original)
            mutated = json.loads(original.decode("utf-8"))
            mutated["agent"] = "MUTATED-AFTER-READ"
            mutated_bytes = json.dumps(mutated).encode("utf-8")
            out = tmp_path / "reports"

            real_loader = bench._load_evidence_with_sha

            def load_then_mutate(path, scenario_ids):
                payload, digest = real_loader(path, scenario_ids)
                if Path(path) == evidence:
                    evidence.write_bytes(mutated_bytes)
                return payload, digest

            with mock.patch.object(bench, "_load_evidence_with_sha", side_effect=load_then_mutate):
                rc = bench.main([
                    "score", "--dataset", str(DATASET), "--evidence", str(evidence),
                    "--out-dir", str(out),
                ])

            self.assertEqual(rc, 0)
            report = json.loads((out / "reference-agent.report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["agent"], "reference-agent")
            self.assertEqual(report["provenance"]["evidence_sha256"], hashlib.sha256(original).hexdigest())
            self.assertNotEqual(report["provenance"]["evidence_sha256"], hashlib.sha256(mutated_bytes).hexdigest())

    def test_score_hashes_exact_dataset_bytes_that_were_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dataset = tmp_path / "dataset.jsonl"
            original = DATASET.read_bytes()
            dataset.write_bytes(original)
            mutated_bytes = original + b"\n# mutated after capture\n"
            out = tmp_path / "reports"

            real_loader = bench._read_dataset_with_sha

            def load_then_mutate(path):
                scenarios, digest = real_loader(path)
                if Path(path) == dataset:
                    dataset.write_bytes(mutated_bytes)
                return scenarios, digest

            with mock.patch.object(bench, "_read_dataset_with_sha", side_effect=load_then_mutate):
                rc = bench.main([
                    "score", "--dataset", str(dataset), "--evidence", str(REFERENCE),
                    "--out-dir", str(out),
                ])

            self.assertEqual(rc, 0)
            report = json.loads((out / "reference-agent.report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["provenance"]["dataset_sha256"], hashlib.sha256(original).hexdigest())
            self.assertNotEqual(report["provenance"]["dataset_sha256"], hashlib.sha256(mutated_bytes).hexdigest())

    def test_compare_hashes_each_evidence_capture_not_later_path_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            left = tmp_path / "left.json"
            right = tmp_path / "right.json"
            left_original = REFERENCE.read_bytes()
            right_original = FORGETFUL.read_bytes()
            left.write_bytes(left_original)
            right.write_bytes(right_original)
            mutated = json.loads(left_original.decode("utf-8"))
            mutated["agent"] = "MUTATED-AFTER-READ"
            mutated_bytes = json.dumps(mutated).encode("utf-8")
            out = tmp_path / "reports"

            real_loader = bench._load_evidence_with_sha

            def load_then_mutate(path, scenario_ids):
                payload, digest = real_loader(path, scenario_ids)
                if Path(path) == left:
                    left.write_bytes(mutated_bytes)
                return payload, digest

            with mock.patch.object(bench, "_load_evidence_with_sha", side_effect=load_then_mutate):
                rc = bench.main([
                    "compare", "--dataset", str(DATASET),
                    "--evidence", str(left), "--evidence", str(right),
                    "--out-dir", str(out),
                ])

            self.assertEqual(rc, 0)
            comparison = json.loads((out / "comparison.json").read_text(encoding="utf-8"))
            by_agent = {report["agent"]: report for report in comparison}
            self.assertIn("reference-agent", by_agent)
            self.assertEqual(
                by_agent["reference-agent"]["provenance"]["evidence_sha256"],
                hashlib.sha256(left_original).hexdigest(),
            )
            self.assertNotEqual(
                by_agent["reference-agent"]["provenance"]["evidence_sha256"],
                hashlib.sha256(mutated_bytes).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()

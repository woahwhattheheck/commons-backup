from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import memory_dynamics as md  # noqa: E402


class FakeBaseline:
    DIMENSIONS = md.DIMENSIONS

    @staticmethod
    def validate_dataset(rows):
        seen = set()
        dims = set()
        for row in rows:
            if row["id"] in seen:
                raise ValueError("duplicate")
            seen.add(row["id"])
            dims.add(row["dimension"])
        if dims != set(md.DIMENSIONS):
            raise ValueError("missing dimension")

    @staticmethod
    def validate_evidence(payload, scenario_ids):
        if not isinstance(payload.get("records"), list):
            raise ValueError("records")
        seen = set()
        for record in payload["records"]:
            sid = record["scenario_id"]
            if sid not in scenario_ids or sid in seen:
                raise ValueError("scenario")
            seen.add(sid)

    @staticmethod
    def _norm(value):
        return " ".join(value.casefold().split())

    @classmethod
    def score(cls, rows, evidence):
        cls.validate_evidence(evidence, {row["id"] for row in rows})
        record_map = {row["scenario_id"]: row for row in evidence["records"]}
        de = defaultdict(float)
        dt = defaultdict(float)
        scenarios = []
        for row in rows:
            channels = record_map.get(row["id"], {}).get("channels", {})
            earned = total = 0.0
            results = []
            for assertion in row["assertions"]:
                items = channels.get(assertion["channel"], [])
                atype = assertion["type"]
                if atype == "contains":
                    needle = cls._norm(assertion["value"])
                    passed = any(needle in cls._norm(item) for item in items)
                elif atype == "not_contains":
                    needle = cls._norm(assertion["value"])
                    passed = not any(needle in cls._norm(item) for item in items)
                elif atype == "latest_equals":
                    passed = bool(items) and cls._norm(items[-1]) == cls._norm(assertion["value"])
                elif atype == "ordered_contains":
                    cursor = 0
                    values = assertion["values"]
                    for item in items:
                        if cursor < len(values) and cls._norm(values[cursor]) in cls._norm(item):
                            cursor += 1
                    passed = cursor == len(values)
                else:
                    raise ValueError(atype)
                total += 1.0
                if passed:
                    earned += 1.0
                results.append({"passed": passed, "type": atype, "channel": assertion["channel"]})
            de[row["dimension"]] += earned
            dt[row["dimension"]] += total
            scenarios.append(
                {
                    "id": row["id"],
                    "dimension": row["dimension"],
                    "score": round(100.0 * earned / total, 2),
                    "assertions": results,
                }
            )
        return {
            "agent": evidence["agent"],
            "overall": round(100.0 * sum(de.values()) / sum(dt.values()), 2),
            "dimensions": {dim: round(100.0 * de[dim] / dt[dim], 2) for dim in md.DIMENSIONS},
            "scenarios": scenarios,
        }

    @staticmethod
    def _radar_svg(reports):
        return "<svg>" + ",".join(report["agent"] for report in reports) + "</svg>\n"


class DynamicsTests(unittest.TestCase):
    def test_suite_is_deterministic_and_complete(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a"
            b = Path(td) / "b"
            ma = md.compile_suite(a, variants=3)
            mb = md.compile_suite(b, variants=3)
            self.assertEqual(ma["dataset_sha256"], mb["dataset_sha256"])
            self.assertEqual((a / "dataset.jsonl").read_bytes(), (b / "dataset.jsonl").read_bytes())
            self.assertEqual(ma["scenario_count"], 18)
            self.assertEqual(set(ma["dimensions"]), set(md.DIMENSIONS))
            self.assertEqual(set(ma["risk_tags"]), set(md.RISK_TAGS))

    def test_suite_manifest_detects_dataset_drift(self):
        with tempfile.TemporaryDirectory() as td:
            suite = Path(td) / "suite"
            md.compile_suite(suite)
            with (suite / "dataset.jsonl").open("ab") as fh:
                fh.write(b" ")
            with self.assertRaisesRegex(ValueError, "digest"):
                md.synthesize_trials(suite, Path(td) / "evidence")

    def test_stable_trials_are_perfect_and_stable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            suite = root / "suite"
            evidence = root / "evidence"
            results = root / "results"
            md.compile_suite(suite, variants=3)
            md.synthesize_trials(suite, evidence, trials=5)
            md.aggregate_trials(suite, evidence, results, baseline=FakeBaseline)
            summary = json.loads((results / "stability_summary.json").read_text())
            stable = summary["agents"]["stable-agent"]
            self.assertEqual(stable["overall"]["mean"], 100.0)
            self.assertEqual(stable["overall"]["pstdev"], 0.0)
            self.assertEqual(stable["unique_dimension_score_vectors"], 1)
            self.assertTrue(all(item["rate"] == 0.0 for item in stable["risk_error_rates"].values()))

    def test_volatile_profile_exposes_targeted_failures_and_variance(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            suite = root / "suite"
            evidence = root / "evidence"
            results = root / "results"
            md.compile_suite(suite, variants=3)
            md.synthesize_trials(suite, evidence, trials=5)
            md.aggregate_trials(suite, evidence, results, baseline=FakeBaseline)
            summary = json.loads((results / "stability_summary.json").read_text())
            volatile = summary["agents"]["volatile-agent"]
            self.assertLess(volatile["overall"]["mean"], 100.0)
            self.assertGreater(volatile["overall"]["pstdev"], 0.0)
            self.assertGreater(volatile["unique_dimension_score_vectors"], 1)
            for tag in md.RISK_TAGS:
                self.assertGreater(volatile["risk_error_rates"][tag]["rate"], 0.0)

    def test_evidence_generation_is_bound_to_dataset_digest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            suite = root / "suite"
            evidence = root / "evidence"
            results = root / "results"
            md.compile_suite(suite)
            md.synthesize_trials(suite, evidence, trials=2)
            path = sorted(evidence.glob("*.json"))[0]
            payload = json.loads(path.read_text())
            payload["suite_sha256"] = "0" * 64
            path.write_text(json.dumps(payload) + "\n")
            with self.assertRaisesRegex(ValueError, "different dataset generation"):
                md.aggregate_trials(suite, evidence, results, baseline=FakeBaseline)

    def test_duplicate_trial_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            suite = root / "suite"
            evidence = root / "evidence"
            md.compile_suite(suite)
            md.synthesize_trials(suite, evidence, trials=2)
            src = sorted(evidence.glob("stable-agent*.json"))[0]
            (evidence / "copy.json").write_bytes(src.read_bytes())
            with self.assertRaisesRegex(ValueError, "duplicate trial identity"):
                md.aggregate_trials(suite, evidence, root / "results", baseline=FakeBaseline)

    def test_mismatched_trial_indexes_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            suite = root / "suite"
            evidence = root / "evidence"
            md.compile_suite(suite)
            md.synthesize_trials(suite, evidence, trials=3)
            victim = evidence / "volatile-agent.trial-002.json"
            victim.unlink()
            with self.assertRaisesRegex(ValueError, "same ordered trial indexes"):
                md.aggregate_trials(suite, evidence, root / "results", baseline=FakeBaseline)

    def test_receipt_detects_evidence_tampering(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            suite = root / "suite"
            evidence = root / "evidence"
            results = root / "results"
            md.compile_suite(suite)
            md.synthesize_trials(suite, evidence, trials=2)
            md.aggregate_trials(suite, evidence, results, baseline=FakeBaseline)
            check = md.verify_receipt(suite, evidence, results)
            self.assertTrue(check["valid"])
            path = sorted(evidence.glob("*.json"))[0]
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                md.verify_receipt(suite, evidence, results)

    def test_demo_rebuild_is_byte_reproducible(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root / "a"
            b = root / "b"
            md.build_demo(a, variants=2, trials=3, baseline=FakeBaseline)
            md.build_demo(b, variants=2, trials=3, baseline=FakeBaseline)
            rels = [
                Path("suite/dataset.jsonl"),
                Path("suite/suite_manifest.json"),
                Path("results/stability_summary.json"),
                Path("results/receipt.json"),
            ]
            for rel in rels:
                self.assertEqual((a / rel).read_bytes(), (b / rel).read_bytes(), str(rel))

    def test_reserved_and_overlong_output_names_are_rejected(self):
        with self.assertRaises(ValueError):
            md._safe_slug("CON")
        with self.assertRaises(ValueError):
            md._safe_slug("x" * 121)
        self.assertEqual(md._safe_slug("safe agent"), "safe-agent")

    def test_default_baseline_contract_when_repo_module_is_available(self):
        spec = importlib.util.find_spec("kylin_memory_bench")
        if spec is None:
            self.skipTest("exact landed baseline module is not present in isolated local fixture")
        baseline = md._load_baseline()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = md.build_demo(root, variants=2, trials=3, baseline=baseline)
            self.assertTrue(result["verified"]["valid"])


if __name__ == "__main__":
    unittest.main()

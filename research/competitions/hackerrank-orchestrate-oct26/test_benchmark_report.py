import json
import tempfile
import unittest
from pathlib import Path

import benchmark_report as bench


class BenchmarkReportTests(unittest.TestCase):
    def test_summary_metrics(self):
        cases = [
            {
                "case_id": "a",
                "expected_action": "answer",
                "actual_action": "answer",
                "answer_correct": True,
                "latency_ms": 100,
                "retries": 0,
                "failure_injected": False,
                "recovered": False,
                "injection_case": False,
                "injection_contained": None,
                "gold_evidence": {"g1", "g2"},
                "used_evidence": {"g1"},
                "tokens": 10,
            },
            {
                "case_id": "b",
                "expected_action": "escalate",
                "actual_action": "answer",
                "answer_correct": False,
                "latency_ms": 200,
                "retries": 1,
                "failure_injected": True,
                "recovered": True,
                "injection_case": True,
                "injection_contained": False,
                "gold_evidence": set(),
                "used_evidence": set(),
                "tokens": 20,
            },
            {
                "case_id": "c",
                "expected_action": "escalate",
                "actual_action": "escalate",
                "answer_correct": None,
                "latency_ms": 300,
                "retries": 0,
                "failure_injected": True,
                "recovered": False,
                "injection_case": True,
                "injection_contained": True,
                "gold_evidence": {"g3"},
                "used_evidence": {"g3"},
                "tokens": None,
            },
        ]
        report = bench.summarize(cases)
        self.assertEqual(report["success"]["count"], 2)
        self.assertEqual(report["success"]["false_reply"], 1)
        self.assertEqual(report["latency_ms"]["p50"], 200.0)
        self.assertEqual(report["latency_ms"]["p95"], 290.0)
        self.assertEqual(report["failure_recovery"]["rate"], 0.5)
        self.assertEqual(report["prompt_injection"]["containment_rate"], 0.5)
        self.assertEqual(report["retrieval"]["micro_recall"], 2 / 3)

    def test_loader_rejects_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cases.jsonl"
            row = {
                "case_id": "same",
                "expected_action": "escalate",
                "actual_action": "escalate",
                "latency_ms": 1,
            }
            path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaises(bench.BenchmarkError):
                bench.load_cases(path)

    def test_loader_rejects_incomplete_answer_case(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cases.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "case_id": "x",
                        "expected_action": "answer",
                        "actual_action": "answer",
                        "latency_ms": 1,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(bench.BenchmarkError):
                bench.load_cases(path)


if __name__ == "__main__":
    unittest.main()

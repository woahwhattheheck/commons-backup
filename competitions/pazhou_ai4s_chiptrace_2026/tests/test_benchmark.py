import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("chiptrace_benchmark", HERE / "benchmark.py")
bench = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["chiptrace_benchmark"] = bench
SPEC.loader.exec_module(bench)


class ChipTraceBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_frozen_corpus_hits_expected_qc_states(self):
        corpus = bench.build_frozen_corpus(self.root)
        observed = {}
        for scenario in bench.SCENARIOS:
            baseline, candidate = corpus[scenario.name]
            observed[scenario.name] = bench.ct.analyze(baseline, candidate)["overall_state"]
        self.assertEqual(
            observed,
            {
                "clean": "SUPPORTED",
                "level_shift": "REVIEW",
                "cadence_gap": "REVIEW",
                "replicate_divergence": "REVIEW",
                "sparse": "INSUFFICIENT_EVIDENCE",
            },
        )

    def test_triage_citations_resolve_and_sparse_abstains(self):
        corpus = bench.build_frozen_corpus(self.root)
        baseline, candidate = corpus["sparse"]
        report = bench.ct.analyze(baseline, candidate)
        triage = bench.triage_report(report)
        self.assertEqual(triage["decision"], "ABSTAIN")
        check = bench.validate_citations(report, triage)
        self.assertEqual(check["valid"], check["total"])
        self.assertEqual(check["failures"], [])

    def test_benchmark_scores_classification_abstention_and_stability(self):
        result = bench.run_benchmark(self.root, repeats=2)
        self.assertEqual(result["qc_only"]["precision"], 1.0)
        self.assertEqual(result["qc_only"]["recall"], 1.0)
        self.assertEqual(result["qc_only"]["f1"], 1.0)
        self.assertEqual(result["qc_only"]["false_flag_rate"], 0.0)
        self.assertEqual(result["evidence_bound_triage"]["f1"], 1.0)
        self.assertEqual(result["evidence_bound_triage"]["abstention_accuracy"], 1.0)
        self.assertEqual(result["evidence_bound_triage"]["citation_validity"], 1.0)
        self.assertEqual(result["evidence_bound_triage"]["decision_churn_rate"], 0.0)
        self.assertGreaterEqual(result["latency_ms"]["median"], 0.0)
        self.assertGreaterEqual(result["latency_ms"]["p95"], result["latency_ms"]["median"])

    def test_citation_validation_detects_tamper(self):
        corpus = bench.build_frozen_corpus(self.root)
        baseline, candidate = corpus["level_shift"]
        report = bench.ct.analyze(baseline, candidate)
        triage = bench.triage_report(report)
        triage["citations"][0]["value"] = "SUPPORTED"
        check = bench.validate_citations(report, triage)
        self.assertLess(check["valid"], check["total"])
        self.assertIn("/overall_state", check["failures"])


if __name__ == "__main__":
    unittest.main()

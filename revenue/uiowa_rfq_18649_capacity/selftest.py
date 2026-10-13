#!/usr/bin/env python3
"""Focused regression/self-test for the UIOWA-095 capacity benchmark."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import benchmark


class CapacityBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compiler_dir = Path(__file__).resolve().parents[1] / "uiowa_rfq_18649_workshare"
        # Historical measurement is deliberately bound to these exact semantic blobs.
        cls.compiler = benchmark.load_compiler(cls.compiler_dir)

    def test_synthetic_sizes_cover_all_twelve_cells(self) -> None:
        for size in benchmark.SIZES:
            candidate_text, authority_text = benchmark.synthetic_inputs(size)
            candidate = json.loads(candidate_text)
            authority = json.loads(authority_text)
            self.assertEqual(len(candidate["source_ids"]), size)
            self.assertEqual(len(authority["sources"]), size)
            self.assertEqual(len(set(candidate["source_ids"])), size)
            cells = {(row["group"], row["dimension"]) for row in authority["sources"]}
            self.assertEqual(len(cells), 12)
            self.assertTrue(all("not a University finding" in row["claim"] for row in authority["sources"]))

    def test_source_count_contract_bounds(self) -> None:
        for bad in (0, 11, 257, 1000):
            with self.assertRaises(ValueError):
                benchmark.synthetic_inputs(bad)

    def test_exact_semantic_blob_pin(self) -> None:
        observed = benchmark.verify_pinned_semantic_sources(self.compiler_dir)
        self.assertEqual(observed, benchmark.PINNED_SEMANTIC_BLOBS)

    def test_pipeline_preserves_authority_and_receipt_invariants(self) -> None:
        result = benchmark.benchmark_size(self.compiler, 12, 3)
        self.assertEqual(result["correctness"]["assessment_cells"], 12)
        self.assertTrue(result["correctness"]["receipt_stable"])
        self.assertTrue(result["correctness"]["json_roundtrip_receipt_preserved"])
        self.assertTrue(result["correctness"]["markdown_receipt_present"])
        self.assertTrue(result["correctness"]["untrusted_mode_only"])
        self.assertFalse(result["correctness"]["current_review_authority"])
        self.assertGreater(result["input_bytes_total"], 0)
        self.assertGreater(result["report_json_bytes"], 0)
        self.assertGreater(result["python_allocation_peak_bytes"], 0)

    def test_markdown_projection_mentions_synthetic_scope_and_no_fleet_limit(self) -> None:
        fake = {
            "baseline_commit": benchmark.PINNED_BASELINE_COMMIT,
            "measurement_scope": "Synthetic scope.",
            "sizes": [{
                "source_count": 12,
                "input_bytes_total": 1024,
                "report_json_bytes": 2048,
                "python_allocation_peak_bytes": 4096,
                "timing": {
                    "pipeline_median_ms": 1.0,
                    "pipeline_p95_ms": 2.0,
                    "dominant_stage_by_median": "verify_ms",
                },
            }],
            "analyst_work": {"operator_step_count": 6},
            "optimization_decision": {"reason": "No unsafe shortcut justified."},
        }
        text = benchmark.render_markdown(fake)
        self.assertIn("Synthetic scope.", text)
        self.assertIn("not a fleet limit", text)
        self.assertIn("6", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

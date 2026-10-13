# SPDX-License-Identifier: Apache-2.0
import importlib.util
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("worker_results", HERE / "check_worker_results.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class WorkerConsumerResultsTests(unittest.TestCase):
    def result(self):
        return json.loads((HERE / "RESULTS.json").read_text())

    def test_exact_sources(self):
        result = self.result()
        self.assertEqual(result["archive_sha256"], check.EXPECTED_ARCHIVE)
        self.assertEqual(result["titan_agent_sha256"], check.EXPECTED_AGENT)
        self.assertEqual(result["deadline_adapter_sha256"], check.EXPECTED_DEADLINE)
        self.assertEqual(result["entrypoint_sha256"], check.EXPECTED_ENTRYPOINT)
        self.assertEqual(result["source_frames_sha256"], check.EXPECTED_FRAMES)

    def test_both_modes_complete(self):
        result = self.result()
        for mode in ("main", "worker"):
            self.assertEqual(result[mode]["actions"], 719)
            self.assertEqual(result[mode]["errors"], [])
            self.assertEqual(result[mode]["mismatched_steps"], [])
            self.assertLess(result[mode]["max_call_seconds"], 2.0)

    def test_no_unexported_fallback_claim(self):
        self.assertIsNone(self.result()["fallback_count"])

    def test_scope_is_not_games(self):
        result = self.result()
        self.assertEqual(result["full_games"], 0)
        self.assertEqual(result["new_seeds"], [])

    def test_worker_overhead_is_retained(self):
        result = self.result()
        self.assertGreater(result["worker_to_main_mean_ratio"], 1.0)
        self.assertGreater(result["worker"]["wall_seconds"], result["main"]["wall_seconds"])

    def test_slowest_rows_are_source_steps(self):
        for mode in ("main", "worker"):
            rows = self.result()[mode]["slowest"]
            self.assertEqual(len(rows), 10)
            self.assertTrue(all(0 <= row["step"] < 719 for row in rows))
            self.assertEqual(rows, sorted(rows, key=lambda row: row["seconds"], reverse=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)

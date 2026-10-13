# SPDX-License-Identifier: Apache-2.0
"""Regression for closure distinction versus finite-panel outcome bytes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import dual_predecessor_gate as dual
from test_dual_predecessor_gate import (
    _write_case,
    _write_jsonl,
    _write_receipt,
)


class EqualResultBytesTests(unittest.TestCase):
    def test_identical_rows_are_valid_for_distinct_bound_predecessors(self):
        with TemporaryDirectory(prefix="dual-gate-equal-results-") as directory:
            (
                paths,
                _first,
                second,
                _first_evidence,
                second_evidence,
                first_rows,
                _second_rows,
                _candidate_rows,
            ) = _write_case(Path(directory))

            # Model two closure-distinct predecessors that happen to produce the
            # same finite-grid terminal rows. Refresh B's receipt after writing
            # those exact result bytes.
            _write_jsonl(paths["predecessor_b_games_path"], first_rows)
            _write_receipt(paths, "b", second, second_evidence)

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
        self.assertEqual(
            report["custody"]["predecessor_a"]["bound_file_sha256"][
                "baseline_games"
            ],
            report["custody"]["predecessor_b"]["bound_file_sha256"][
                "baseline_games"
            ],
        )


if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from materialize_evaluator import (
    EXPECTED_EVALUATOR_BLOB,
    EvaluatorMaterializeError,
    git_blob_sha1,
    materialize_evaluator,
)

HERE = Path(__file__).resolve().parent
LAB = HERE.parent.parent
EVALUATOR = LAB.parent / "cloud-eval" / "evaluate.py"


class EvaluatorMaterializationTests(unittest.TestCase):
    def test_exact_source_materializes_without_mutation(self):
        before = EVALUATOR.read_bytes()
        self.assertEqual(git_blob_sha1(before), EXPECTED_EVALUATOR_BLOB)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evaluate.py"
            receipt = materialize_evaluator(EVALUATOR, output)
            compile(output.read_text(encoding="utf-8"), str(output), "exec")
            self.assertEqual(len(receipt["patched"]["patches"]), 7)
            self.assertFalse(receipt["patched"]["action_mutation"])
        self.assertEqual(EVALUATOR.read_bytes(), before)

    def test_wrong_source_pin_fails_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evaluate.py"
            with self.assertRaises(EvaluatorMaterializeError):
                materialize_evaluator(EVALUATOR, output, expected_blob="0" * 40)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

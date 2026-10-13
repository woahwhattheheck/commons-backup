#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
V4 = HERE.parents[2]
DONOR = V4 / "donor" / "overlay" / "r04_full_router.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


engaged = load(HERE / "materialize_engaged_variant.py", "f3_engaged_variant_test")
rebase = load(HERE / "rebase_current_router.py", "f3_rebase_test")


class EngagedVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = DONOR.read_bytes()

    def test_current_donor_is_still_exact_first_stage_source(self):
        self.assertEqual(rebase.git_blob_sha(self.source), rebase.SOURCE_GIT_BLOB)

    def test_off_is_byte_exact_landed_rebase(self):
        expected = rebase.materialize(self.source)
        actual = engaged.materialize(self.source, enabled=False)
        self.assertEqual(actual, expected)
        self.assertEqual(actual.count(engaged.CALL_OFF.encode()), 1)
        self.assertEqual(actual.count(engaged.CALL_ON.encode()), 0)

    def test_on_changes_only_the_live_admission_literal(self):
        off = engaged.materialize(self.source, enabled=False)
        on = engaged.materialize(self.source, enabled=True)
        self.assertNotEqual(on, off)
        self.assertEqual(on.count(engaged.CALL_OFF.encode()), 0)
        self.assertEqual(on.count(engaged.CALL_ON.encode()), 1)
        self.assertEqual(on, off.replace(engaged.CALL_OFF.encode(), engaged.CALL_ON.encode(), 1))
        ast.parse(on.decode("utf-8"))

    def test_only_v217_planner_call_final_argument_changes(self):
        off = ast.parse(engaged.materialize(self.source, enabled=False).decode("utf-8"))
        on = ast.parse(engaged.materialize(self.source, enabled=True).decode("utf-8"))

        def admission_values(tree):
            result = []
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "_v217_plan" and len(node.args) == 7):
                    tail = node.args[-1]
                    if isinstance(tail, ast.Constant) and type(tail.value) is bool:
                        result.append(tail.value)
            return result

        self.assertEqual(admission_values(off), [False])
        self.assertEqual(admission_values(on), [True])

    def test_drifted_donor_fails_closed(self):
        drifted = self.source + b"\n# drift\n"
        with self.assertRaises(engaged.EngagedVariantError):
            engaged.materialize(drifted, enabled=True)

    def test_non_bool_flag_fails_closed(self):
        with self.assertRaises(engaged.EngagedVariantError):
            engaged.materialize(self.source, enabled=1)

    def test_receipt_names_truth_boundary(self):
        output = engaged.materialize(self.source, enabled=True)
        receipt = engaged.receipt(self.source, output, enabled=True)
        self.assertEqual(receipt["source_git_blob"], rebase.SOURCE_GIT_BLOB)
        self.assertTrue(receipt["enabled"])
        self.assertFalse(receipt["canonical_runtime_mutated"])
        self.assertFalse(receipt["production_activation"])


if __name__ == "__main__":
    unittest.main()

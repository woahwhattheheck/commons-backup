# SPDX-License-Identifier: Apache-2.0
"""Current-source custody tests for the integrated executable-prefix recovery."""
from __future__ import annotations
import ast
from pathlib import Path
import unittest
from fold_integrated_action_prefix import SOURCE_BLOB, fold_bytes, git_blob

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[3]
SOURCE = LAB / "integrated_selected.py"

class IntegratedPrefixRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = SOURCE.read_bytes()
        if git_blob(cls.before) != SOURCE_BLOB:
            raise RuntimeError(f"source drift: {git_blob(cls.before)} != {SOURCE_BLOB}")
        cls.after = fold_bytes(cls.before)
        cls.text = cls.after.decode()

    def test_current_source_is_exactly_pinned(self):
        self.assertEqual(git_blob(self.before), SOURCE_BLOB)
        self.assertNotEqual(self.after, self.before)

    def test_future_purchase_scan_is_executable_prefix_only(self):
        self.assertIn("action.get('market', [])[:maximum]", self.text)
        self.assertNotIn("for o in action.get('market', [])):\n                    reason = 'future_product_purchase_needs_cash_bound'", self.text)

    def test_seed_dependency_scan_is_executable_prefix_only(self):
        self.assertIn("selected.get('market',[])[:maximum]", self.text)
        self.assertIn("proposed.get('market',[])[:maximum]", self.text)
        self.assertIn("selected['market'][i+1:maximum]", self.text)

    def test_cap_matches_engine_minimum_one_rule(self):
        self.assertIn("maximum = max(1, int(cfg.get('maxMarketOrdersPerTurn',10)))", self.text)

    def test_raw_suffix_is_not_deleted_or_compacted(self):
        self.assertNotIn("selected['market'] =", self.text)
        self.assertNotIn("del selected['market']", self.text)

    def test_postimage_parses(self):
        ast.parse(self.text)

    def test_drift_fails_closed(self):
        poisoned = self.before + b"\n# drift\n"
        with self.assertRaisesRegex(ValueError, "source drift"):
            fold_bytes(poisoned)

if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[3]
SPEC = importlib.util.spec_from_file_location(
    "microstack_current_sale_timing", HERE / "current_sale_timing.py"
)
M = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(M)

CURRENT = LAB / "frozen_selected.py"
CANONICAL = (
    LAB
    / "candidates"
    / "v4"
    / "research"
    / "sale-window-engagement"
    / "compose_current_h3s420.py"
)


class CurrentSaleTimingTest(unittest.TestCase):
    def test_control_is_exact_current_bytes(self):
        source = CURRENT.read_bytes()
        self.assertEqual(M.git_blob(source), M.CURRENT_FROZEN_SELECTED_GIT_BLOB)
        self.assertEqual(
            M.compose_current_frozen(
                source, arm="control", canonical_composer_path=CANONICAL
            ),
            source,
        )

    def test_h3_only_shadows_current_baseline_horizon(self):
        source = CURRENT.read_bytes()
        result = M.compose_current_frozen(
            source, arm="h3", canonical_composer_path=CANONICAL
        )
        text = result.decode("utf-8")
        self.assertIn("HORIZON = 3", text)
        self.assertNotIn("H3S420_SUPPRESS_NEW_PLANS_AFTER", text)
        compile(text, "<h3-test>", "exec")

    def test_h3s420_is_exact_canonical_rewrite_on_current_source(self):
        source = CURRENT.read_bytes()
        rewrite = M._load_canonical_rewrite(CANONICAL)
        expected = rewrite(source.decode("utf-8")).encode("utf-8")
        actual = M.compose_current_frozen(
            source, arm="h3_s420", canonical_composer_path=CANONICAL
        )
        self.assertEqual(actual, expected)
        text = actual.decode("utf-8")
        self.assertIn("H3S420_BASELINE_HORIZON = 3", text)
        self.assertIn("H3S420_SUPPRESS_NEW_PLANS_AFTER = 420", text)
        self.assertIn(
            "if now < H3S420_SUPPRESS_NEW_PLANS_AFTER:",
            text,
        )

    def test_canonical_s420_guard_skips_quantity_changing_new_plan_at_threshold(self):
        # This predecessor deliberately places a quantity-changing "new plan"
        # inside the exact block the canonical composer guards. At step 420 the
        # entire block must be skipped, regardless of plan comparability.
        synthetic = (
            M._IMPORT_MARKER
            + "import copy\n"
            + "class FrozenSelected:\n"
            + "    def __init__(self):\n"
            + "        self.diagnostics={}\n"
            + "        self.new_plan_calls=0\n"
            + "    def cash_reserve(self, obs, config, base, end):\n"
            + "        self.new_plan_calls += 1\n"
            + "        return 0\n"
            + "    def transform(self, now, base):\n"
            + "        obs=config=end=None\n"
            + "        budget=self.cash_reserve(obs,config,base,end)\n"
            + "        self.quantity_changing_new_plan=((now,99),)\n"
            + "        out=copy.deepcopy(base)\n"
            + "        return out\n"
        )
        rewrite = M._load_canonical_rewrite(CANONICAL)
        transformed = rewrite(synthetic)

        stub = types.ModuleType("selected_sell_core")
        stub.optimize_lot = lambda **_kwargs: None
        stub.joint_plan_metrics = lambda *_args, **_kwargs: None
        stub.shared_slot_ledger = lambda *_args, **_kwargs: None
        old = sys.modules.get("selected_sell_core")
        sys.modules["selected_sell_core"] = stub
        try:
            namespace = {}
            exec(compile(transformed, "<synthetic-h3s420>", "exec"), namespace)
            cls = namespace["FrozenSelected"]

            late = cls()
            base = {"market": [["SELL", "MILK", 3]]}
            self.assertEqual(late.transform(420, base), base)
            self.assertEqual(late.new_plan_calls, 0)
            self.assertFalse(hasattr(late, "quantity_changing_new_plan"))
            self.assertTrue(late.diagnostics["h3s420"]["new_plan_suppressed"])

            early = cls()
            self.assertEqual(early.transform(419, base), base)
            self.assertEqual(early.new_plan_calls, 1)
            self.assertEqual(early.quantity_changing_new_plan, ((419, 99),))
            self.assertFalse(early.diagnostics["h3s420"]["new_plan_suppressed"])
        finally:
            if old is None:
                sys.modules.pop("selected_sell_core", None)
            else:
                sys.modules["selected_sell_core"] = old

    def test_canonical_composer_drift_fails_closed(self):
        tmp = HERE / ".tampered-h3s420-test.py"
        try:
            tmp.write_text("def _rewrite_source(source): return source\n")
            with self.assertRaisesRegex(ValueError, "composer drift"):
                M._load_canonical_rewrite(tmp)
        finally:
            tmp.unlink(missing_ok=True)

    def test_current_source_drift_and_unknown_arm_fail_closed(self):
        source = CURRENT.read_bytes()
        with self.assertRaisesRegex(ValueError, "source drift"):
            M.compose_current_frozen(
                source + b"\n# drift\n",
                arm="control",
                canonical_composer_path=CANONICAL,
            )
        with self.assertRaisesRegex(ValueError, "arm must"):
            M.compose_current_frozen(
                source, arm="other", canonical_composer_path=CANONICAL
            )

    def test_semantics_receipt_binds_canonical_authority(self):
        receipt = M.canonical_semantics_receipt()
        self.assertEqual(receipt["baseline_horizon"], 3)
        self.assertEqual(receipt["suppress_new_plans_after"], 420)
        self.assertEqual(
            receipt["canonical_composer_git_blob"],
            "7c5778b4d6d7c47f8feca7e800fc8093267b66f8",
        )
        self.assertIn("all new plan selection suppressed", receipt["semantics"])


if __name__ == "__main__":
    unittest.main()

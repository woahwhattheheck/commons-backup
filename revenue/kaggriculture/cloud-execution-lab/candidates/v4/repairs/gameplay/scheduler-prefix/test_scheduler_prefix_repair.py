# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "scheduler_prefix_repair", HERE / "materialize_scheduler_prefix.py"
)
repair = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(repair)


def repo_root() -> Path:
    rel = Path("revenue/kaggriculture/cloud-execution-lab/scheduler.py")
    for parent in HERE.parents:
        if (parent / rel).is_file():
            return parent
    raise AssertionError("repository root not found")


class SchedulerExecutablePrefixRepairTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = repo_root()
        cls.scheduler = cls.root / "revenue/kaggriculture/cloud-execution-lab/scheduler.py"
        cls.engine = cls.root / "revenue/kaggriculture/cloud-execution-lab/reference/engine/kaggriculture.py"
        cls.source_bytes = cls.scheduler.read_bytes()
        cls.engine_bytes = cls.engine.read_bytes()

    def test_current_source_and_engine_are_exactly_pinned(self):
        self.assertEqual(repair.git_blob_sha(self.source_bytes), repair.SOURCE_GIT_BLOB)
        self.assertEqual(repair.git_blob_sha(self.engine_bytes), repair.ENGINE_GIT_BLOB)
        repair.verify_engine(self.engine_bytes.decode("utf-8"))

    def test_current_source_materializes_and_compiles(self):
        out = repair.materialize(self.source_bytes, self.engine_bytes)
        text = out.decode("utf-8")
        self.assertEqual(text.count("def _engine_market_prefix("), 1)
        self.assertEqual(text.count("orders=_engine_market_prefix(market_action,config)"), 2)
        ast.parse(text, filename="<scheduler-prefix-postimage>")
        compile(text, "<scheduler-prefix-postimage>", "exec")

    def test_current_source_has_exact_two_legacy_consumers(self):
        source = self.source_bytes.decode("utf-8")
        self.assertEqual(source.count(repair.CALLSITE.format(name="order")), 1)
        self.assertEqual(source.count(repair.CALLSITE.format(name="o")), 1)

    def test_double_apply_fails_closed(self):
        post = repair.transform(self.source_bytes.decode("utf-8"))
        with self.assertRaises(repair.MaterializationError):
            repair.transform(post)

    def test_helper_matches_official_raw_prefix_shape(self):
        post = repair.transform(self.source_bytes.decode("utf-8"))
        tree = ast.parse(post)
        helper = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_engine_market_prefix"
        )
        ns = {}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), "<prefix-helper>", "exec"), ns)
        prefix = ns["_engine_market_prefix"]
        self.assertEqual(
            prefix({"market": [[], ["HIRE"], ["BUY_LAND"]]}, {"maxMarketOrdersPerTurn": 1}),
            [[]],
        )
        self.assertEqual(
            prefix({"market": [["SELL", "MILK", 1], ["HIRE"]]}, {"maxMarketOrdersPerTurn": 0}),
            [["SELL", "MILK", 1]],
        )
        self.assertEqual(prefix({"market": "not-a-list"}, {"maxMarketOrdersPerTurn": 10}), [])

    def test_suffix_spend_and_receipt_rows_are_engine_inert(self):
        # The official interpreter keeps raw positions and slices before execution.
        action = {"market": [[], ["HIRE"], ["BUY_PRODUCT", "WHEAT", 5]]}
        post = repair.transform(self.source_bytes.decode("utf-8"))
        tree = ast.parse(post)
        helper = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_engine_market_prefix"
        )
        ns = {}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), "<prefix-helper>", "exec"), ns)
        self.assertEqual(ns["_engine_market_prefix"](action, {"maxMarketOrdersPerTurn": 1}), [[]])


if __name__ == "__main__":
    unittest.main()

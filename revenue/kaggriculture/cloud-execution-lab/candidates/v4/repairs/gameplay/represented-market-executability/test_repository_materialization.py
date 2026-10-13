#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "represented_physical_materializer",
    HERE / "materialize_represented_physical_transition.py",
)
carrier = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(carrier)


class RepositoryMaterializationTests(unittest.TestCase):
    def test_exact_current_source_engine_and_prefix_compose(self):
        root = None
        for parent in (HERE, *HERE.parents):
            if (parent / "revenue/kaggriculture/cloud-execution-lab/scheduler.py").is_file():
                root = parent
                break
        if root is None:
            self.skipTest("complete repository checkout not mounted")

        lab = root / "revenue/kaggriculture/cloud-execution-lab"
        source = (lab / "scheduler.py").read_bytes()
        engine = (lab / "reference/engine/kaggriculture.py").read_bytes()
        prefix = (
            lab
            / "candidates/v4/repairs/gameplay/scheduler-prefix/materialize_scheduler_prefix.py"
        ).read_bytes()

        candidate = carrier.materialize(source, engine, prefix)
        text = candidate.decode("utf-8")
        ast.parse(text, filename="<represented-physical-candidate>")
        compile(text, "<represented-physical-candidate>", "exec")

        self.assertEqual(carrier.git_blob_sha(source), carrier.RAW_SCHEDULER_GIT_BLOB)
        self.assertEqual(carrier.git_blob_sha(engine), carrier.ENGINE_GIT_BLOB)
        self.assertEqual(carrier.git_blob_sha(prefix), carrier.PREFIX_MATERIALIZER_GIT_BLOB)
        self.assertEqual(text.count("def _engine_market_prefix("), 1)
        self.assertEqual(text.count("def _represented_market_physical_transition("), 1)
        self.assertEqual(text.count("orders=_engine_market_prefix(market_action,config)"), 2)
        self.assertNotIn("p['shed'][o[1]]=p['shed'].get(o[1],0)+int(o[2])", text)
        self.assertNotIn(
            "f['hands'].append(m._spawn_hand(f,len(f['tiles'])));p['inventories'].append({})",
            text,
        )
        self.assertIn("if not physical.get('resolved',False):", text)
        self.assertIn("return lambda _plan: False", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import math
import pathlib
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
LAB = pathlib.Path(__file__).resolve().parents[5]
sys.path.insert(0, str(HERE))

from compose_native_return_bridge import (
    CONFIG_BLOB,
    FROZEN_BLOB,
    MAIN_BLOB,
    RUNTIME_BLOB,
    SCHEDULER_BLOB,
    compose,
    git_blob_id,
    patch_config,
    patch_main,
    patch_runtime,
    replace_once,
)


class ComposerTests(unittest.TestCase):
    def test_source_pins_are_exact_current_v5_package(self):
        expected = {
            "main.py": MAIN_BLOB,
            "titan_runtime.py": RUNTIME_BLOB,
            "frozen_selected.py": FROZEN_BLOB,
            "scheduler.py": SCHEDULER_BLOB,
            "TITAN-CONFIG.json": CONFIG_BLOB,
        }
        for relative, blob in expected.items():
            with self.subTest(relative=relative):
                self.assertEqual(git_blob_id((LAB / relative).read_bytes()), blob)

    def test_runtime_feature_enters_exact_bool_contract(self):
        out = patch_runtime((LAB / "titan_runtime.py").read_text())
        self.assertEqual(out.count("lockstep_join: bool = False"), 1)
        self.assertEqual(out.count("'lockstep_join',"), 1)
        self.assertIn("lockstep_join requires nonterminal frozen SELL", out)

        tree = ast.parse(out)
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Features")
        start = min([node.lineno, *(item.lineno for item in node.decorator_list)]) - 1
        source = "".join(out.splitlines(keepends=True)[start:node.end_lineno])
        namespace = {"__name__": __name__, "dataclass": dataclass, "math": math}
        exec(source, namespace)
        Features = namespace["Features"]
        self.assertIs(Features(lockstep_join=False).lockstep_join, False)
        self.assertIs(Features(lockstep_join=True).lockstep_join, True)
        for bad in (0, 1, "false", [], None):
            with self.subTest(bad=bad):
                with self.assertRaises(TypeError):
                    Features(lockstep_join=bad)

    def test_main_hooks_current_outer_timer_boundary(self):
        out = patch_main((LAB / "main.py").read_text())
        construction = out.index("if features.lockstep_join:")
        town_check = out.index("town_procurement is the tested nonterminal frozen composition")
        class_start = out.index("class FinalPressureAgent")
        self.assertLess(town_check, construction)
        self.assertLess(construction, class_start)
        self.assertIn("bridge.observe(observation, cfg)", out)
        self.assertLess(out.index("output = instance.act", class_start), out.index("bridge.commit(", class_start))
        self.assertIn("instance._return_bridge = bridge", out)
        self.assertIn("stage = 'lockstep_join'", out)

    def test_current_package_materializes_default_off_transaction(self):
        with tempfile.TemporaryDirectory() as td:
            package = pathlib.Path(td) / "package"
            package.mkdir()
            for relative in (
                "main.py", "titan_runtime.py", "frozen_selected.py",
                "scheduler.py", "TITAN-CONFIG.json",
            ):
                shutil.copyfile(LAB / relative, package / relative)

            receipt = compose(LAB, package, HERE)
            self.assertEqual(receipt["schema"], "titan-v5-lockstep-return-bridge-composition/v1")
            self.assertIs(receipt["default_enabled"], False)
            self.assertIs(receipt["strict_feature_types"], True)
            config = json.loads((package / "TITAN-CONFIG.json").read_text())
            self.assertIs(config["lockstep_join"], False)
            self.assertTrue((package / "native_return_bridge.py").is_file())
            self.assertTrue((package / "lockstep_effective_flow_bounds.py").is_file())
            self.assertTrue((package / "lockstep_join_queue_contract.py").is_file())
            self.assertIn("'lockstep_join',", (package / "titan_runtime.py").read_text())
            self.assertIn("stage = 'lockstep_join'", (package / "main.py").read_text())

    def test_config_is_default_off_and_v5_bound(self):
        out = patch_config(json.dumps({'early_capital': True, 'town_procurement': True}))
        self.assertIs(json.loads(out)['lockstep_join'], False)
        with self.assertRaises(ValueError):
            patch_config(json.dumps({'early_capital': True, 'town_procurement': False}))

    def test_config_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            patch_config(json.dumps({
                'early_capital': True,
                'town_procurement': True,
                'lockstep_join': False,
            }))

    def test_anchor_drift_rejected(self):
        with self.assertRaises(ValueError):
            replace_once('abc', 'zzz', 'x', 'drift')

    def test_duplicate_anchor_rejected(self):
        with self.assertRaises(ValueError):
            replace_once('aa', 'a', 'x', 'duplicate')


if __name__ == '__main__':
    unittest.main(verbosity=2)

# SPDX-License-Identifier: Apache-2.0
"""Release-source contract for the ordered selected prepared-stage binding."""
import ast
from collections.abc import Mapping
from pathlib import Path
import unittest

import build_integrated


ROOT = Path(__file__).resolve().parent
MIRROR = ROOT / "reference/titan-current/latest/ordered_selected_sell.py"


def _packaged_binding():
    """Load only the packaged binding helpers without importing seller runtime."""
    parsed = ast.parse(MIRROR.read_text(encoding="utf-8"), filename=str(MIRROR))
    names = {"_configuration_value", "_configuration_binding", "_binding"}
    body = [node for node in parsed.body
            if isinstance(node, ast.FunctionDef) and node.name in names]
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "Mapping": Mapping,
        "absolute_step": lambda observation, configuration: observation["step"],
    }
    exec(compile(module, str(MIRROR), "exec"), namespace)
    return namespace["_binding"]


class OrderedSelectedReleaseMirrorTests(unittest.TestCase):
    def test_release_builder_uses_guarded_ordered_mirror(self):
        self.assertEqual(
            build_integrated.source_files()["ordered_selected_sell.py"],
            "reference/titan-current/latest/ordered_selected_sell.py",
        )

    def test_packaged_binding_ignores_nested_mapping_order_only(self):
        binding = _packaged_binding()
        observation = {
            "step": 12,
            "player": 0,
            "farms": [{"money": 10}, {"money": 20}],
            "private": {"shed": {"WHEAT": 1}},
            "market": {"inventory": {"WHEAT": 100}},
            "town": {"unlocked_shops": []},
        }
        action = {"farmer": ["PASS"], "hands": [], "market": []}
        first = {
            "turnsPerDay": 24,
            "nested": {"alpha": 1, "beta": {"x": True, "y": [1, 2]}},
        }
        reordered = {
            "nested": {"beta": {"y": [1, 2], "x": True}, "alpha": 1},
            "turnsPerDay": 24,
        }
        self.assertEqual(
            binding(observation, first, action),
            binding(observation, reordered, action),
        )

        variants = [
            {**first, "turnsPerDay": 24.0},
            {**first, "turnsPerDay": True},
            {**first, "nested": {"alpha": 1, "beta": {"x": True, "y": (1, 2)}}},
        ]
        baseline = binding(observation, first, action)
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertNotEqual(baseline, binding(observation, variant, action))


if __name__ == "__main__":
    unittest.main(verbosity=2)

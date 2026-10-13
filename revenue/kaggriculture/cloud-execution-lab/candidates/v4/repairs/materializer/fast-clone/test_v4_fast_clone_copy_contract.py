# SPDX-License-Identifier: Apache-2.0
"""Mechanism tests; full frozen-corpus check runs when r01_tapes is available."""
import copy
import importlib.util
import itertools
import random
import unittest
from unittest.mock import patch

import ast
import types
from pathlib import Path
import harden_v4_fast_clone_recipe as donor


def embedded_module(helper):
    module = types.ModuleType("fast_clone_recipe_test")
    exec(compile("import copy\n" + helper, "<embedded-fast-clone>", "exec"), module.__dict__)
    module._fast_shape = module._r04_is_fast_tape_action
    module.apply_fast_clone = module._r04_clone_tape_action
    return module


fast = embedded_module(donor.HARDENED_HELPER)


def action():
    return {"farmer": ["PASS"], "hands": [["NORTH"], ["PICKUP", "WHEAT", 2]],
            "market": [["SELL", "WOOL", 4], []]}


def graph(value):
    """Record container identities by traversal index, not process addresses."""
    seen = {}
    def visit(node):
        if isinstance(node, (dict, list, tuple)):
            if id(node) in seen:
                return ("ref", seen[id(node)])
            index = seen[id(node)] = len(seen)
            children = ([(visit(k), visit(v)) for k, v in node.items()]
                        if isinstance(node, dict) else [visit(v) for v in node])
            return (type(node).__name__, index, children)
        return (type(node).__name__, repr(node))
    return visit(value)


class FastCloneTests(unittest.TestCase):
    def check_copy(self, template, expected_fast=None):
        before = graph(template)
        result = fast.apply_fast_clone(template)
        self.assertEqual(graph(result), graph(copy.deepcopy(template)))
        self.assertEqual(graph(template), before)
        if expected_fast is not None:
            self.assertIs(fast._fast_shape(template), expected_fast)
        if isinstance(template, (dict, list)):
            self.assertIsNot(result, template)
        return result

    def test_plain_action_uses_no_deepcopy(self):
        with patch.object(fast.copy, "deepcopy", side_effect=AssertionError("slow path")):
            clone = fast.apply_fast_clone(action())
        self.assertEqual(clone, action())

    def test_all_containers_are_private(self):
        template = action()
        result = self.check_copy(template, True)
        self.assertIsNot(result["farmer"], template["farmer"])
        for key in ("hands", "market"):
            self.assertIsNot(result[key], template[key])
            for left, right in zip(result[key], template[key]):
                self.assertIsNot(left, right)
        result["farmer"].append("x")
        result["hands"][0].append("y")
        result["market"][0][2] = 999
        self.assertEqual(template, action())

    def test_repeated_calls_do_not_alias(self):
        template = action()
        first, second = fast.apply_fast_clone(template), fast.apply_fast_clone(template)
        first["hands"][0].append("changed")
        self.assertEqual(second, template)

    def test_dict_insertion_order(self):
        for order in itertools.permutations(("farmer", "hands", "market")):
            template = {key: action()[key] for key in order}
            self.assertEqual(list(self.check_copy(template, True)), list(order))

    def test_builtin_scalars(self):
        template = {"farmer": ["x", 0, -1, 10**1000, 1.5, True, None,
                               float("inf"), float("nan")], "hands": [[]], "market": [[]]}
        self.check_copy(template, True)

    def test_unknown_keys(self):
        template = action(); template["metadata"] = {"nested": [1]}
        self.check_copy(template, False)

    def test_missing_key(self):
        template = action(); del template["farmer"]
        self.check_copy(template, False)

    def test_non_mapping(self):
        for template in (None, [], "action", 1):
            with self.subTest(template=template):
                self.check_copy(template, False)

    def test_container_subclasses(self):
        class D(dict): pass
        class L(list): pass
        self.check_copy(D(action()), False)
        for key in ("farmer", "hands", "market"):
            template = action(); template[key] = L(template[key])
            self.check_copy(template, False)
        template = action(); template["hands"][0] = L(["PASS"])
        self.check_copy(template, False)

    def test_scalar_and_key_subclasses(self):
        class S(str): pass
        class I(int): pass
        template = action(); template["farmer"][0] = S("PASS")
        self.check_copy(template, False)
        template = action(); template["market"][0][2] = I(2)
        self.check_copy(template, False)
        template = {S(k): v for k, v in action().items()}
        self.check_copy(template, False)

    def test_nested_mutables(self):
        for value in (["x"], {"x": [1]}, (["x"],), {1, 2}):
            template = action(); template["farmer"].append(value)
            result = self.check_copy(template, False)
            self.assertIsNot(result["farmer"][-1], value)

    def test_non_list_rows_and_roots(self):
        for value in (None, (), {}, "PASS", 1):
            for key in ("farmer", "hands", "market"):
                template = action(); template[key] = value
                self.check_copy(template, False)
            for key in ("hands", "market"):
                template = action(); template[key][0] = value
                self.check_copy(template, False)

    def test_shared_sibling_row(self):
        row = ["PASS"]
        template = {"farmer": [], "hands": [row, row], "market": []}
        result = self.check_copy(template, False)
        self.assertIs(result["hands"][0], result["hands"][1])
        self.assertIsNot(result["hands"][0], row)

    def test_shared_farmer_hand_market_row(self):
        row = ["PASS"]
        result = self.check_copy({"farmer": row, "hands": [row], "market": [row]}, False)
        self.assertIs(result["farmer"], result["hands"][0])
        self.assertIs(result["farmer"], result["market"][0])

    def test_shared_top_level_empty_lists(self):
        for first, second in itertools.combinations(("farmer", "hands", "market"), 2):
            template = {"farmer": [], "hands": [], "market": []}
            template[second] = template[first]
            result = self.check_copy(template, False)
            self.assertIs(result[first], result[second])

    def test_cross_level_empty_list_alias(self):
        empty = []
        template = {"farmer": ["PASS"], "hands": [empty], "market": empty}
        result = self.check_copy(template, False)
        self.assertIs(result["hands"][0], result["market"])

    def test_cycles_preserve_graph(self):
        template = action(); template["farmer"].append(template)
        result = self.check_copy(template, False)
        self.assertIs(result["farmer"][-1], result)
        template = action(); template["hands"].append(template["hands"])
        result = self.check_copy(template, False)
        self.assertIs(result["hands"][-1], result["hands"])

    def test_predecessor_alias_counterexample(self):
        row = ["PASS"]
        template = {"farmer": row, "hands": [row], "market": []}
        old = {"farmer": list(template["farmer"]),
               "hands": [list(r) for r in template["hands"]],
               "market": [list(r) for r in template["market"]]}
        self.assertNotEqual(graph(old), graph(copy.deepcopy(template)))
        self.check_copy(template, False)

    def test_generated_shape_matrix(self):
        rng = random.Random(41)
        atoms = ["PASS", "WHEAT", "SELL", 0, 1, 17, None, False, 0.5]
        for _ in range(600):
            row = lambda: [rng.choice(atoms) for _ in range(rng.randrange(5))]
            template = {"farmer": row(),
                        "hands": [row() for _ in range(rng.randrange(9))],
                        "market": [row() for _ in range(rng.randrange(11))]}
            self.check_copy(template, True)

    @unittest.skipUnless(importlib.util.find_spec("r01_tapes"), "frozen tape module not mounted")
    def test_full_frozen_corpus(self):
        from r01_tapes import load_tapes
        tapes = load_tapes()
        self.assertEqual(len(tapes), 13)
        count = 0
        for tape in tapes:
            self.assertEqual(len(tape), 719)
            for template in tape:
                self.check_copy(template, True)
                count += 1
        self.assertEqual(count, 9347)


class RecipePatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = '_R04_JSON_SCALAR_TYPES = frozenset((str, int, float, bool, type(None)))\n\n\ndef _r04_is_fast_tape_action(template):\n    """Return whether template is exactly the shallow-clone-safe R04 JSON action shape."""\n    if (type(template) is not dict or len(template) != 3\n            or "farmer" not in template or "hands" not in template or "market" not in template):\n        return False\n    farmer, hands, market = template["farmer"], template["hands"], template["market"]\n    if type(farmer) is not list or type(hands) is not list or type(market) is not list:\n        return False\n    for value in farmer:\n        if type(value) not in _R04_JSON_SCALAR_TYPES:\n            return False\n    for rows in (hands, market):\n        for row in rows:\n            if type(row) is not list:\n                return False\n            for value in row:\n                if type(value) not in _R04_JSON_SCALAR_TYPES:\n                    return False\n    return True\n\n\ndef _r04_clone_tape_action(template):\n    """Clone the frozen tape schema; fail closed to deepcopy for any future schema."""\n    if not _r04_is_fast_tape_action(template):\n        return copy.deepcopy(template)\n    return {\n        "farmer": list(template["farmer"]),\n        "hands": [list(row) for row in template["hands"]],\n        "market": [list(row) for row in template["market"]],\n    }\n'

    def fixture(self, expression=None):
        return '# untouched prefix: \N{SNOWMAN}\nHELPER = ' + (expression or repr(self.original)) + '\nKEEP = 37\n'

    def test_changes_only_literal(self):
        source = self.fixture()
        output = donor.harden(source)
        self.assertEqual(output, self.fixture(repr(donor.HARDENED_HELPER)))
        value = ast.literal_eval(ast.parse(output).body[0].value)
        runtime = embedded_module(value)
        row = ['PASS']
        template = {'market': [], 'hands': [row], 'farmer': row}
        result = runtime.apply_fast_clone(template)
        self.assertEqual(graph(result), graph(copy.deepcopy(template)))
        self.assertEqual(list(result), list(template))

    def test_wrong_helper_rejected(self):
        with self.assertRaises(ValueError):
            donor.harden(self.fixture(repr(self.original + '# drift')))

    def test_repeat_rejected(self):
        with self.assertRaises(ValueError):
            donor.harden(donor.harden(self.fixture()))

    def test_missing_or_duplicate_rejected(self):
        for source in ('X = 1', self.fixture() + 'HELPER = "duplicate"\n'):
            with self.assertRaises(ValueError):
                donor.harden(source)

    def test_dynamic_rejected(self):
        with self.assertRaises(ValueError):
            donor.harden(self.fixture('str("dynamic")'))

    def test_chained_binding_rejected(self):
        with self.assertRaises(ValueError):
            donor.harden(self.fixture().replace('HELPER = ', 'HELPER = OTHER = '))

    def test_non_string_rejected(self):
        with self.assertRaises(ValueError):
            donor.harden(self.fixture('17'))

    def test_utf8_byte_offsets_and_crlf(self):
        source = self.fixture().replace('HELPER = ', 'TITLE = "☃"; HELPER = ').replace('\n', '\r\n')
        output = donor.harden(source)
        self.assertEqual(output, source.replace(repr(self.original), repr(donor.HARDENED_HELPER)))


if __name__ == "__main__":
    unittest.main()

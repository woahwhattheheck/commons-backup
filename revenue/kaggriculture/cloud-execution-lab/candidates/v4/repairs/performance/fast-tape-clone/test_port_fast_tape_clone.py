# SPDX-License-Identifier: Apache-2.0
"""Exact-parent, default-OFF and literal-recipe integration checks."""
import ast
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import port_fast_tape_clone as port
import r04_fast_tape_clone as helper

HERE = Path(__file__).resolve().parent
PARENT = (HERE / 'parent_apply_v4.py').read_bytes()


def recipe(data):
    tree = ast.parse(data)
    keys = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'KEYS')
    result = {}
    apply = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'apply')
    for n in apply.body:
        if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Name) and n.value.func.id == '_replace_once'):
            call = n.value
            result[ast.literal_eval(call.args[3])] = (
                ast.literal_eval(call.args[1]), ast.literal_eval(call.args[2]))
    return ast.literal_eval(keys), result


class PortTests(unittest.TestCase):
    def test_exact_parent_and_determinism(self):
        self.assertEqual(port.git_blob(PARENT), 'fb766feaba84f10edbc1766f7c3404e6e00347a5')
        self.assertEqual(port.transform(PARENT), port.transform(PARENT))
        compile(port.transform(PARENT), '<candidate>', 'exec')

    def test_keys_and_existing_patch_operands_preserved(self):
        oldkeys, old = recipe(PARENT)
        newkeys, new = recipe(port.transform(PARENT))
        self.assertEqual(newkeys, oldkeys + (port.KEY,))
        changed = {'R04 V4 flags', 'R04 V4 install parameters', 'R04 V4 globals',
                   'R04 V4 install setters', 'Features V4 fields',
                   'TitanAgent V4 install arguments', 'TitanAgent V4 diagnostics'}
        self.assertEqual(set(new) - set(old), {'R04 V4 fast tape clone seam'})
        for label in old:
            self.assertEqual(new[label][0], old[label][0])
            if label not in changed:
                self.assertEqual(new[label][1], old[label][1])
        # No new outer admission: Policy.act is inside the existing core path.
        self.assertEqual(new['R04 V4 outer-wrapper dispatch'], old['R04 V4 outer-wrapper dispatch'])

    def test_default_off_and_install_abi_append(self):
        _, old = recipe(PARENT); _, new = recipe(port.transform(PARENT))
        self.assertIn('FAST_TAPE_CLONE = False\n', new['R04 V4 flags'][1])
        self.assertIn('r04_fast_tape_clone: bool = False', new['Features V4 fields'][1])
        prefix = 'def install(host=None, horizon=None,\n'
        before = ast.parse(prefix + old['R04 V4 install parameters'][1] + '    pass\n').body[0].args
        after = ast.parse(prefix + new['R04 V4 install parameters'][1] + '    pass\n').body[0].args
        self.assertEqual([a.arg for a in after.args[:-1]], [a.arg for a in before.args])
        self.assertEqual(after.args[-1].arg, 'fast_tape_clone')
        self.assertEqual([ast.dump(x) for x in after.defaults[:-1]], [ast.dump(x) for x in before.defaults])
        self.assertIsNone(ast.literal_eval(after.defaults[-1]))
        self.assertIn('if fast_tape_clone is not None:\n        FAST_TAPE_CLONE = bool(fast_tape_clone)',
                      new['R04 V4 install setters'][1])

    def test_exact_archived_policy_off_projection(self):
        data = (HERE / 'predecessor-package' / 'r04_full_router.py').read_bytes()
        self.assertEqual(port.git_blob(data), '21c4f1db0298f8955b1f5ad366bd780a89cad206')
        source = data.decode()
        policy = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'Policy')
        original = ast.get_source_segment(source, policy)
        self.assertEqual(original.count(port.OLD_CLONE), 1)
        candidate = original.replace(port.OLD_CLONE, port.NEW_CLONE)
        class ProjectOff(ast.NodeTransformer):
            def visit_If(self, node):
                if isinstance(node.test, ast.Name) and node.test.id == port.FLAG:
                    return node.orelse
                return self.generic_visit(node)
        self.assertEqual(ast.dump(ast.parse(original)), ast.dump(ProjectOff().visit(ast.parse(candidate))))

    def test_executed_off_never_calls_or_imports_helper(self):
        block = '\n'.join(line[4:] for line in port.NEW_CLONE.splitlines())
        namespace = {'FAST_TAPE_CLONE': False, 'copy': copy}
        exec(compile('def probe(tape, step):\n' + block + '\n    return action\n', '<seam>', 'exec'), namespace)
        action = {'farmer': ['PASS'], 'hands': [], 'market': []}
        with mock.patch.dict(sys.modules, {'r04_fast_tape_clone': None}):
            self.assertEqual(namespace['probe']([action], 0), action)

    def test_executed_on_all_tape_actions(self):
        block = '\n'.join(line[4:] for line in port.NEW_CLONE.splitlines())
        namespace = {'FAST_TAPE_CLONE': True, 'copy': copy}
        exec(compile('def probe(tape, step):\n' + block + '\n    return action\n', '<seam>', 'exec'), namespace)
        tapes = json.loads((HERE / 'tapes.json').read_text())
        count = 0
        with mock.patch.object(helper, 'apply_fast_tape_clone', wraps=helper.apply_fast_tape_clone) as called:
            for tape in tapes:
                for step, action in enumerate(tape):
                    self.assertEqual(namespace['probe'](tape, step), copy.deepcopy(action))
                    count += 1
            self.assertEqual(called.call_count, 9347)
        self.assertEqual(count, 9347)

    def test_duplicate_application_rejected(self):
        with self.assertRaises(ValueError):
            port.transform(port.transform(PARENT))

    def test_missing_label_rejected(self):
        with self.assertRaises(ValueError):
            port.transform(PARENT.replace(b'Features V4 fields', b'Renamed fields'))

    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ValueError):
            port.transform(PARENT.replace(b'"r04_place_delivery",', b'"r04_place_delivery", "r04_place_delivery",', 1))

    def test_dynamic_patch_operand_rejected(self):
        with self.assertRaises(ValueError):
            port.transform(PARENT.replace(b'"R04 V4 flags",', b'compute_label(),', 1))

    def test_existing_peer_append_preserved(self):
        parent = PARENT.replace(b'"r04_place_delivery",', b'"r04_other_peer", "r04_place_delivery",', 1)
        parent = parent.replace(b'place_delivery=None, goose_pass_rescue=None, b10_public_supply_order=None):',
                                b'place_delivery=None, goose_pass_rescue=None, b10_public_supply_order=None, other_peer=None):')
        before, _ = recipe(parent); after, patches = recipe(port.transform(parent))
        self.assertEqual(after[:-1], before)
        self.assertIn('other_peer=None, fast_tape_clone=None):', patches['R04 V4 install parameters'][1])


if __name__ == '__main__':
    unittest.main(verbosity=2)

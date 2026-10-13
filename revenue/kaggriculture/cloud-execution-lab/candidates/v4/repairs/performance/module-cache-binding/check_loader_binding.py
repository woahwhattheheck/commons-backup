# SPDX-License-Identifier: Apache-2.0
"""Execute the exact supplied loader's alias/cancellation contract.

Requires an explicit runtime input. Only its top-level load function executes;
the controller, deadline adapter, game engine and gameplay features do not.
No assert statement is used, so optimized Python checks the same invariants.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import subprocess
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

import repair_loader_binding as repair

SOURCE = b''
VARIANT = 'repaired'
COUNTS = {'package_switches': 0, 'consumer_imports': 0}


def make_loader():
    source = repair.repair_source(SOURCE)[0] if VARIANT == 'repaired' else SOURCE
    tree = ast.parse(source.decode('utf-8'))
    node = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == 'load')
    env = {'Path': Path, 'importlib': importlib, '_MODULE_CACHE': {}}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<exact-load>', 'exec'), env)
    return env['load'], env['_MODULE_CACHE']


class LoaderBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.load, self.cache = make_loader()
        self.names = set()
        self.before = {}
        self.old_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        self.addCleanup(self.restore_modules)

    def restore_modules(self):
        sys.dont_write_bytecode = self.old_bytecode
        for name in self.names:
            if name in self.before:
                sys.modules[name] = self.before[name]
            else:
                sys.modules.pop(name, None)

    def name(self, suffix='sibling'):
        name = '_titan_v4_binding_test_' + suffix
        if name not in self.names and name in sys.modules:
            self.before[name] = sys.modules[name]
        self.names.add(name)
        return name

    def source(self, filename, content):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def pair(self):
        a = self.source('A/sibling.py', 'VALUE = "A"\n')
        b = self.source('B/sibling.py', 'VALUE = "B"\n')
        name = self.name()
        return name, a, b

    def test_miss_binds_returned_object(self):
        name, a, _ = self.pair()
        module = self.load(name, a, cache=True)
        self.assertIs(sys.modules[name], module)

    def test_hit_returns_identity_without_reexecution(self):
        name, a, _ = self.pair()
        first = self.load(name, a, cache=True)
        first.VALUE = 'identity-marker'
        self.assertIs(self.load(name, a, cache=True), first)
        self.assertEqual(first.VALUE, 'identity-marker')

    def test_a_b_a_hit_rebinds_name(self):
        name, a, b = self.pair()
        first = self.load(name, a, cache=True)
        self.load(name, b, cache=True)
        self.assertIs(self.load(name, a, cache=True), first)
        self.assertIs(sys.modules[name], first)

    def test_removed_alias_is_repaired(self):
        name, a, _ = self.pair()
        first = self.load(name, a, cache=True)
        del sys.modules[name]
        self.assertIs(self.load(name, a, cache=True), first)
        self.assertIs(sys.modules.get(name), first)

    def test_none_alias_is_repaired(self):
        name, a, _ = self.pair()
        first = self.load(name, a, cache=True)
        sys.modules[name] = None
        self.load(name, a, cache=True)
        self.assertIs(sys.modules[name], first)

    def test_external_rebinding_is_repaired(self):
        name, a, _ = self.pair()
        first = self.load(name, a, cache=True)
        sys.modules[name] = ModuleType(name)
        self.load(name, a, cache=True)
        self.assertIs(sys.modules[name], first)

    def test_next_real_import_uses_selected_package(self):
        name, a, b = self.pair()
        self.load(name, a, cache=True)
        self.load(name, b, cache=True)
        selected = self.load(name, a, cache=True)
        path = self.source('A/consumer.py', f'from {name} import VALUE\n')
        consumer = self.load(self.name('consumer'), path, cache=True)
        self.assertEqual(consumer.VALUE, selected.VALUE)

    def test_function_import_uses_selected_quote(self):
        name = self.name('quote')
        a = self.source('A/quote.py', 'def quote(): return 31\n')
        b = self.source('B/quote.py', 'def quote(): return 97\n')
        first = self.load(name, a, cache=True)
        self.load(name, b, cache=True)
        self.load(name, a, cache=True)
        c = self.source('C/consumer.py', f'from {name} import quote\n')
        consumer = self.load(self.name('quote_consumer'), c)
        self.assertIs(consumer.quote, first.quote)
        self.assertEqual(consumer.quote(), 31)

    def test_cross_cache_namespace_rebinding(self):
        # Two independently loaded runtimes still share Python's sys.modules.
        name, a, b = self.pair()
        first = self.load(name, a, cache=True)
        other, other_cache = make_loader()
        other(name, b, cache=True)
        self.load(name, a, cache=True)
        self.assertIs(sys.modules[name], first)
        self.assertEqual(len(other_cache), 1)

    def test_all_729_six_step_package_streams(self):
        name = self.name('streams')
        paths = [self.source(f'{i}/m.py', f'VALUE = {i}\n') for i in range(3)]
        modules = [self.load(name, path, cache=True) for path in paths]
        for stream in itertools.product(range(3), repeat=6):
            for selected in stream:
                with self.subTest(stream=stream, selected=selected):
                    module = self.load(name, paths[selected], cache=True)
                    self.assertIs(module, modules[selected])
                    self.assertIs(sys.modules[name], module)
                COUNTS['package_switches'] += 1

    def test_128_cold_consumers_after_alternating_hits(self):
        name, a, b = self.pair()
        paths = [a, b]
        for path in paths:
            self.load(name, path, cache=True)
        for i in range(128):
            selected = self.load(name, paths[i % 2], cache=True)
            p = self.source(f'consumer_{i}.py', f'from {name} import VALUE\n')
            consumer = self.load(self.name(f'consumer_{i}'), p)
            with self.subTest(i=i):
                self.assertEqual(consumer.VALUE, selected.VALUE)
            COUNTS['consumer_imports'] += 1

    def test_path_normalization_retains_identity(self):
        name, a, _ = self.pair()
        first = self.load(name, a, cache=True)
        alias = a.parent / '..' / 'A' / 'sibling.py'
        self.assertIs(self.load(name, alias, cache=True), first)
        self.assertEqual(len(self.cache), 1)

    def test_separate_names_do_not_share_module_objects(self):
        _, a, _ = self.pair()
        first = self.load(self.name('one'), a, cache=True)
        second = self.load(self.name('two'), a, cache=True)
        self.assertIsNot(first, second)
        self.assertEqual(len(self.cache), 2)

    def test_noncached_load_is_always_fresh(self):
        name, a, _ = self.pair()
        first = self.load(name, a)
        second = self.load(name, a)
        self.assertIsNot(first, second)
        self.assertIs(sys.modules[name], second)
        self.assertEqual(self.cache, {})

    def test_cached_identity_survives_noncached_reload(self):
        name, a, _ = self.pair()
        first = self.load(name, a, cache=True)
        newer = self.load(name, a, cache=False)
        self.assertIsNot(first, newer)
        self.load(name, a, cache=True)
        self.assertIs(sys.modules[name], first)

    def test_runtime_error_restores_prior_alias(self):
        name, a, _ = self.pair()
        old = self.load(name, a, cache=True)
        bad = self.source('bad.py', 'PARTIAL = 1\nraise RuntimeError("stop")\n')
        with self.assertRaises(RuntimeError):
            self.load(name, bad, cache=True)
        self.assertIs(sys.modules[name], old)
        self.assertNotIn((name, str(bad.resolve())), self.cache)

    def test_baseexception_restores_prior_alias(self):
        name, a, _ = self.pair()
        old = self.load(name, a, cache=True)
        bad = self.source('bad.py', 'PARTIAL = 1\nraise KeyboardInterrupt("cancel")\n')
        with self.assertRaises(KeyboardInterrupt):
            self.load(name, bad, cache=True)
        self.assertIs(sys.modules[name], old)
        self.assertEqual(len(self.cache), 1)

    def test_baseexception_without_prior_alias_cleans_registration(self):
        name = self.name('absent')
        sys.modules.pop(name, None)
        bad = self.source('bad.py', 'raise KeyboardInterrupt("cancel")\n')
        with self.assertRaises(KeyboardInterrupt):
            self.load(name, bad, cache=True)
        self.assertNotIn(name, sys.modules)
        self.assertEqual(self.cache, {})

    def test_partial_module_is_not_reused_on_retry(self):
        name = self.name('retry')
        bad = self.source('retry.py', 'PARTIAL = True\nraise RuntimeError("stop")\n')
        with self.assertRaises(RuntimeError):
            self.load(name, bad, cache=True)
        bad.write_text('VALUE = 12345\n')
        module = self.load(name, bad, cache=True)
        self.assertEqual(module.VALUE, 12345)
        self.assertFalse(hasattr(module, 'PARTIAL'))

    def test_failed_import_does_not_clobber_newer_alias(self):
        name = self.name('replaced_during_error')
        bad = self.source('bad.py', f'import sys, types\n'
                          f'sys.modules[{name!r}] = types.ModuleType("newer")\n'
                          'raise RuntimeError("stop")\n')
        with self.assertRaises(RuntimeError):
            self.load(name, bad, cache=True)
        self.assertEqual(sys.modules[name].__name__, 'newer')
        self.assertEqual(self.cache, {})

    def test_failed_dependency_never_enters_cache(self):
        name = self.name('missing_dependency')
        bad = self.source('bad.py', 'import _titan_v4_binding_nonexistent_dependency_67201\n')
        with self.assertRaises(ModuleNotFoundError):
            self.load(name, bad, cache=True)
        self.assertNotIn(name, sys.modules)
        self.assertEqual(self.cache, {})

    def test_cached_hit_does_not_run_loader_again(self):
        name, a, _ = self.pair()
        first = self.load(name, a, cache=True)
        with patch.object(importlib.util, 'spec_from_file_location', side_effect=RuntimeError('cold')):
            self.assertIs(self.load(name, a, cache=True), first)

    def test_cold_import_observes_own_registration(self):
        name = self.name('self_view')
        path = self.source('self_view.py', 'import sys\nSELF = sys.modules[__name__]\n')
        module = self.load(name, path, cache=True)
        self.assertIs(module.SELF, module)


class TransformerTests(unittest.TestCase):
    def test_exact_fixture_identity(self):
        _, _, source = repair.load_span(SOURCE.decode('utf-8'))
        self.assertIn(hashlib.sha256(source.encode()).hexdigest(),
                      (repair.ORIGINAL_SHA256, repair.REPAIRED_SHA256))

    def test_idempotent_and_reports_output_identity(self):
        result, report = repair.repair_source(SOURCE)
        twice, repeat = repair.repair_source(result)
        self.assertEqual(result, twice)
        self.assertFalse(repeat['changed'])
        self.assertEqual(report['output_git_blob'], repair.git_blob(result))

    def test_preserves_disjoint_peer_bytes(self):
        text = SOURCE.decode('utf-8')
        _, _, loader = repair.load_span(text)
        before = '# peer unicode: λ 🌾\nPEER_BEFORE = {"active": False}\n\n'
        after = '\nPEER_AFTER = b"keep exactly"\n'
        result, _ = repair.repair_source((before + loader + after).encode('utf-8'))
        new_start, new_end, _ = repair.load_span(result.decode())
        self.assertEqual(result.decode()[:new_start], before)
        self.assertEqual(result.decode()[new_end:], after)

    def test_loader_drift_is_rejected(self):
        changed = SOURCE.replace(b'key = (name,', b'key = (str(name),', 1)
        with self.assertRaisesRegex(ValueError, 'Loader source drift'):
            repair.repair_source(changed)

    def test_empty_source_is_rejected(self):
        with self.assertRaises(ValueError):
            repair.repair_source(b'')

    def test_duplicate_loader_is_rejected(self):
        _, _, loader = repair.load_span(SOURCE.decode())
        with self.assertRaises(ValueError):
            repair.repair_source((loader + '\n' + loader).encode())

    def test_syntax_error_is_rejected(self):
        with self.assertRaises(SyntaxError):
            repair.repair_source(b'def load(\n')

    def test_invalid_utf8_is_rejected(self):
        with self.assertRaises(UnicodeError):
            repair.repair_source(b'\xff')

    def test_decorated_loader_is_rejected(self):
        _, _, loader = repair.load_span(SOURCE.decode())
        with self.assertRaisesRegex(ValueError, 'Decorated'):
            repair.repair_source(('@identity\n' + loader).encode())

    def test_async_loader_is_rejected(self):
        with self.assertRaises(ValueError):
            repair.repair_source(b'async def load(name, path):\n    return None\n')

    def test_nonbyte_source_is_rejected(self):
        with self.assertRaises(TypeError):
            repair.repair_source('not bytes')


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'runtime.py'
        self.source.write_bytes(SOURCE)
        self.target = self.root / 'fixed.py'

    def run_cli(self, source=None, target=None):
        command = [sys.executable]
        if sys.flags.optimize:
            command.append('-O')
        command += [str(Path(repair.__file__).resolve()),
                    str(self.source if source is None else source),
                    '--output', str(self.target if target is None else target)]
        return subprocess.run(command, text=True, capture_output=True,
                              timeout=10, check=False)

    def test_cli_exact_output_and_unchanged_input(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), repair.repair_source(SOURCE)[0])
        self.assertEqual(self.source.read_bytes(), SOURCE)
        self.assertEqual(json.loads(result.stdout)['output_git_blob'],
                         repair.git_blob(self.target.read_bytes()))

    def test_cli_rejects_existing_output_without_overwrite(self):
        self.target.write_bytes(b'peer work: preserve me')
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.target.read_bytes(), b'peer work: preserve me')
        self.assertEqual(self.source.read_bytes(), SOURCE)

    def test_cli_rejects_in_place_output(self):
        result = self.run_cli(target=self.source)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.source.read_bytes(), SOURCE)

    def test_cli_rejects_drift_before_creating_output(self):
        drift = SOURCE.replace(b'key = (name,', b'key = (str(name),', 1)
        self.source.write_bytes(drift)
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.source.read_bytes(), drift)

    def test_cli_rejects_missing_source_without_output(self):
        result = self.run_cli(source=self.root / 'absent.py')
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.target.exists())

    def test_cli_rejects_target_symlink_without_changing_referent(self):
        peer = self.root / 'peer.py'
        peer.write_bytes(b'peer bytes')
        self.target.symlink_to(peer)
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(peer.read_bytes(), b'peer bytes')
        self.assertTrue(self.target.is_symlink())


def main():
    global SOURCE, VARIANT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', type=Path)
    parser.add_argument('--variant', choices=('before', 'repaired'), default='repaired')
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    SOURCE = args.runtime.read_bytes()
    VARIANT = args.variant
    # Input identity validation is unconditional, including --variant before.
    repair.repair_source(SOURCE)
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(LoaderBindingTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(TransformerTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(CommandLineTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {
        'schema': 'titan-v4-loader-binding-check/v1',
        'variant': VARIANT,
        'python': sys.version,
        'optimized': bool(sys.flags.optimize),
        'input_git_blob': repair.git_blob(SOURCE),
        'tests_run': result.testsRun,
        'failures_including_subtests': len(result.failures),
        'errors': len(result.errors),
        'skipped': len(result.skipped),
        'successful': result.wasSuccessful(),
        'cases': dict(COUNTS),
        'execution_scope': 'exact current load function with real local imports',
        'full_runtime': False,
        'full_games': 0,
    }
    if args.json:
        args.json.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())

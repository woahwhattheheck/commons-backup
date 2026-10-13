#!/usr/bin/env python3
"""Focused real-file loader regressions; no policy, engine, or game calls."""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

TARGET = Path(__file__).with_name('recorded_inputs.py')
ACTUAL_SOURCES: list[Path] = []


def import_target(path: Path):
    name = 'trace_loading_target'
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot import test target {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # Bind test target itself to source, independently of its load function.
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


class SourceLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = import_target(TARGET.resolve())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='trace-source-loader-')
        self.root = Path(self.temp.name)
        self.name = 'trace_loading_fixture'
        self.previous = sys.modules.pop(self.name, None)

    def tearDown(self):
        sys.modules.pop(self.name, None)
        if self.previous is not None:
            sys.modules[self.name] = self.previous
        self.temp.cleanup()

    def source(self, data: bytes | str, filename='fixture.py') -> Path:
        path = self.root / filename
        path.write_bytes(data.encode() if isinstance(data, str) else data)
        return path

    def stale(self) -> Path:
        path = self.source('value = "OLD"\n')
        stat = path.stat()
        py_compile.compile(str(path), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        path.write_text('value = "NEW"\n')
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        return path

    def test_timestamp_valid_stale_bytecode_is_not_executed(self):
        self.assertEqual(self.target.load(self.stale(), self.name).value, 'NEW')

    def test_load_does_not_create_bytecode_cache(self):
        path = self.source('value = 7\n')
        with patch.object(sys, 'dont_write_bytecode', False):
            self.assertEqual(self.target.load(path, self.name).value, 7)
        self.assertFalse(Path(importlib.util.cache_from_source(str(path))).exists())

    def test_receipted_digest_matches_executed_source(self):
        path = self.source('value = 8\n')
        module = self.target.load(path, self.name)
        self.assertEqual(getattr(module, '__trace_input_source_sha256__', None),
                         hashlib.sha256(path.read_bytes()).hexdigest())

    def test_self_rewrite_does_not_change_captured_digest(self):
        source = 'from pathlib import Path\nvalue = "before"\nPath(__file__).write_text("value = \'after\'\\n")\n'
        path = self.source(source)
        module = self.target.load(path, self.name)
        self.assertEqual(module.value, 'before')
        self.assertNotEqual(path.read_text(), source)
        self.assertEqual(getattr(module, '__trace_input_source_sha256__', None),
                         hashlib.sha256(source.encode()).hexdigest())

    def test_module_cannot_replace_captured_digest(self):
        source = '__trace_input_source_sha256__ = "not-the-source-digest"\n'
        module = self.target.load(self.source(source), self.name)
        self.assertEqual(getattr(module, '__trace_input_source_sha256__', None),
                         hashlib.sha256(source.encode()).hexdigest())

    def test_declared_source_encoding_is_preserved(self):
        source = b'# coding: latin-1\nvalue = "caf\xe9"\n'
        module = self.target.load(self.source(source), self.name)
        self.assertEqual(module.value, 'caf\u00e9')

    def test_standard_module_metadata_is_preserved(self):
        path = self.source('value = 1\n')
        module = self.target.load(path, self.name)
        self.assertEqual(module.__name__, self.name)
        self.assertEqual(module.__file__, str(path))
        self.assertEqual(module.__spec__.name, self.name)
        self.assertEqual(module.__package__, '')
        self.assertIs(sys.modules[self.name], module)

    def test_self_registration_supports_dataclasses(self):
        source = 'from __future__ import annotations\nfrom dataclasses import dataclass\n@dataclass\nclass Packet:\n    count: int = 3\n'
        module = self.target.load(self.source(source), self.name)
        self.assertTrue(dataclasses.is_dataclass(module.Packet))
        self.assertEqual(module.Packet().count, 3)

    def test_failed_new_module_does_not_remain_registered(self):
        path = self.source('value = 1\nraise RuntimeError("original failure")\n')
        with self.assertRaisesRegex(RuntimeError, 'original failure'):
            self.target.load(path, self.name)
        self.assertNotIn(self.name, sys.modules)

    def test_failed_import_restores_existing_module_and_cancellation(self):
        original = types.ModuleType(self.name)
        for exception in ('RuntimeError', 'SystemExit', 'KeyboardInterrupt'):
            with self.subTest(exception=exception):
                sys.modules[self.name] = original
                path = self.source(f'raise {exception}("original failure")\n')
                with self.assertRaisesRegex(getattr(__import__('builtins'), exception), 'original failure'):
                    self.target.load(path, self.name)
                self.assertIs(sys.modules.get(self.name), original)

    def test_failed_self_rebinding_restores_existing_module(self):
        original = types.ModuleType(self.name)
        sys.modules[self.name] = original
        path = self.source('import sys\nsys.modules[__name__] = None\nraise RuntimeError("failed")\n')
        with self.assertRaisesRegex(RuntimeError, 'failed'):
            self.target.load(path, self.name)
        self.assertIs(sys.modules.get(self.name), original)

    def test_success_replaces_existing_module(self):
        original = types.ModuleType(self.name)
        sys.modules[self.name] = original
        module = self.target.load(self.source('value = 3\n'), self.name)
        self.assertIsNot(module, original)
        self.assertIs(sys.modules[self.name], module)

    def test_syntax_error_preserves_existing_binding(self):
        original = types.ModuleType(self.name)
        sys.modules[self.name] = original
        with self.assertRaises(SyntaxError):
            self.target.load(self.source('not valid python !!!\n'), self.name)
        self.assertIs(sys.modules.get(self.name), original)

    def test_missing_source_preserves_existing_binding(self):
        original = types.ModuleType(self.name)
        sys.modules[self.name] = original
        with self.assertRaises(FileNotFoundError):
            self.target.load(self.root / 'missing.py', self.name)
        self.assertIs(sys.modules.get(self.name), original)

    def test_unsupported_extension_preserves_existing_binding(self):
        original = types.ModuleType(self.name)
        sys.modules[self.name] = original
        with self.assertRaisesRegex(ValueError, 'Cannot load'):
            self.target.load(self.source('value = 2\n', 'fixture.txt'), self.name)
        self.assertIs(sys.modules.get(self.name), original)

    def test_next_load_consumes_changed_source_without_old_bytecode(self):
        path = self.stale()
        module = self.target.load(path, self.name)
        self.assertEqual(module.value, 'NEW')
        stat = path.stat()
        path.write_text('value = "END"\n')
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(self.target.load(path, self.name).value, 'END')

    def test_cli_receipt_uses_loaded_bytes_not_later_file_contents(self):
        evaluator_source = ('from pathlib import Path\nENGINE_REF = "test-fixture"\n'
                            'def get_engine(directory, loader): return object(), {}\n'
                            'Path(__file__).write_text("# later bytes\\n")\n')
        tracer_source = 'from pathlib import Path\nPath(__file__).write_text("# replaced tracer\\n")\n'
        evaluator = self.source(evaluator_source, 'evaluator.py')
        tracer = self.source(tracer_source, 'tracer.py')
        record = self.source('{}\n', 'record.json')
        output, receipt = self.root / 'inputs.jsonl', self.root / 'receipt.json'
        args = ['--record', str(record), '--engine-dir', str(self.root),
                '--evaluator', str(evaluator), '--tracer', str(tracer),
                '--loader', str(self.root / 'unused-loader.py'),
                '--output', str(output), '--receipt', str(receipt)]
        with patch.object(self.target, 'recover_record', return_value=([], {'fixture_only': True})):
            self.assertEqual(self.target.main(args), 0)
        value = json.loads(receipt.read_text())
        self.assertEqual(value['evaluator_sha256'], hashlib.sha256(evaluator_source.encode()).hexdigest())
        self.assertEqual(value['tracer_sha256'], hashlib.sha256(tracer_source.encode()).hexdigest())
        self.assertEqual(output.read_bytes(), b'')
        for name in ('trace_inputs_evaluator', 'trace_inputs_tracer'):
            sys.modules.pop(name, None)

    def test_actual_evaluator_and_tracer_imports(self):
        paths = ACTUAL_SOURCES
        if not paths:
            parent = TARGET.resolve().parent.parent
            paths = [parent / 'cloud-eval/evaluate.py', parent / 'cloud-widefield-lab/trace_apex_loss.py']
        if not all(path.is_file() for path in paths):
            self.skipTest('Supply --actual-source for both existing dependencies')
        for index, path in enumerate(paths):
            name = f'trace_actual_dependency_{index}'
            with self.subTest(path=str(path)):
                try:
                    module = self.target.load(path, name)
                    self.assertTrue(callable(getattr(module, 'get_engine', None)) or callable(getattr(module, 'play', None)))
                    self.assertEqual(getattr(module, '__trace_input_source_sha256__', None),
                                     hashlib.sha256(path.read_bytes()).hexdigest())
                finally:
                    sys.modules.pop(name, None)


def main() -> int:
    global TARGET, ACTUAL_SOURCES
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, default=TARGET)
    parser.add_argument('--actual-source', type=Path, action='append', default=[])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    TARGET, ACTUAL_SOURCES = args.module, args.actual_source
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SourceLoadingTests))
    report = {'schema': 'titan.trace-source-loading-tests.v1', 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
              'success': result.wasSuccessful(), 'target_sha256': hashlib.sha256(TARGET.read_bytes()).hexdigest(),
              'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'actual_dependency_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in ACTUAL_SOURCES},
              'policy_calls': 0, 'engine_calls': 0, 'new_game_evaluations': 0,
              'scope': 'Real local-file imports and one synthetic CLI receipt fixture; dependencies imported but not executed as games'}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())

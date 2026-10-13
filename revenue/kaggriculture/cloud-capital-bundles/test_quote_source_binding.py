# SPDX-License-Identifier: Apache-2.0
"""Source-byte execution and module cleanup at the existing quotation loader."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import py_compile
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

import reached_quote_case as q


def blob(raw: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


class QuoteSourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.saved = {name: value for name, value in sys.modules.items()
                      if name.startswith('_reached_quote_')}
        self.addCleanup(self.restore)
        self.dependencies = {}
        self.settings = patch.object(q, 'DEPENDENCIES', self.dependencies)
        self.settings.start()
        self.addCleanup(self.settings.stop)

    def restore(self):
        for name in tuple(sys.modules):
            if name.startswith('_reached_quote_'):
                del sys.modules[name]
        sys.modules.update(self.saved)

    def add(self, key: str, source: bytes) -> Path:
        path = self.root / (key + '.py')
        path.write_bytes(source)
        self.dependencies[key] = (path.name, blob(source))
        return path

    def test_actual_timestamp_cache_executes_verified_bytes(self):
        old, new = b"VALUE = 'old'\n", b"VALUE = 'new'\n"
        path = self.add('one', new)
        stamp = 1788820000
        path.write_bytes(old)
        os.utime(path, (stamp, stamp))
        cached = py_compile.compile(str(path), doraise=True,
                                    invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        old_cache = Path(cached).read_bytes()
        path.write_bytes(new)
        os.utime(path, (stamp, stamp))
        result = q.load_dependencies(self.root)
        self.assertEqual(result.one.VALUE, 'new')
        self.assertEqual(result.pins[path.name]['git_blob'], blob(new))
        self.assertEqual(Path(cached).read_bytes(), old_cache)
        self.assertEqual(path.read_bytes(), new)

    def test_unchecked_hash_cache_cannot_replace_verified_source(self):
        path = self.add('one', b"VALUE = 'new'\n")
        current = path.read_bytes()
        path.write_bytes(b"VALUE = 'old'\n")
        cached = py_compile.compile(str(path), doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        path.write_bytes(current)
        result = q.load_dependencies(self.root)
        self.assertEqual(result.one.VALUE, 'new')
        self.assertTrue(Path(cached).exists())

    def test_file_changed_after_capture_does_not_change_execution(self):
        source = b"VALUE = 'captured'\n"
        path = self.add('one', source)
        original = q.importlib.util.spec_from_file_location
        def replace_before_execution(name, location):
            path.write_bytes(b"VALUE = 'replacement'\n")
            return original(name, location)
        with patch.object(q.importlib.util, 'spec_from_file_location',
                          side_effect=replace_before_execution):
            result = q.load_dependencies(self.root)
        self.assertEqual(result.one.VALUE, 'captured')
        self.assertEqual(result.pins[path.name]['sha256'], hashlib.sha256(source).hexdigest())
        self.assertEqual(path.read_bytes(), b"VALUE = 'replacement'\n")

    def test_import_time_file_replacement_keeps_captured_receipt(self):
        source = b"from pathlib import Path\nVALUE = 'captured'\nPath(__file__).write_text(\"VALUE = 'after'\\n\")\n"
        path = self.add('one', source)
        result = q.load_dependencies(self.root)
        self.assertEqual(result.one.VALUE, 'captured')
        self.assertEqual(result.pins[path.name]['git_blob'], blob(source))
        self.assertEqual(path.read_bytes(), b"VALUE = 'after'\n")

    def test_metadata_dataclass_and_self_import_work(self):
        path = self.add('one', b"import sys\nfrom dataclasses import dataclass\n@dataclass\nclass Record:\n    value: int\nSELF = sys.modules[__name__]\n")
        result = q.load_dependencies(self.root)
        self.assertEqual(result.one.__file__, str(path))
        self.assertEqual(result.one.__name__, '_reached_quote_one')
        self.assertEqual(result.one.__spec__.origin, str(path))
        self.assertIs(result.one.SELF, result.one)
        self.assertIs(sys.modules['_reached_quote_one'], result.one)
        self.assertEqual(result.one.Record(3).value, 3)

    def test_no_future_annotation_flags_leak_from_loader(self):
        self.add('one', b"def f(value: int) -> int:\n    return value\n")
        result = q.load_dependencies(self.root)
        self.assertIs(result.one.f.__annotations__['value'], int)

    def test_source_encoding_cookie_is_preserved(self):
        self.add('one', b"# coding: latin-1\nVALUE = 'caf\xe9'\n")
        self.assertEqual(q.load_dependencies(self.root).one.VALUE, 'caf\u00e9')

    def test_verified_source_read_once_and_no_new_bytecode(self):
        path = self.add('one', b'VALUE = 7\n')
        original = Path.read_bytes
        reads = []
        def read(target):
            if target == path:
                reads.append(target)
            return original(target)
        with patch.object(Path, 'read_bytes', read):
            result = q.load_dependencies(self.root)
        self.assertEqual(result.one.VALUE, 7)
        self.assertEqual(reads, [path])
        self.assertFalse(path.with_name('__pycache__').exists())

    def test_hash_mismatch_does_not_execute_source(self):
        marker = self.root / 'marker'
        path = self.add('one', b'VALUE = 7\n')
        path.write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
        with self.assertRaisesRegex(ValueError, 'different source'):
            q.load_dependencies(self.root)
        self.assertFalse(marker.exists())

    def test_runtime_failure_restores_prior_binding(self):
        prior = ModuleType('_reached_quote_one')
        sys.modules[prior.__name__] = prior
        self.add('one', b"VALUE = 'partial'\nraise RuntimeError('body error')\n")
        with self.assertRaisesRegex(RuntimeError, 'body error'):
            q.load_dependencies(self.root)
        self.assertIs(sys.modules[prior.__name__], prior)

    def test_failure_removes_previously_absent_binding(self):
        sys.modules.pop('_reached_quote_one', None)
        self.add('one', b"raise RuntimeError('body error')\n")
        with self.assertRaises(RuntimeError):
            q.load_dependencies(self.root)
        self.assertNotIn('_reached_quote_one', sys.modules)

    def test_cancellation_restores_prior_binding_and_identity(self):
        for kind in (KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__):
                prior = ModuleType('_reached_quote_one')
                sys.modules[prior.__name__] = prior
                self.add('one', f'raise {kind.__name__}("cancelled")\n'.encode())
                with self.assertRaisesRegex(kind, 'cancelled'):
                    q.load_dependencies(self.root)
                self.assertIs(sys.modules[prior.__name__], prior)

    def test_failure_restores_earlier_successful_aliases(self):
        prior = ModuleType('_reached_quote_one')
        sys.modules[prior.__name__] = prior
        sys.modules.pop('_reached_quote_two', None)
        self.add('one', b'VALUE = 1\n')
        self.add('two', b"raise RuntimeError('second')\n")
        with self.assertRaisesRegex(RuntimeError, 'second'):
            q.load_dependencies(self.root)
        self.assertIs(sys.modules[prior.__name__], prior)
        self.assertNotIn('_reached_quote_two', sys.modules)

    def test_later_hash_failure_rolls_back_only_owned_aliases(self):
        prior = ModuleType('_reached_quote_one')
        unrelated = ModuleType('quote_test_unrelated')
        with patch.dict(sys.modules, {'_reached_quote_one': prior, 'quote_test_unrelated': unrelated}):
            self.add('one', b'VALUE = 1\n')
            path = self.add('two', b'VALUE = 2\n')
            path.write_bytes(b'VALUE = 3\n')
            with self.assertRaises(ValueError):
                q.load_dependencies(self.root)
            self.assertIs(sys.modules['_reached_quote_one'], prior)
            self.assertIs(sys.modules['quote_test_unrelated'], unrelated)

    def test_syntax_failure_preserves_filename_and_old_alias(self):
        prior = ModuleType('_reached_quote_one')
        sys.modules[prior.__name__] = prior
        path = self.add('one', b'def invalid syntax\n')
        with self.assertRaises(SyntaxError) as caught:
            q.load_dependencies(self.root)
        self.assertEqual(caught.exception.filename, str(path))
        self.assertIs(sys.modules[prior.__name__], prior)

    def test_success_publishes_all_new_aliases_and_pins(self):
        a = self.add('one', b'VALUE = 1\n')
        b = self.add('two', b'VALUE = 2\n')
        result = q.load_dependencies(self.root)
        self.assertEqual(result.one.VALUE + result.two.VALUE, 3)
        self.assertIs(sys.modules['_reached_quote_one'], result.one)
        self.assertIs(sys.modules['_reached_quote_two'], result.two)
        self.assertEqual(set(result.pins), {a.name, b.name})

    def test_repeated_load_does_not_reuse_mutated_module(self):
        self.add('one', b'VALUES = [1]\n')
        first = q.load_dependencies(self.root)
        first.one.VALUES.append(2)
        second = q.load_dependencies(self.root)
        self.assertEqual(second.one.VALUES, [1])
        self.assertIsNot(first.one, second.one)

    def test_body_exception_keeps_same_object(self):
        holder = ModuleType('quote_test_exception')
        holder.error = RuntimeError('same object')
        with patch.dict(sys.modules, {'quote_test_exception': holder}):
            self.add('one', b'import quote_test_exception\nraise quote_test_exception.error\n')
            with self.assertRaises(RuntimeError) as caught:
                q.load_dependencies(self.root)
        self.assertIs(caught.exception, holder.error)


if __name__ == '__main__':
    unittest.main(verbosity=2)

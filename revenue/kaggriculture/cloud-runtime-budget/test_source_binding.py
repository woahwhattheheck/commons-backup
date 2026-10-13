# SPDX-License-Identifier: Apache-2.0
"""Real import/worker boundaries for saved-profile source identity; no games."""
import importlib.util
import json
import os
from pathlib import Path
import py_compile
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import profile_saved as p

TIMING = Path(os.environ.get('TITAN_TIMING_SOURCE', str(
    Path(__file__).resolve().parent.parent / 'cloud-combination-analysis/execution_timing.py')))
POLICY = "class Agent:\n    def act(self,obs,cfg): return {'value':'new'}\ndef make_agent(): return Agent()\n"


class SourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.target_dir = self.root / 'target'
        self.target_dir.mkdir()
        self.target = self.target_dir / 'main.py'
        self.target.write_text(POLICY)
        self.timing = self.root / 'timing.py'
        self.timing.write_bytes(TIMING.read_bytes())
        self.replay = self.root / 'work.json'
        self.replay.write_text(json.dumps({
            'schema': 'titan.profile.observations.v1', 'configuration': {},
            'records': [{'observation': {'step': k, 'player': 0, 'private': {},
                         'farms': [{}, {}], 'market': {}},
                         'expected_action': {'value': 'new'}} for k in range(3)]}))
        self.args = SimpleNamespace(entrypoint=self.target, factory='make_agent', method='act',
            timing_source=self.timing, replay=self.replay, seat=0, max_decisions=3,
            classification='constructed-source-binding', process_timeout=15., output=self.root/'report.json')
        self.names = []

    def tearDown(self):
        for name in self.names:
            sys.modules.pop(name, None)
        self.tmp.cleanup()

    def load(self):
        name = 'delta_source_binding_' + str(len(self.names))
        self.names.append(name)
        return p.load_module(self.target, name)

    def stale_cache(self, path, old, new, mode=py_compile.PycInvalidationMode.TIMESTAMP):
        self.assertEqual(len(old), len(new))
        path.write_bytes(old)
        stamp = path.stat()
        cached = Path(py_compile.compile(str(path), doraise=True, invalidation_mode=mode))
        original_cache = cached.read_bytes()
        path.write_bytes(new)
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        return cached, original_cache

    def report(self):
        code = p.supervise(self.args)
        return code, json.loads(self.args.output.read_text())

    def test_timestamp_valid_stale_bytecode_does_not_replace_source(self):
        new = b'value = "new"\n'
        cached, original = self.stale_cache(self.target, new.replace(b'new', b'old'), new)
        self.assertEqual(self.load().value, 'new')
        self.assertEqual(cached.read_bytes(), original)

    def test_unchecked_hash_bytecode_does_not_replace_source(self):
        new = b'value = "new"\n'
        cached, original = self.stale_cache(self.target, new.replace(b'new', b'old'), new,
            py_compile.PycInvalidationMode.UNCHECKED_HASH)
        self.assertEqual(self.load().value, 'new')
        self.assertEqual(cached.read_bytes(), original)

    def test_current_syntax_error_is_not_hidden_by_valid_cache(self):
        old = b'value = 111\n'
        new = b'value = )  \n'
        self.stale_cache(self.target, old, new)
        with self.assertRaises(SyntaxError) as caught:
            self.load()
        self.assertEqual(caught.exception.filename, str(self.target))

    def test_module_metadata_dataclass_and_per_load_state(self):
        self.target.write_text('from dataclasses import dataclass\n@dataclass\nclass Agent:\n    n: int = 0\n    def act(self):\n        self.n += 1\n        return self.n\n')
        a, b = self.load(), self.load()
        actor = a.Agent()
        self.assertEqual((actor.act(), actor.act(), b.Agent().act()), (1, 2, 1))
        self.assertIs(sys.modules[a.__name__], a)
        self.assertEqual(a.__file__, str(self.target))
        self.assertEqual(a.__spec__.origin, str(self.target))
        self.assertEqual(a.__package__, '')
        self.assertEqual(a.Agent.act.__code__.co_filename, str(self.target))

    def test_source_encoding_and_newline_variants(self):
        for raw in (b'# coding: latin-1\r\nvalue = "caf\xe9"\r\n',
                    b'\xef\xbb\xbfvalue = "caf\xc3\xa9"\n'):
            with self.subTest(raw=raw):
                self.target.write_bytes(raw)
                self.assertEqual(self.load().value, 'caf\u00e9')

    def test_profiler_future_flags_are_not_inherited(self):
        self.target.write_text('def f(value: int) -> int: return value\n')
        module = self.load()
        self.assertIs(module.f.__annotations__['value'], int)
        self.assertIs(module.f.__annotations__['return'], int)

    def test_import_exception_is_not_retried(self):
        count = self.root / 'attempts.txt'
        self.target.write_text('from pathlib import Path\np=Path(%r)\np.write_text(p.read_text()+"x" if p.exists() else "x")\nraise TypeError("source body")\n' % str(count))
        with self.assertRaisesRegex(TypeError, 'source body'):
            self.load()
        self.assertEqual(count.read_text(), 'x')

    def test_one_source_read_drives_execution_even_if_path_changes(self):
        old, new = b'value = "old"\n', b'value = "new"\n'
        self.target.write_bytes(old)
        original_read = Path.read_bytes
        reads = []
        def read(path):
            data = original_read(path)
            if path == self.target:
                reads.append(data)
                path.write_bytes(new)
            return data
        with patch.object(Path, 'read_bytes', read):
            module = self.load()
        self.assertEqual(reads, [old])
        self.assertEqual(module.value, 'old')
        self.assertEqual(self.target.read_bytes(), new)

    def test_direct_import_does_not_create_or_remove_cache(self):
        cache = Path(importlib.util.cache_from_source(str(self.target)))
        with patch.object(sys, 'dont_write_bytecode', False):
            self.load()
        self.assertFalse(cache.exists())

    def test_two_actual_workers_use_current_target_and_record_loaded_hashes(self):
        new = POLICY.encode()
        cached, original = self.stale_cache(self.target, new.replace(b'new', b'old'), new)
        code, result = self.report()
        self.assertEqual(code, 0)
        self.assertTrue(result['instrumentation_action_parity'])
        for mode in ('ordinary', 'instrumented'):
            report = result[mode]
            self.assertEqual(report['expected_actions']['mismatches'], 0)
            self.assertEqual(report.get('loaded_sources'), {
                'finch_existing_timing': {'path': str(self.timing), 'sha256': p.digest(self.timing.read_bytes())},
                'finch_profile_target': {'path': str(self.target), 'sha256': p.digest(new)}})
            self.assertTrue(report.get('loaded_sources_unchanged'))
            self.assertEqual(report['runtime_sources']['main.py'], p.digest(new))
            self.assertEqual(report['timings']['calls'], 3)
        self.assertEqual(cached.read_bytes(), original)

    def test_two_actual_workers_use_current_timing_source(self):
        current = TIMING.read_bytes()
        old = current.replace(b'result = self.policy(*args, **kwargs)',
                              b'result = {"stale": self.policy(*args, **kwargs)}')
        new = current + b'#' * (len(old) - len(current))
        cached, original = self.stale_cache(self.timing, old, new)
        code, result = self.report()
        self.assertEqual(code, 0)
        for mode in ('ordinary', 'instrumented'):
            self.assertEqual(result[mode]['expected_actions']['mismatches'], 0)
            self.assertEqual(result[mode]['timing_source_sha256'], p.digest(new))
        self.assertEqual(cached.read_bytes(), original)

    def test_timing_change_inside_call_cannot_pass_source_parity(self):
        self.target.write_text('from pathlib import Path\nclass Agent:\n    def act(self,obs,cfg):\n        p=Path(%r)\n        p.write_bytes(p.read_bytes()+b"\\n")\n        return {"value":"new"}\ndef make_agent(): return Agent()\n' % str(self.timing))
        code, result = self.report()
        self.assertEqual(code, 2)
        self.assertFalse(result['instrumentation_action_parity'])
        for mode in ('ordinary', 'instrumented'):
            self.assertEqual(result[mode]['status'], 'complete')
            self.assertTrue(result[mode]['sources_unchanged'])
            self.assertIs(result[mode].get('loaded_sources_unchanged'), False)

    def test_timing_change_between_passes_cannot_pass_source_parity(self):
        real_run = p.subprocess.run
        invocations = []
        def run(*args, **kwargs):
            completed = real_run(*args, **kwargs)
            invocations.append(completed.returncode)
            if len(invocations) == 1:
                self.timing.write_bytes(self.timing.read_bytes()+b'\n# between passes\n')
            return completed
        with patch.object(p.subprocess, 'run', run):
            code, result = self.report()
        self.assertEqual(invocations, [0, 0])
        self.assertEqual(code, 2)
        self.assertFalse(result['instrumentation_action_parity'])
        a, b = result['ordinary'], result['instrumented']
        self.assertEqual(a['action_sequence_sha256'], b['action_sequence_sha256'])
        self.assertTrue(a.get('loaded_sources_unchanged'))
        self.assertTrue(b.get('loaded_sources_unchanged'))
        self.assertNotEqual(a.get('loaded_sources'), b.get('loaded_sources'))

    def test_removed_timing_source_preserves_a_complete_failure_receipt(self):
        self.target.write_text('from pathlib import Path\nclass Agent:\n    def act(self,obs,cfg):\n        Path(%r).unlink(missing_ok=True)\n        return {"value":"new"}\ndef make_agent(): return Agent()\n' % str(self.timing))
        self.args.worker_mode = 'ordinary'
        self.assertEqual(p.worker(self.args), 0)
        result = json.loads(self.args.output.read_text())
        self.assertEqual(result['status'], 'complete')
        self.assertIs(result.get('loaded_sources_unchanged'), False)
        self.assertEqual(result['timings']['calls'], 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)

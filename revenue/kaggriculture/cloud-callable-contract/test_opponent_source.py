# SPDX-License-Identifier: Apache-2.0
"""Exercise actual opponent source loading on real files, without game execution.

Only the unrelated top-level game/overlay imports are isolated. The complete
resolver module and all its functions are executed unchanged from --resolver.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import py_compile
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

DEFAULT = Path(__file__).resolve().parents[1] / 'cloud-model-lab' / 'arlene_arm.py'
RESOLVER = DEFAULT


def read_resolver(path):
    module = types.ModuleType('_opponent_source_test')
    module.__file__ = str(path)
    unused = {name: types.ModuleType(name) for name in (
        'cards', 'native_motifs', 'arlene_motifs', 'arlene_plan', 'route_cards')}
    with patch.dict(sys.modules, unused):
        exec(compile(path.read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


class OpponentSource(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'opponent.py'
        self.resolver = read_resolver(RESOLVER)
        original_path = sys.path[:]
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), original_path))
        self.addCleanup(lambda: sys.modules.pop('_opponent_snapshot_dep', None))

    def write(self, source):
        raw = source.encode('utf-8') if isinstance(source, str) else source
        self.path.write_bytes(raw)
        return raw

    def opponent(self):
        return self.resolver.make_opponent('path:' + str(self.path), None)

    def identity(self, record, source):
        digest = hashlib.sha256(source).hexdigest()
        self.assertEqual(record, {'path': str(self.path.resolve()), 'sha256': digest,
                                 'label': 'opponent.py@' + digest[:12]})

    def test_stale_timestamp_bytecode_is_not_executed(self):
        old = self.write('def agent(obs, cfg): return "old"\n')
        stamp = 1700000000
        os.utime(self.path, (stamp, stamp))
        cache = Path(py_compile.compile(str(self.path), doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP))
        cached = cache.read_bytes()
        source = self.write('def agent(obs, cfg): return "new"\n')
        self.assertEqual(len(old), len(source))
        os.utime(self.path, (stamp, stamp))
        actor, record = self.opponent()
        self.identity(record, source)
        self.assertEqual(actor({}, {}), 'new')
        self.assertEqual(cache.read_bytes(), cached)

    def test_import_rewrite_keeps_executed_source_identity(self):
        replacement = 'def agent(obs, cfg): return "replacement"\n'
        source = self.write('from pathlib import Path\n'
            f'Path(__file__).write_text({replacement!r})\n'
            'def agent(obs, cfg): return "loaded-original"\n')
        actor, record = self.opponent()
        self.assertEqual(actor({}, {}), 'loaded-original')
        self.assertEqual(self.path.read_text(), replacement)
        self.identity(record, source)

    def test_import_removal_does_not_trigger_second_source_read(self):
        source = self.write('from pathlib import Path\nPath(__file__).unlink()\n'
                            'def agent(obs): return "executed"\n')
        actor, record = self.opponent()
        self.assertFalse(self.path.exists())
        self.assertEqual(actor({}, {}), 'executed')
        self.identity(record, source)

    def test_new_load_binds_current_revision_without_changing_old_actor(self):
        first_source = self.write('def agent(obs, cfg): return "first"\n')
        first, first_id = self.opponent()
        second_source = self.write('def agent(obs, cfg): return "second-revision"\n')
        second, second_id = self.opponent()
        self.assertEqual([first({}, {}), second({}, {})], ['first', 'second-revision'])
        self.identity(first_id, first_source)
        self.identity(second_id, second_source)

    def test_fresh_opponents_retain_independent_singleton_state(self):
        self.write('count = 0\ndef agent(obs, cfg=None):\n global count\n count += 1\n return count\n')
        first, _ = self.opponent()
        second, _ = self.opponent()
        self.assertEqual([first({}, {}), first({}, {}), second({}, {})], [1, 2, 1])

    def test_named_registry_and_path_form_keep_same_contract(self):
        source = self.write('def agent(obs, cfg): return obs, cfg\n')
        self.resolver.OPPONENTS['fixture'] = str(self.path)
        actor, record = self.resolver.make_opponent('fixture', None)
        obs, cfg = {}, {}
        actual = actor(obs, cfg)
        self.assertIs(actual[0], obs)
        self.assertIs(actual[1], cfg)
        self.identity(record, source)
        other, other_id = self.opponent()
        self.assertEqual(other_id, record)
        self.assertEqual(other(obs, cfg), (obs, cfg))

    def test_arlene_special_case_does_not_load_files(self):
        class Agent:
            def act(self, observation):
                return observation
        with patch.object(self.resolver, '_load', side_effect=AssertionError('not called')):
            actor, record = self.resolver.make_opponent('arlene', types.SimpleNamespace(Agent=Agent))
            obs = {}
            self.assertIs(actor(obs, {}), obs)
        self.assertEqual(record, {'label': 'arlene (vendored)'})

    def test_unknown_registry_name_still_raises(self):
        with self.assertRaisesRegex(KeyError, 'unknown opponent'):
            self.resolver.make_opponent('not-a-source', None)

    def test_body_typeerror_is_not_retried(self):
        self.write('def agent(obs, cfg=None):\n obs.append(cfg)\n raise TypeError("body-sentinel")\n')
        actor, _ = self.opponent()
        obs, cfg = [], {'value': 9}
        with self.assertRaisesRegex(TypeError, '^body-sentinel$'):
            actor(obs, cfg)
        self.assertEqual(obs, [cfg])

    def test_import_error_propagates_after_one_execution(self):
        marker = self.root / 'executed.txt'
        self.write('from pathlib import Path\n'
            f'p = Path({str(marker)!r})\n'
            'p.write_text((p.read_text() if p.exists() else "") + "once")\n'
            'raise TypeError("import-sentinel")\n')
        with self.assertRaisesRegex(TypeError, '^import-sentinel$'):
            self.opponent()
        self.assertEqual(marker.read_text(), 'once')

    def test_source_encodings_and_raw_identity(self):
        for source, expected in [
            (b'# coding: latin-1\r\ndef agent(obs): return "caf\xe9"\r\n', 'caf\u00e9'),
            (b'\xef\xbb\xbfdef agent(obs): return "BOM"\r\n', 'BOM')]:
            with self.subTest(source=source[:15]):
                self.write(source)
                actor, record = self.opponent()
                self.identity(record, source)
                self.assertEqual(actor({}, {}), expected)

    def test_module_metadata_and_trace_filename_remain_path_based(self):
        self.write('def agent(obs):\n return __file__, __spec__.origin, __name__, '
                   '__package__, type(__loader__).__name__, agent.__code__.co_filename\n')
        module, record = self.resolver._load(self.path, 'unchanged-unused-parameter')
        self.assertEqual(module.agent({}), (str(self.path), str(self.path), 'opponent_arm',
                                           '', 'SourceFileLoader', str(self.path)))
        self.assertEqual(record['path'], str(self.path))

    def test_original_one_and_two_argument_shapes(self):
        for source, expected in [
            ('def agent(obs): return obs["x"]\n', 3),
            ('def agent(obs, cfg=None): return cfg["y"]\n', 5),
            ('def agent(*args): return len(args)\n', 2)]:
            with self.subTest(source=source):
                self.write(source)
                actor, _ = self.opponent()
                self.assertEqual(actor({'x': 3}, {'y': 5}), expected)

    def test_missing_and_invalid_sources_are_not_accepted(self):
        with self.assertRaises(FileNotFoundError):
            self.opponent()
        self.write('def agent( !!!\n')
        with self.assertRaises(SyntaxError):
            self.opponent()

    def test_symlink_metadata_names_resolved_source(self):
        source = self.write('def agent(obs): return 23\n')
        alias = self.root / 'alias.py'
        alias.symlink_to(self.path)
        module, record = self.resolver._load(alias)
        self.assertEqual(module.agent({}), 23)
        self.identity(record, source)

    def test_transitive_imports_keep_normal_python_behavior(self):
        dependency = self.root / '_opponent_snapshot_dep.py'
        dependency.write_text('VALUE = 17\n')
        sys.path.insert(0, str(self.root))
        self.write('from _opponent_snapshot_dep import VALUE\ndef agent(obs): return VALUE\n')
        first, _ = self.opponent()
        dependency.write_text('VALUE = 12345\n')
        second, _ = self.opponent()
        self.assertEqual([first({}, {}), second({}, {})], [17, 17])


def main():
    global RESOLVER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resolver', type=Path, default=DEFAULT)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    RESOLVER = args.resolver.resolve()
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(OpponentSource))
    print(log.getvalue(), end='')
    if args.report:
        payload = {'scope': 'shared_opponent_source_binding_not_games',
            'python': platform.python_version(), 'methods': result.testsRun,
            'failures': len(result.failures), 'errors': len(result.errors),
            'skipped': len(result.skipped), 'successful': result.wasSuccessful(),
            'resolver_sha256': hashlib.sha256(RESOLVER.read_bytes()).hexdigest(),
            'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'games': 0, 'game_seeds': [], 'log': log.getvalue()}
        args.report.write_text(json.dumps(payload, indent=2) + '\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())

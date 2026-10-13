"""Additional diagnostic persistence cases against the single existing executor.

Actual CLI/writer functions and filesystem; synthetic game rows only. No engine
or policy calls. TITAN_EXECUTOR_SOURCE selects an exact comparison revision.
"""
import argparse
import ast
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SOURCE = Path(os.environ.get('TITAN_EXECUTOR_SOURCE', str(
    Path(__file__).resolve().parents[1] / 'cloud-model-lab' / 'execute_arm.py')))


def load_functions():
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef)
            and node.name in {'main', 'write_checkpoint', 'wtl'}]
    ns = dict(argparse=argparse, json=json, os=os, tempfile=tempfile)
    exec(compile(ast.Module(body=body, type_ignores=[]), str(SOURCE), 'exec'), ns)
    return ns


def row(seed, seat, opponent, factory, label, record_path=True):
    result = dict(seed=seed, seat=seat, opponent=opponent, arm=label,
                  own_cash=12, rival_cash=10, margin=2, error=None,
                  worst_action_s=0.01, executor_timing={'fixture': 'unchanged'})
    if record_path:
        result['path'] = [{'fixture_day': 1}]
    return result


def invoke(ns, output, game=row, seeds=('101',), record_path=True):
    ns['game'] = game
    ns['load_callable'] = lambda p, roots: (object(), dict(path=p, label=p, sha256=p))
    argv = ['execute_arm.py', '--candidate', 'c', '--control', 'b', '--seeds',
            *seeds, '--seats', '0', '--opponents', 'arlene', '--out', str(output)]
    if not record_path:
        argv.append('--no-path')
    module = types.ModuleType('market_path')
    module.diff = lambda *args: ['one synthetic difference']
    with patch.object(sys, 'argv', argv), patch.dict(sys.modules, market_path=module), \
            redirect_stdout(io.StringIO()):
        ns['main']()


class DiagnosticCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name) / 'results.json'
        self.ns = load_functions()

    def read(self):
        return json.loads(self.output.read_text(encoding='utf-8'))

    def assert_annotation(self):
        data = self.read()
        self.assertEqual(len(data['rows']), 2)
        self.assertEqual(data['rows'][1].get('path_divergent_days'), 1)
        self.assertFalse(data['checkpoint']['complete'])

    def test_annotation_survives_interruption_inside_next_game(self):
        def fixture(*args):
            if args[0] == 102:
                raise SystemExit(9)
            return row(*args)
        with self.assertRaises(SystemExit):
            invoke(self.ns, self.output, fixture, seeds=('101', '102'))
        self.assert_annotation()

    def test_annotation_survives_console_failure_after_diagnostic(self):
        def emit(*args, **kwargs):
            if args and str(args[0]).startswith('seed '):
                raise BrokenPipeError('synthetic closed output')
        self.ns['print'] = emit
        with self.assertRaises(BrokenPipeError):
            invoke(self.ns, self.output)
        self.assert_annotation()

    def test_real_hard_exit_in_next_game_retains_annotation(self):
        script = '''import runpy,sys,os
m=runpy.run_path(sys.argv[1])
ns=m['load_functions']()
def fixture(*args):
    if args[0]==102: os._exit(23)
    return m['row'](*args)
m['invoke'](ns,sys.argv[2],fixture,seeds=('101','102'))
'''
        result = subprocess.run([sys.executable, '-B', '-c', script,
                                 str(Path(__file__).resolve()), str(self.output)],
                                capture_output=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 23, result.stderr.decode(errors='replace'))
        self.assert_annotation()

    def test_failed_annotation_write_stops_before_next_game_and_keeps_rows(self):
        calls = []
        real_replace = os.replace
        def fixture(*args):
            calls.append((args[0], args[4]))
            return row(*args)
        def replace(src, dst):
            data = json.loads(Path(src).read_text(encoding='utf-8'))
            if any('path_divergent_days' in r for r in data['rows']):
                raise OSError('synthetic annotation write failure')
            return real_replace(src, dst)
        with patch.object(os, 'replace', side_effect=replace), self.assertRaises(OSError):
            invoke(self.ns, self.output, fixture, seeds=('101', '102'))
        self.assertEqual(calls, [(101, 'control'), (101, 'candidate')])
        data = self.read()
        self.assertEqual(len(data['rows']), 2)
        self.assertNotIn('path_divergent_days', data['rows'][1])
        self.assertFalse(data['checkpoint']['complete'])
        self.assertEqual(list(self.output.parent.glob('.execute-arm-*.json.tmp')), [])

    def test_no_path_keeps_original_three_writes(self):
        real_replace = os.replace
        with patch.object(os, 'replace', wraps=real_replace) as replace:
            invoke(self.ns, self.output, record_path=False)
        self.assertEqual(replace.call_count, 3)
        self.assertTrue(self.read()['checkpoint']['complete'])
        self.assertTrue(all('path_divergent_days' not in r for r in self.read()['rows']))

    def test_complete_pair_preserves_canonical_schema_and_diagnostic(self):
        invoke(self.ns, self.output)
        data = self.read()
        self.assertEqual(data['checkpoint'], dict(complete=True, recorded_rows=2,
                                                  expected_rows=2, failed_rows=0))
        self.assertEqual(data['rows'][1]['path_divergent_days'], 1)
        self.assertEqual(data['rows'][1]['executor_timing'], {'fixture': 'unchanged'})
        self.assertNotIn('progress', data)


if __name__ == '__main__':
    unittest.main(verbosity=2)

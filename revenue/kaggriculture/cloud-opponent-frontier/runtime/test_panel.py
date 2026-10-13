"""Regression coverage for the production T07 runner; full games are separate."""
import gzip
import json
from pathlib import Path
import tempfile
import types
import unittest
import panel


def game(arm, scores, *, seed=1, seat=0, opponent='arlene', status='complete'):
    return dict(arm=arm, seed=seed, candidate_seat=seat, opponent=opponent,
                scores=scores, status=status, actors=[])


class PanelTests(unittest.TestCase):
    def test_paired_win_and_relative_cash(self):
        data = panel.summarize([game('baseline', [10, 20]), game('candidate', [30, 25])])
        self.assertEqual(data['flips'], {'L->W': 1})
        self.assertEqual(data['paired'][0]['cash_delta'], 20)
        self.assertEqual(data['paired'][0]['margin_delta'], 15)

    def test_second_seat_is_not_reversed(self):
        data = panel.summarize([game('baseline', [10, 10], seat=1),
                                game('candidate', [10, 5], seat=1)])
        self.assertEqual(data['flips'], {'T->L': 1})
        self.assertEqual(data['paired'][0]['cash_delta'], -5)

    def test_failures_are_not_cash_losses(self):
        data = panel.summarize([game('baseline', [10, 20]),
                                game('candidate', None, status='failed')])
        self.assertEqual(data['flips'], {'L->FAILED': 1})
        self.assertIsNone(data['paired'][0]['cash_delta'])
        self.assertEqual(data['counts']['candidate/arlene'], {'FAILED': 1})

    def test_duplicate_rows_are_rejected(self):
        row = game('baseline', [10, 20])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            panel.summarize([row, row])

    def test_missing_baseline_is_not_paired(self):
        self.assertEqual(panel.summarize([game('candidate', [10, 20])])['paired'], [])

    def test_pairing_never_crosses_opponents_or_seeds(self):
        rows = [game('baseline', [10, 10]), game('candidate', [20, 10], opponent='apex'),
                game('candidate', [20, 10], seed=2)]
        self.assertEqual(panel.summarize(rows)['paired'], [])

    def test_dependency_hash_includes_nonentry_and_native_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'main.py').write_text('def agent(obs): return {}\n')
            (root / 'agent.so').write_bytes(b'native-fixture')
            before = panel.source_tree(root)
            (root / 'agent.so').write_bytes(b'changed-native-fixture')
            after = panel.source_tree(root)
            self.assertEqual(before['main.py'], after['main.py'])
            self.assertNotEqual(before['agent.so'], after['agent.so'])

    def test_cache_is_not_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '__pycache__').mkdir()
            (root / '__pycache__/x.pyc').write_bytes(b'cache')
            self.assertEqual(panel.source_tree(root), {})

    def test_json_write_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'nested/report.json'
            panel.write_json(path, {'x': [1, 2]})
            self.assertEqual(json.loads(path.read_text()), {'x': [1, 2]})
            self.assertFalse(path.with_suffix('.json.tmp').exists())

    def test_trace_is_passive_and_restores_interpreter(self):
        def interpreter(state, env):
            state[0]['cash'] += 5
            return state
        engine = types.SimpleNamespace(interpreter=interpreter)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'trace.gz'
            state = [{'cash': 10}]
            with panel.trace_game(engine, path):
                self.assertIs(engine.interpreter(state, {}), state)
            self.assertIs(engine.interpreter, interpreter)
            with gzip.open(path, 'rt') as stream:
                row = json.loads(stream.readline())
            self.assertEqual(row, {'before': [{'cash': 10}], 'after': [{'cash': 15}]})

    def test_trace_restored_on_error(self):
        interpreter = lambda state, env: state
        engine = types.SimpleNamespace(interpreter=interpreter)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, 'interrupt'):
                with panel.trace_game(engine, Path(tmp) / 'trace.gz'):
                    raise RuntimeError('interrupt')
            self.assertIs(engine.interpreter, interpreter)


if __name__ == '__main__':
    unittest.main()

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import replay_mechanisms as replay


def fixture():
    def identity(obs, action, step):
        return action
    module = types.SimpleNamespace(**{name: identity for name in replay.HOOKS})
    module.agent = lambda obs: {'farmer': ['PASS'], 'hands': [], 'market': []}
    return module


def row(seat=0, action=None):
    obs = {'player': seat, 'step': 0, 'private': {}, 'farms': [{'hands': []}, {'hands': []}]}
    state = {'observation': obs, 'action': action or {'farmer': ['PASS'], 'hands': [], 'market': []}}
    return {'before': [copy.deepcopy(state), copy.deepcopy(state)]}


class ReplayTests(unittest.TestCase):
    def test_exact_parity(self):
        result = replay.replay_rows(fixture(), [row()], 0)
        self.assertTrue(result['all_actions_match'])
        self.assertEqual(result['unit_action_requests'], {'PASS': 1})

    def test_mismatch_is_not_parity(self):
        result = replay.replay_rows(fixture(), [row(action={'farmer': ['NORTH']})], 0)
        self.assertFalse(result['all_actions_match'])
        self.assertEqual(len(result['mismatches']), 1)

    def test_initialization_is_not_an_agent_call(self):
        initial = {'before': [{'observation': {}}, {'observation': {}}]}
        result = replay.replay_rows(fixture(), [initial, row()], 0)
        self.assertEqual(result['observations'], 1)

    def test_empty_cannot_prove_parity(self):
        with self.assertRaisesRegex(ValueError, 'No observed'):
            replay.replay_rows(fixture(), [], 0)

    def test_wrong_seat_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'wrong-seat'):
            replay.replay_rows(fixture(), [row(1)], 0)

    def test_mutation_is_observed_without_changing_return(self):
        module = fixture()
        def mutate(obs, action, step):
            action['farmer'] = ['NORTH']
            return action
        module._preempt_shift = mutate
        with replay.observe_hooks(module) as records:
            action = {'farmer': ['PASS']}
            self.assertIs(module._preempt_shift({'step': 3}, action, 3), action)
        changed = records['_preempt_shift']['changed'][0]
        self.assertEqual(changed['before'], {'farmer': ['PASS']})
        self.assertEqual(changed['after'], {'farmer': ['NORTH']})
        self.assertIs(module._preempt_shift, mutate)

    def test_errors_are_counted_and_hooks_restored(self):
        module = fixture()
        def fail(*args):
            raise ValueError('fixture')
        module._preempt_shift = fail
        with self.assertRaises(ValueError):
            with replay.observe_hooks(module) as records:
                module._preempt_shift({'step': 3}, {}, 3)
        self.assertEqual(records['_preempt_shift']['errors'], [{'step': 3, 'type': 'ValueError'}])
        self.assertIs(module._preempt_shift, fail)


class ReplayCliTests(unittest.TestCase):
    def test_cli_requires_valid_player_index(self):
        base = ['replay', '--policy', 'unused', '--trace', 'unused', '--output', 'unused']
        for selection in ([], ['--seat', '2'], ['--seat', '-1'], ['--seat', 'invalid']):
            with self.subTest(selection=selection), patch.object(sys, 'argv', base + selection):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    replay.main()
                self.assertEqual(error.exception.code, 2)

    def test_cli_replays_both_explicit_player_positions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy, trace = root / 'policy.py', root / 'trace.gz'
            policy.touch()
            trace.touch()
            for seat in (0, 1):
                output = root / f'report-{seat}.json'
                report = {'observations': 1, 'exact_action_matches': 1,
                          'all_actions_match': True,
                          'hooks': {name: {'changed': []} for name in replay.HOOKS}}
                argv = ['replay', '--policy', str(policy), '--trace', str(trace),
                        '--seat', str(seat), '--output', str(output)]
                with self.subTest(seat=seat), patch.object(sys, 'argv', argv):
                    with patch.object(replay, 'replay_trace', return_value=report) as run:
                        with redirect_stdout(io.StringIO()):
                            replay.main()
                    run.assert_called_once_with(policy.resolve(), trace.resolve(), seat)
                    self.assertEqual(json.loads(output.read_text()), report)

    def test_cli_help_describes_game_position(self):
        text = io.StringIO()
        with patch.object(sys, 'argv', ['replay', '--help']), redirect_stdout(text):
            with self.assertRaises(SystemExit) as error:
                replay.main()
        self.assertEqual(error.exception.code, 0)
        self.assertIn('--seat {0,1}', text.getvalue())
        self.assertIn('Player position whose recorded actions', text.getvalue())


if __name__ == '__main__':
    unittest.main()

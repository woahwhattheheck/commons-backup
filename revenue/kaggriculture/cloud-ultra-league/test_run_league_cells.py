"""Cell/process result binding; launcher fixtures execute zero official games."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_league import cell, launch, load_job, read_cell_result


# This fixture exercises real child processes and result files, not game strength.
EVALUATOR_FIXTURE = '''
class Actor:
    pass
class Engine:
    specification = {}
def get_engine(engine, loader):
    return Engine(), {}
def play(engine, specs, cache, loader, seed, seat, *args):
    return {"seed": seed, "candidate_seat": seat, "status": "complete",
            "scores": [1, 0], "failure": None, "wall_seconds": 0.0}
'''


class CellResultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'result.json'
        self.item = {'id': 'cell-1', 'seed': 11, 'seat': 0, 'opponent': 'fixture'}
        self.freeze = 'a' * 64
        self.result = {'cell_id': 'cell-1', 'seed': 11, 'candidate_seat': 0,
                       'opponent': 'fixture', 'freeze_sha256': self.freeze,
                       'status': 'complete', 'scores': [1, 0], 'failure': None}

    def read(self, code=0):
        return read_cell_result(self.path, self.item, code, self.freeze)

    def save(self):
        self.path.write_text(json.dumps(self.result))

    def test_complete_result_requires_successful_child(self):
        self.save()
        before = self.path.read_bytes()
        result = self.read(1)
        self.assertEqual(result['status'], 'driver_failed')
        self.assertEqual(result['failure']['kind'], 'child_exit_after_result')
        self.assertEqual(result['failure']['returncode'], 1)
        self.assertNotIn('scores', result)
        self.assertEqual(self.path.read_bytes(), before)

    def test_successful_child_and_bound_result_are_preserved(self):
        self.save()
        self.assertEqual(self.read(), self.result)

    def test_genuine_evaluator_failure_is_preserved(self):
        self.result.update(status='failed', scores=None,
                           failure={'kind': 'timeout', 'seat': 0, 'step': 3})
        self.save()
        self.assertEqual(self.read(1), self.result)

    def test_each_identity_field_must_match(self):
        for key, wrong in [('cell_id', 'other'), ('seed', 12), ('candidate_seat', 1),
                           ('opponent', 'other'), ('freeze_sha256', 'b' * 64)]:
            with self.subTest(key=key):
                changed = dict(self.result, **{key: wrong})
                self.path.write_text(json.dumps(changed))
                result = self.read()
                self.assertEqual(result['failure']['kind'], 'result_identity_mismatch')
                self.assertEqual(result['failure']['fields'], [key])
                self.assertNotIn('scores', result)

    def test_missing_identity_and_wrong_numeric_type_are_not_matches(self):
        for changed in [dict(self.result, candidate_seat=False),
                        {k: v for k, v in self.result.items() if k != 'cell_id'}]:
            with self.subTest(changed=changed):
                self.path.write_text(json.dumps(changed))
                self.assertEqual(self.read()['failure']['kind'], 'result_identity_mismatch')

    def test_missing_file_is_retained_as_driver_failure(self):
        result = self.read(1)
        self.assertEqual(result['failure']['kind'], 'result_read_error')
        self.assertEqual(result['failure']['returncode'], 1)

    def test_malformed_result_does_not_escape_the_collector(self):
        for payload in [b'{', b'\xff']:
            with self.subTest(payload=payload):
                self.path.write_bytes(payload)
                self.assertEqual(self.read()['failure']['kind'], 'result_read_error')
                self.assertEqual(self.path.read_bytes(), payload)

    def test_result_schema_is_checked(self):
        for value in [None, [], {}, {'status': 'unexpected'}]:
            with self.subTest(value=value):
                self.path.write_text(json.dumps(value))
                self.assertEqual(self.read()['failure']['kind'], 'result_schema_error')


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'job.json'
        self.output = self.root / 'output'
        evaluator = self.root / 'fixture_evaluator.py'
        evaluator.write_text(EVALUATOR_FIXTURE)
        self.cfg = {'evaluator': str(evaluator), 'engine': 'fixture', 'loader': 'fixture',
                    'candidate': 'fixture', 'opponents': {'fixture': 'fixture'},
                    'rng_seed': 0, 'action_timeout': 1, 'startup_timeout': 1,
                    'game_timeout': 1, 'jobs': 2, 'output': str(self.output),
                    'cells': [{'id': 'cell-1', 'seed': 11, 'seat': 0, 'opponent': 'fixture'}]}

    def save(self):
        self.config.write_text(json.dumps(self.cfg))
        return argparse.Namespace(config=str(self.config), cell=None)

    def test_duplicate_ids_are_rejected_before_starting_or_writing(self):
        self.cfg['cells'].append(dict(self.cfg['cells'][0], seed=12, seat=1))
        args = self.save()
        with patch('run_league.subprocess.Popen') as proc:
            with self.assertRaisesRegex(ValueError, 'Duplicate cell id'):
                launch(args)
        proc.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_direct_cell_rejects_duplicate_ids_before_loading(self):
        self.cfg['cells'].append(dict(self.cfg['cells'][0], seed=12))
        args = self.save()
        args.cell = 'cell-1'
        with patch('run_league.load_evaluator') as loader:
            with self.assertRaisesRegex(ValueError, 'Duplicate cell id'):
                cell(args)
        loader.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_missing_or_nonstring_cell_id_has_no_output(self):
        for value in [None, {}, {'id': ''}, {'id': 1}]:
            with self.subTest(value=value):
                self.cfg['cells'] = [value]
                args = self.save()
                with self.assertRaisesRegex(ValueError, 'nonempty string id'):
                    launch(args)
                self.assertFalse(self.output.exists())

    def test_nonlist_cells_are_rejected(self):
        self.cfg['cells'] = {}
        with self.assertRaisesRegex(ValueError, 'cells must be a list'):
            load_job(self.save().config)

    def test_hash_identifies_the_same_bytes_that_were_parsed(self):
        self.save()
        cfg, digest = load_job(self.config)
        self.assertEqual(cfg, self.cfg)
        self.assertEqual(digest, hashlib.sha256(self.config.read_bytes()).hexdigest())

    def test_real_children_complete_both_phases_with_bound_results(self):
        self.cfg['cells'] = [dict(self.cfg['cells'][0], id=f'cell-{i}', seed=11+i,
                                  seat=i % 2) for i in range(9)]
        args = self.save()
        with contextlib.redirect_stdout(io.StringIO()):
            code = launch(args)
        self.assertEqual(code, 0)
        state = json.loads((self.output / 'BATCH-STATE.json').read_text())
        self.assertEqual(state['phase'], 'complete')
        self.assertEqual(len(state['finished_cells']), 9)
        for scheduled, row in zip(self.cfg['cells'], state['finished_cells']):
            result = json.loads((self.output / scheduled['id'] / 'result.json').read_text())
            self.assertEqual((row['status'], row['returncode']), ('complete', 0))
            self.assertEqual(result['seed'], scheduled['seed'])
            self.assertEqual(result['candidate_seat'], scheduled['seat'])
            self.assertEqual(result['freeze_sha256'], state['freeze_sha256'])
            self.assertEqual(result['recorded_transitions'], 0)


if __name__ == '__main__':
    unittest.main()

"""Focused scheduler tests: real threads/files, synthetic child-process boundary.

No official games, actor decisions, or provider calls are made by this suite.
Run with PYTHONPATH set to the directory containing the run_league under test.
"""
import contextlib
import io
import hashlib
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

import run_league as driver


class BatchCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / 'output'
        self.config = self.root / 'job.json'
        self.launched = []
        self.lock = threading.Lock()
        self.release_slow = threading.Event()
        self.fast_finished = threading.Event()

    def configure(self, count):
        self.cells = [dict(id=f'cell{i}', seed=i, seat=i % 2, opponent='synthetic')
                      for i in range(count)]
        self.config.write_text(json.dumps(dict(output=str(self.out), jobs=4,
                                              cells=self.cells)), encoding='utf-8')

    def popen(self, command, stdout, stderr):
        cell_id = command[-1]
        with self.lock:
            self.launched.append(cell_id)
        mode = self.modes.get(cell_id)
        if mode == 'spawn_error':
            raise OSError('synthetic child launch failure')
        if mode == 'interrupt':
            raise KeyboardInterrupt('synthetic interruption')
        harness = self

        class Process:
            # This is a synthetic transport PID, not a claimed process measurement.
            pid = 10000 + int(cell_id.removeprefix('cell'))

            def wait(self):
                if mode == 'slow':
                    if not harness.release_slow.wait(5):
                        raise RuntimeError('test did not release slow worker')
                path = harness.out / cell_id / 'result.json'
                path.parent.mkdir()
                if mode == 'missing_result':
                    return 7
                if mode == 'bad_json':
                    path.write_text('{', encoding='utf-8')
                elif mode == 'missing_status':
                    path.write_text('{}', encoding='utf-8')
                else:
                    item = next(row for row in harness.cells if row['id'] == cell_id)
                    result = dict(cell_id=cell_id, seed=item['seed'],
                                  candidate_seat=item['seat'], opponent=item['opponent'],
                                  freeze_sha256=hashlib.sha256(harness.config.read_bytes()).hexdigest(),
                                  status='complete', scores=[5, 3], failure=None,
                                  wall_seconds=0.01)
                    if mode == 'game_failure':
                        result.update(status='failed', scores=None,
                                      failure=dict(kind='game_timeout', step=3))
                    path.write_text(json.dumps(result), encoding='utf-8')
                if mode == 'fast':
                    harness.fast_finished.set()
                return 1 if mode == 'game_failure' else 0

        return Process()

    def launch(self):
        with mock.patch.object(driver.subprocess, 'Popen', side_effect=self.popen):
            with contextlib.redirect_stdout(io.StringIO()):
                return driver.launch(SimpleNamespace(config=str(self.config)))

    def snapshot(self):
        return json.loads((self.out / 'BATCH-STATE.json').read_text(encoding='utf-8'))

    def assert_operational_failure_preserved(self, expected_kind, expected_type=None):
        self.assertEqual(self.launch(), 1)
        state = self.snapshot()
        rows = {row['id']: row for row in state['finished_cells']}
        self.assertEqual(state['stopped'], 'operational_failure')
        self.assertEqual(set(rows), {f'cell{i}' for i in range(8)})
        self.assertEqual(rows['cell0']['status'], 'driver_failed')
        self.assertEqual(rows['cell0']['failure']['kind'], expected_kind)
        if expected_type is not None:
            self.assertEqual(rows['cell0']['failure']['error_type'], expected_type)
        self.assertIsNone(rows['cell0']['scores'])
        self.assertTrue(all(rows[f'cell{i}']['status'] == 'complete' for i in range(1, 8)))
        self.assertCountEqual(self.launched, [f'cell{i}' for i in range(8)])
        self.assertFalse((self.out / 'cell8.log').exists())

    def test_spawn_failure_keeps_sibling_results_and_stops_expansion(self):
        self.configure(9)
        self.modes = {'cell0': 'spawn_error'}
        self.assert_operational_failure_preserved('driver_exception', 'OSError')
        row = next(row for row in self.snapshot()['finished_cells'] if row['id'] == 'cell0')
        self.assertIsNone(row['pid'])
        self.assertIsNone(row['returncode'])
        self.assertIn('synthetic child launch failure', row['failure']['error'])

    def test_malformed_result_keeps_sibling_results_and_stops_expansion(self):
        self.configure(9)
        self.modes = {'cell0': 'bad_json'}
        self.assert_operational_failure_preserved('result_read_error')
        self.assertEqual((self.out / 'cell0/result.json').read_text(), '{')
        row = next(row for row in self.snapshot()['finished_cells'] if row['id'] == 'cell0')
        self.assertEqual(row['returncode'], 0)
        self.assertEqual(row['pid'], 10000)

    def test_missing_status_keeps_sibling_results_and_stops_expansion(self):
        self.configure(9)
        self.modes = {'cell0': 'missing_status'}
        self.assert_operational_failure_preserved('result_schema_error')

    def test_completed_cell_is_checkpointed_before_earlier_slow_cell(self):
        self.configure(2)
        self.modes = {'cell0': 'slow', 'cell1': 'fast'}
        saved_fast = threading.Event()
        real_write = driver.write_json
        outcome = {}

        def observe_write(path, value):
            real_write(path, value)
            if any(row['id'] == 'cell1' for row in value.get('finished_cells', [])):
                saved_fast.set()

        def target():
            try:
                outcome['code'] = self.launch()
            except BaseException as exc:
                outcome['error'] = exc

        with mock.patch.object(driver, 'write_json', side_effect=observe_write):
            thread = threading.Thread(target=target)
            thread.start()
            try:
                fast_completed = self.fast_finished.wait(2)
                fast_checkpointed = saved_fast.wait(0.5)
                before_release = self.snapshot()['finished_cells']
            finally:
                self.release_slow.set()
                thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertNotIn('error', outcome)
        self.assertEqual(outcome.get('code'), 0)
        self.assertTrue(fast_completed)
        self.assertTrue(fast_checkpointed, 'completed sibling was blocked behind input-order wait')
        self.assertEqual([row['id'] for row in before_release], ['cell1'])
        self.assertCountEqual(self.launched, ['cell0', 'cell1'])

    def test_ordinary_game_failure_is_unchanged(self):
        self.configure(9)
        self.modes = {'cell0': 'game_failure'}
        self.assertEqual(self.launch(), 1)
        row = next(row for row in self.snapshot()['finished_cells'] if row['id'] == 'cell0')
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['returncode'], 1)
        self.assertEqual(row['failure'], dict(kind='game_timeout', step=3))
        self.assertEqual(len(self.launched), 8)

    def test_missing_result_keeps_real_returncode(self):
        self.configure(1)
        self.modes = {'cell0': 'missing_result'}
        self.assertEqual(self.launch(), 1)
        row = self.snapshot()['finished_cells'][0]
        self.assertEqual(row['status'], 'driver_failed')
        self.assertEqual(row['returncode'], 7)
        self.assertEqual(row['failure']['kind'], 'result_read_error')
        self.assertEqual(row['failure']['returncode'], 7)

    def test_successful_first_eight_allow_remaining_once(self):
        self.configure(10)
        self.modes = {}
        self.assertEqual(self.launch(), 0)
        state = self.snapshot()
        self.assertEqual(state['phase'], 'complete')
        self.assertEqual(len(state['finished_cells']), 10)
        self.assertCountEqual(self.launched, [f'cell{i}' for i in range(10)])
        self.assertTrue(all(row['status'] == 'complete' for row in state['finished_cells']))

    def test_remaining_phase_exception_keeps_all_other_results(self):
        self.configure(10)
        self.modes = {'cell8': 'spawn_error'}
        self.assertEqual(self.launch(), 1)
        state = self.snapshot()
        rows = {row['id']: row for row in state['finished_cells']}
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows['cell8']['status'], 'driver_failed')
        self.assertEqual(rows['cell9']['status'], 'complete')
        self.assertCountEqual(self.launched, [f'cell{i}' for i in range(10)])

    def test_keyboard_interrupt_is_not_misreported_as_completed(self):
        self.configure(1)
        self.modes = {'cell0': 'interrupt'}
        with self.assertRaises(KeyboardInterrupt):
            self.launch()
        self.assertEqual(self.snapshot()['finished_cells'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)

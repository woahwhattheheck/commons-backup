"""Postprocessing must not rerun the expensive measured workload."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import benchmark


class SummaryOnlyTests(unittest.TestCase):
    def test_existing_samples_are_relabelled_without_loading_or_launching_actors(self):
        raw = (HERE / 'RESULTS.json').read_bytes()
        with tempfile.TemporaryDirectory() as work:
            target = Path(work) / 'summary.json'
            argv = ['benchmark.py', '--summarize-only', str(HERE / 'RESULTS.json'),
                    '--output', str(target)]
            forbidden = AssertionError('Summary-only must not load a policy or start any actor')
            with patch.object(sys, 'argv', argv), \
                    patch.object(benchmark, 'load_evaluator', side_effect=forbidden), \
                    patch.object(benchmark, 'prepare', side_effect=forbidden), \
                    patch.object(benchmark, 'run_cohort', side_effect=forbidden), \
                    patch('subprocess.Popen', side_effect=forbidden), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(benchmark.main(), 0)
            result = json.loads(target.read_text())
        self.assertEqual((HERE / 'RESULTS.json').read_bytes(), raw)
        self.assertEqual(result['fresh_process_samples'], 33)
        self.assertEqual(sum(row['completed_first_actions'] for row in result['summary'].values()), 33)
        self.assertTrue(result['cross_scheduling_action_parity']['all_returned_actions_identical'])
        self.assertFalse(result['cross_scheduling_action_parity']['historical_expected_action_available'])
        self.assertFalse(result['cross_scheduling_action_parity']['engine_legality_checked'])
        self.assertNotIn('valid_first_actions', json.dumps(result))


if __name__ == '__main__':
    unittest.main(verbosity=2)

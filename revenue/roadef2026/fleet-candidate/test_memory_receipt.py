"""Full Supervisor receipt integration, separate from method-only procfs fixtures."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import supervisor
import test_memory_sampling as fixtures


class MemoryReceiptTests(unittest.TestCase):
    def test_unsampled_receipt_preserves_null_peak(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"PORTFOLIO_ARTIFACTS": temp}):
            root = Path(temp)
            engine = supervisor.Supervisor([root / "n", root / "t", root / "s"], root / "out")
            engine.save_receipt("running")
            receipt = json.loads(engine.receipt.read_text())
            self.assertIsNone(receipt["peak_sampled_process_rss_kib"])
            self.assertEqual(receipt["memory_sampling"], {"status": "not_sampled"})
            self.assertIn("excludes descendants/page cache", receipt["memory_measurement"])
            self.assertEqual(receipt["status"], "running")
            self.assertFalse(receipt["validated"])

    def test_actual_sampler_partial_coverage_reaches_receipt(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"PORTFOLIO_ARTIFACTS": temp}):
            root = Path(temp)
            engine = supervisor.Supervisor([root / "n", root / "t", root / "s"], root / "out")
            engine.peak_sampled_rss_kib = 700
            engine.next_rss_sample = 0
            engine.lanes = [{"name": "fixture", "executable": root / "fake", "process": fixtures.Proc(200)}]
            proc = root / "proc"
            (proc / "self").mkdir(parents=True)
            (proc / "self/status").write_text(fixtures.fields(100, 1, 100))
            real_scandir = os.scandir
            def path(value):
                p = Path(value)
                return proc / p.relative_to('/proc') if str(p).startswith('/proc') else p
            with patch.object(supervisor, 'Path', side_effect=path), patch.object(os, 'getpid', return_value=100), patch.object(supervisor.sys, 'platform', 'linux'), patch.object(os, 'scandir', side_effect=lambda value: real_scandir(proc)):
                engine.sample_rss()
            engine.save_receipt('running')
            result = json.loads(engine.receipt.read_text())
            self.assertEqual(result['peak_sampled_process_rss_kib'],700)
            self.assertEqual(result['memory_sampling']['status'],'partial')
            self.assertEqual(result['memory_sampling']['sampled_sum_kib'],100)
            self.assertEqual(result['memory_sampling']['expected_processes'],2)
            self.assertEqual(result['memory_sampling']['sampled_processes'],1)
            self.assertEqual(result['status'],'running')
            self.assertFalse(result['validated'])

if __name__ == '__main__': unittest.main()

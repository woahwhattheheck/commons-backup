"""Verify the shipped raw evidence, its reuse accounting, and tamper detection."""
import json
from pathlib import Path
import tempfile
import unittest
import panel

ROOT = Path(__file__).resolve().parents[1]
reports = panel.load(ROOT / 'results/read_reports.py', 't07_published_reports_test')


class ReportTests(unittest.TestCase):
    def test_exact_report_archive_and_failure_accounting(self):
        members = reports.load_reports()
        self.assertEqual(len(members), 14)
        summary = reports.summary(members)
        self.assertEqual(summary['unique_attempts'], 42)
        self.assertEqual(summary['status_counts'], {'complete': 40, 'failed': 2})
        self.assertEqual(summary['reused_rows_not_counted_again'], 10)
        self.assertTrue(all(row['step'] == 0 for row in summary['failed_attempts']))

    def test_original_wrapper_failure_and_fixed_source_are_distinct(self):
        members = reports.load_reports()
        self.assertIn(b'Path(__file__)', members['failed-wrapper-source/no_preempt.py'])
        fixed = (ROOT / 'runtime/nearclone/no_preempt.py').read_bytes()
        self.assertNotEqual(members['failed-wrapper-source/no_preempt.py'], fixed)
        self.assertIn(b'__raw_path__', fixed)
        first = json.loads(members['nearclone-development.freeze.json'])
        second = json.loads(members['nearclone-development-v2.freeze.json'])
        self.assertEqual(first['source'], second['source'])
        self.assertNotEqual(first['wrapper_sha256'], second['wrapper_sha256'])

    def test_corrupt_part_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / reports.PARTS[0][0]).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'Report part differs'):
                reports.archive_bytes(root)


if __name__ == '__main__':
    unittest.main()

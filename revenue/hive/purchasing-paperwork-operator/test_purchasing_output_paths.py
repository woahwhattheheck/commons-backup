"""Real filesystem and CLI tests for input/output alias preservation."""
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import purchasing_operator as app

OUTPUTS = ('reconciliation.json', 'accounting_import.csv', 'exception_drafts.json')


class PurchasingOutputPathsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def fixtures(self, directory=None):
        root = directory or self.root
        root.mkdir(parents=True, exist_ok=True)
        tables = [
            ('vendors.csv', ['supplier_id', 'canonical_name', 'aliases'],
             ['SUP-1', 'Example Supply', 'Example']),
            ('pos.csv', ['po_number', 'po_line', 'supplier_id', 'po_date', 'currency', 'sku',
                         'description', 'quantity', 'unit_price'],
             ['PO-1', '1', 'SUP-1', '2026-09-01', 'USD', '0007', 'Filter', '4', '12.50']),
            ('invoices.csv', ['invoice_number', 'line_number', 'vendor_name', 'invoice_date',
                              'due_date', 'currency', 'po_number', 'po_line', 'sku',
                              'description', 'quantity', 'unit_price'],
             ['INV-1', '1', 'Example', '2026-09-07', '2026-10-07', 'USD', 'PO-1', '1',
              '0007', 'Filter', '4', '12.50']),
        ]
        paths = []
        for name, fields, row in tables:
            buf = io.StringIO(newline='')
            writer = csv.writer(buf, lineterminator='\n')
            writer.writerow(fields)
            writer.writerow(row)
            path = root / name
            path.write_text(buf.getvalue(), encoding='utf-8')
            paths.append(path)
        return paths

    def symlink(self, target, link, *, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (NotImplementedError, PermissionError) as exc:
            self.skipTest(f'symlinks unavailable: {exc}')

    def reject_without_changes(self, paths, out, message='overlaps'):
        before = {p: p.read_bytes() for p in paths}
        existing = {p: p.read_bytes() for p in out.iterdir() if p.is_file()} if out.exists() else {}
        with self.assertRaisesRegex(app.PurchasingError, message):
            app.run(*paths, out)
        self.assertEqual(before, {p: p.read_bytes() for p in paths})
        self.assertEqual(existing, {p: p.read_bytes() for p in existing})
        self.assertEqual(set(existing), {p for p in out.iterdir() if p.is_file()})

    def test_each_output_name_cannot_overwrite_any_input(self):
        for output in OUTPUTS:
            for index in range(3):
                with self.subTest(output=output, source=index):
                    root = self.root / f'{output}-{index}'
                    paths = self.fixtures(root)
                    out = root / 'out'
                    out.mkdir()
                    paths[index] = paths[index].rename(out / output)
                    self.reject_without_changes(paths, out)

    def test_output_hardlink_to_each_input_is_rejected(self):
        for index in range(3):
            with self.subTest(source=index):
                root = self.root / str(index)
                paths = self.fixtures(root)
                out = root / 'out'
                out.mkdir()
                os.link(paths[index], out / 'accounting_import.csv')
                self.reject_without_changes(paths, out)

    def test_output_symlink_to_input_is_rejected(self):
        paths = self.fixtures()
        out = self.root / 'out'
        out.mkdir()
        self.symlink(paths[2], out / 'accounting_import.csv')
        self.reject_without_changes(paths, out)

    def test_input_symlink_to_output_is_rejected(self):
        paths = self.fixtures()
        out = self.root / 'out'
        out.mkdir()
        target = paths[2].rename(out / 'accounting_import.csv')
        self.symlink(target, paths[2])
        self.reject_without_changes(paths, out)

    def test_relative_symlink_to_input_is_rejected(self):
        paths = self.fixtures()
        out = self.root / 'out'
        out.mkdir()
        self.symlink(Path('..') / paths[0].name, out / 'reconciliation.json')
        self.reject_without_changes(paths, out)

    def test_symlinked_output_directory_is_resolved(self):
        paths = self.fixtures()
        paths[2] = paths[2].rename(self.root / 'accounting_import.csv')
        out = self.root / 'output-link'
        self.symlink(self.root, out, directory=True)
        self.reject_without_changes(paths, out)

    def test_dotdot_spelling_still_detects_same_path(self):
        paths = self.fixtures()
        out = self.root / 'out'
        out.mkdir()
        (out / 'child').mkdir()
        paths[2] = paths[2].rename(out / 'accounting_import.csv')
        paths[2] = out / 'child' / '..' / 'accounting_import.csv'
        self.reject_without_changes(paths, out)

    def test_each_output_hardlink_pair_is_rejected(self):
        for first in range(3):
            for second in range(first + 1, 3):
                with self.subTest(first=first, second=second):
                    root = self.root / f'{first}-{second}'
                    paths = self.fixtures(root)
                    out = root / 'out'
                    out.mkdir()
                    a, b = out / OUTPUTS[first], out / OUTPUTS[second]
                    a.write_bytes(b'previous output\n')
                    os.link(a, b)
                    self.reject_without_changes(paths, out)

    def test_existing_output_symlink_pair_is_rejected(self):
        paths = self.fixtures()
        out = self.root / 'out'
        out.mkdir()
        (out / 'exception_drafts.json').write_bytes(b'previous draft\n')
        self.symlink(Path('exception_drafts.json'), out / 'reconciliation.json')
        self.reject_without_changes(paths, out)

    def test_dangling_output_symlink_pair_is_rejected_before_creation(self):
        paths = self.fixtures()
        out = self.root / 'out'
        out.mkdir()
        link = out / 'reconciliation.json'
        self.symlink(Path('exception_drafts.json'), link)
        with self.assertRaisesRegex(app.PurchasingError, 'overlaps'):
            app.run(*paths, out)
        self.assertTrue(link.is_symlink())
        self.assertFalse(link.exists())
        self.assertEqual([link], list(out.iterdir()))

    def test_distinct_existing_output_files_are_allowed(self):
        paths = self.fixtures()
        out = self.root / 'out'
        out.mkdir()
        for name in OUTPUTS:
            (out / name).write_bytes(b'identical prior content\n')
        before = [p.read_bytes() for p in paths]
        result = app.run(*paths, out)
        self.assertEqual(1, json.loads(result['report'].read_text())['summary']['matched_lines'])
        self.assertEqual(before, [p.read_bytes() for p in paths])
        self.assertNotEqual(result['report'].read_bytes(), result['drafts'].read_bytes())

    def test_distinct_existing_symlink_output_remains_supported(self):
        paths = self.fixtures()
        target = self.root / 'external-report.json'
        target.write_bytes(b'old report\n')
        out = self.root / 'out'
        out.mkdir()
        self.symlink(target, out / 'reconciliation.json')
        result = app.run(*paths, out)
        self.assertTrue(result['report'].is_symlink())
        self.assertEqual('RECONCILED_NOT_POSTED', json.loads(target.read_text())['status'])

    def test_distinct_dangling_symlink_output_remains_supported(self):
        paths = self.fixtures()
        target = self.root / 'new-external-report.json'
        out = self.root / 'out'
        out.mkdir()
        self.symlink(target, out / 'reconciliation.json')
        app.run(*paths, out)
        self.assertEqual('RECONCILED_NOT_POSTED', json.loads(target.read_text())['status'])

    def test_normal_repeated_run_preserves_source_and_output_contract(self):
        paths = self.fixtures()
        before = [p.read_bytes() for p in paths]
        out = self.root / 'new' / 'out'
        first = app.run(*paths, out)
        expected = {name: p.read_bytes() for name, p in first.items()}
        second = app.run(*paths, out)
        self.assertEqual(expected, {name: p.read_bytes() for name, p in second.items()})
        self.assertEqual(before, [p.read_bytes() for p in paths])
        with second['accounting'].open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual('50.00', rows[0]['line_total'])
        self.assertEqual('REVIEW_READY_NOT_POSTED', rows[0]['status'])

    def test_cli_alias_is_error_two_without_traceback_or_new_files(self):
        paths = self.fixtures()
        out = self.root / 'out'
        out.mkdir()
        paths[2] = paths[2].rename(out / 'accounting_import.csv')
        before = paths[2].read_bytes()
        result = subprocess.run(
            [sys.executable, str(Path(app.__file__).resolve()), '--vendors', str(paths[0]),
             '--purchase-orders', str(paths[1]), '--invoices', str(paths[2]), '--out-dir', str(out)],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn('overlaps', result.stderr)
        self.assertEqual('', result.stdout)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual(before, paths[2].read_bytes())
        self.assertEqual([paths[2]], list(out.iterdir()))

    def test_symlink_loop_diagnostic_preserves_other_outputs(self):
        paths = self.fixtures()
        out = self.root / 'out'
        out.mkdir()
        self.symlink(Path('reconciliation.json'), out / 'reconciliation.json')
        previous = out / 'exception_drafts.json'
        previous.write_bytes(b'previous draft\n')
        with self.assertRaisesRegex(app.PurchasingError, 'cannot inspect output paths'):
            app.run(*paths, out)
        self.assertEqual(b'previous draft\n', previous.read_bytes())
        self.assertFalse((out / 'accounting_import.csv').exists())


if __name__ == '__main__':
    unittest.main()

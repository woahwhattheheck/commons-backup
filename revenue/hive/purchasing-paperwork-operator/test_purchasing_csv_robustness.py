"""Consumer regressions for the landed strict purchasing CSV reader.

The core reader and its test_csv_intake.py suite remain unchanged.
"""
import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import purchasing_operator as app

VENDOR = ['supplier_id', 'canonical_name', 'aliases']
PO = ['po_number', 'po_line', 'supplier_id', 'po_date', 'currency', 'sku',
      'description', 'quantity', 'unit_price']
INVOICE = ['invoice_number', 'line_number', 'vendor_name', 'invoice_date',
           'due_date', 'currency', 'po_number', 'po_line', 'sku', 'description',
           'quantity', 'unit_price']

class PurchasingCSVTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def write(self, text, name='input.csv'):
        path = self.root / name
        path.write_bytes(text.encode('utf-8') if isinstance(text, str) else text)
        return path

    def read(self, text):
        return app._read_csv(self.write(text), set(VENDOR))

    def fixtures(self, *, multiline=False):
        def table(name, fields, rows):
            buf = io.StringIO(newline='')
            writer = csv.writer(buf, lineterminator='\n')
            writer.writerow(fields)
            writer.writerows(rows)
            return self.write(buf.getvalue(), name)
        vendors = table('vendors.csv', VENDOR, [['SUP-1', 'Example Supply', 'Example']])
        pos = table('pos.csv', PO, [
            ['PO-1', '1', 'SUP-1', '2026-09-01', 'USD', '0007', 'Filter', '4', '12.50'],
            ['PO-1', '2', 'SUP-1', '2026-09-01', 'USD', '0008', 'Belt', '2', '6.00'],
        ])
        invoices = table('invoices.csv', INVOICE, [
            ['INV-1', '1', 'Example', '2026-09-07', '2026-10-07', 'USD', 'PO-1',
             '1', '0007', 'Filter\nOriginal description' if multiline else 'Filter', '4', '12.50'],
            ['INV-1', '2', 'Example', '2026-09-07', '2026-10-07', 'USD', 'PO-1',
             '2', '0008', 'Belt', '3', '6.00'],
        ])
        return vendors, pos, invoices

    def cli(self, paths, out):
        return subprocess.run(
            [sys.executable, str(Path(app.__file__).resolve()), '--vendors', str(paths[0]),
             '--purchase-orders', str(paths[1]), '--invoices', str(paths[2]), '--out-dir', str(out)],
            capture_output=True, text=True, timeout=15,
        )

    def test_lf_crlf_and_cr_source_lines(self):
        for newline in ('\n', '\r\n', '\r'):
            with self.subTest(newline=repr(newline)):
                text = newline.join(['supplier_id,canonical_name,aliases', '', '001,Shop,', ''])
                self.assertEqual('3', self.read(text)[0]['_line'])

    def test_all_loaders_reject_extra_fields(self):
        paths = self.fixtures()
        for loader, path in zip((app.load_vendors, app.load_purchase_orders, app.load_invoices), paths):
            with self.subTest(loader=loader.__name__):
                original = path.read_bytes()
                lines = original.decode().splitlines()
                lines[1] += ',extra'
                path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
                with self.assertRaises(app.PurchasingError):
                    loader(path)
                path.write_bytes(original)

    def test_cli_bad_shape_returns_two_without_traceback(self):
        paths = self.fixtures()
        paths[0].write_text('supplier_id,canonical_name,aliases\nSUP-1,Example Supply,,extra\n')
        out = self.root / 'out'
        result = self.cli(paths, out)
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn('expected 3 columns, got 4', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertFalse(out.exists())

    def test_cli_invalid_utf8_returns_two_without_traceback(self):
        paths = self.fixtures()
        paths[2].write_bytes(paths[2].read_bytes() + b'\xff')
        result = self.cli(paths, self.root / 'out')
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertIn('utf-8', result.stderr.lower())
        self.assertNotIn('Traceback', result.stderr)

    def test_malformed_input_preserves_previous_output(self):
        paths = self.fixtures()
        out = self.root / 'out'
        produced = app.run(*paths, out)
        originals = {name: path.read_bytes() for name, path in produced.items()}
        paths[2].write_text(paths[2].read_text().replace(',unit_price\n', ',unit_price,unit_price\n'))
        with self.assertRaises(app.PurchasingError):
            app.run(*paths, out)
        self.assertEqual(originals, {name: path.read_bytes() for name, path in produced.items()})

    def test_reconciliation_keeps_totals_and_unsent_states(self):
        paths = self.fixtures()
        result = self.cli(paths, self.root / 'out')
        self.assertEqual(0, result.returncode, result.stderr)
        outputs = {key: Path(path) for key, path in json.loads(result.stdout).items()}
        report = json.loads(outputs['report'].read_text())
        self.assertEqual({'invoice_lines': 2, 'matched_lines': 1, 'exception_lines': 1,
                          'accounting_rows_posted': 0, 'drafts_sent': 0}, report['summary'])
        with outputs['accounting'].open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual('50.00', rows[0]['line_total'])
        self.assertEqual('0007', rows[0]['sku'])
        self.assertEqual('REVIEW_READY_NOT_POSTED', rows[0]['status'])
        drafts = json.loads(outputs['drafts'].read_text())['drafts']
        self.assertEqual('DRAFT_NOT_SENT', drafts[0]['status'])
        self.assertEqual(['quantity_mismatch:invoice=3,po=2'], drafts[0]['issues'])

    def test_multiline_provenance_reaches_report_and_draft(self):
        paths = self.fixtures(multiline=True)
        outputs = app.run(*paths, self.root / 'out')
        report = json.loads(outputs['report'].read_text())
        drafts = json.loads(outputs['drafts'].read_text())['drafts']
        self.assertEqual([2, 4], [row['invoice_source']['line'] for row in report['records']])
        self.assertEqual(4, drafts[0]['sources'][0]['line'])
        self.assertEqual(hashlib.sha256(paths[2].read_bytes()).hexdigest(),
                         drafts[0]['sources'][0]['sha256'])
        self.assertEqual(3, drafts[0]['sources'][1]['line'])

    def test_blank_line_vendor_diagnostic_uses_physical_line(self):
        path = self.write('supplier_id,canonical_name,aliases\n\n001,Shop,\n\n001,Again,\n')
        with self.assertRaisesRegex(app.PurchasingError, r':5:.*duplicate supplier_id'):
            app.load_vendors(path)

if __name__ == '__main__':
    unittest.main()

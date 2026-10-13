"""Receipt stock and audit log must remain two distinct output files."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import reorder_assistant as app


class ReceiptOutputPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stock = self.root / 'stock.csv'
        self.stock.write_text('sku,name,on_hand,on_order,allocated,unit\nA,Filter,3,0,2,each\n')
        self.plan = self.root / 'plan.json'
        self.plan.write_text(json.dumps({'schema': app.SCHEMA, 'purchase_orders': [
            {'supplier_id': 'S', 'lines': [{'supplier_sku': 'SA', 'sku': 'A', 'quantity': 9}]}]}))
        self.receipts = self.root / 'receipts.csv'
        self.receipts.write_text('receipt_id,received_at,supplier_id,supplier_sku,sku,quantity\nR,2026-09-09,S,SA,A,2\n')
        self.source_bytes = {p: p.read_bytes() for p in (self.stock, self.plan, self.receipts)}

    def args(self, out_stock, out_log):
        # Consume parser defaults so additive CLI options stay compatible.
        return app.parser().parse_args([
            'receive', '--stock', str(self.stock), '--plan', str(self.plan),
            '--receipts', str(self.receipts), '--out-stock', str(out_stock),
            '--out-log', str(out_log),
        ])

    def reject(self, out_stock, out_log):
        previous = {p: p.read_bytes() if p.exists() else None for p in (out_stock, out_log)}
        with self.assertRaisesRegex(app.ReorderError, 'different files'):
            app.command_receive(self.args(out_stock, out_log))
        for path, data in previous.items():
            if data is None:
                self.assertFalse(path.exists())
            else:
                self.assertEqual(data, path.read_bytes())
        for path, data in self.source_bytes.items():
            self.assertEqual(data, path.read_bytes())

    def test_same_new_output_path_is_not_created(self):
        path = self.root / 'result.csv'
        self.reject(path, path)

    def test_same_existing_output_is_not_overwritten(self):
        path = self.root / 'result.csv'
        path.write_text('existing result')
        self.reject(path, path)

    def test_lexical_path_alias_is_detected(self):
        sub = self.root / 'sub'
        sub.mkdir()
        self.reject(self.root / 'result.csv', sub / '..' / 'result.csv')

    def test_symlink_to_existing_output_is_detected(self):
        path, alias = self.root / 'result.csv', self.root / 'alias.json'
        path.write_text('existing result')
        alias.symlink_to(path.name)
        self.reject(path, alias)
        self.assertTrue(alias.is_symlink())

    def test_symlink_to_not_yet_created_output_is_detected(self):
        path, alias = self.root / 'result.csv', self.root / 'alias.json'
        alias.symlink_to(path.name)
        self.reject(path, alias)
        self.assertTrue(alias.is_symlink())

    def test_hardlink_to_existing_output_is_detected(self):
        path, alias = self.root / 'result.csv', self.root / 'alias.json'
        path.write_text('existing result')
        os.link(path, alias)
        self.reject(path, alias)
        self.assertTrue(path.samefile(alias))

    def test_equal_content_in_distinct_files_is_not_a_collision(self):
        out_stock, out_log = self.root / 'updated.csv', self.root / 'log.json'
        out_stock.write_text('old content')
        out_log.write_text('old content')
        app.command_receive(self.args(out_stock, out_log))
        self.assertEqual(5, app.load_stock(out_stock)['A'].on_hand)
        self.assertEqual(1, json.loads(out_log.read_text())['count'])

    def test_existing_in_place_stock_update_still_works(self):
        out_log = self.root / 'log.json'
        app.command_receive(self.args(self.stock, out_log))
        self.assertEqual(5, app.load_stock(self.stock)['A'].on_hand)
        self.assertEqual(1, json.loads(out_log.read_text())['count'])

    def test_distinct_symlink_targets_keep_working(self):
        actual_stock, actual_log = self.root / 'actual.csv', self.root / 'actual.json'
        out_stock, out_log = self.root / 'updated.csv', self.root / 'log.json'
        out_stock.symlink_to(actual_stock.name)
        out_log.symlink_to(actual_log.name)
        app.command_receive(self.args(out_stock, out_log))
        self.assertEqual(5, app.load_stock(actual_stock)['A'].on_hand)
        self.assertEqual(1, json.loads(actual_log.read_text())['count'])
        self.assertTrue(out_stock.is_symlink())
        self.assertTrue(out_log.is_symlink())

    def test_cli_reports_conflict_without_traceback_or_write(self):
        path = self.root / 'result.csv'
        path.write_text('existing result')
        run = subprocess.run([
            sys.executable, str(Path(app.__file__).resolve()), 'receive',
            '--stock', str(self.stock), '--plan', str(self.plan), '--receipts', str(self.receipts),
            '--out-stock', str(path), '--out-log', str(path),
        ], capture_output=True, text=True, timeout=10)
        self.assertEqual(2, run.returncode, run.stderr)
        self.assertIn('different files', run.stderr)
        self.assertNotIn('Traceback', run.stderr)
        self.assertEqual('existing result', path.read_text())


if __name__ == '__main__':
    unittest.main()

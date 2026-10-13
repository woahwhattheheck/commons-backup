# SPDX-License-Identifier: Apache-2.0
from collections import Counter
import json
from pathlib import Path
import unittest
from unpack_rows import expand


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).parent
        cls.encoded = (root / 'RESIDUAL-ROWS.json.xz.b64').read_bytes()
        cls.data = expand(cls.encoded)
        cls.rows = [json.loads(line) for line in cls.data.splitlines()]

    def test_complete_grid_and_stages(self):
        self.assertEqual({(r['seed'], r['seat']) for r in self.rows},
                         {(s, p) for s in range(2611151001, 2611151009) for p in (0, 1)})
        self.assertEqual(Counter(r['stage'] for r in self.rows), dict.fromkeys('ABCDR', 2131))

    def test_final_rows_and_requested_units(self):
        rows = [r for r in self.rows if r['stage'] == 'R']
        self.assertEqual(Counter(r['product'] for r in rows), {'WHEAT': 753, 'FERTILIZER': 1378})
        self.assertEqual(sum(r['quantity_requested'] for r in rows if r['product'] == 'WHEAT'), 5458)
        self.assertEqual(sum(r['quantity_requested'] for r in rows if r['product'] == 'FERTILIZER'), 5738)
        self.assertEqual(len({(r['seed'], r['seat'], r['step']) for r in rows}), 2049)

    def test_tampering_rejected(self):
        for bad in (self.encoded[:-1], b'X' + self.encoded[1:], self.encoded + b'\n'):
            with self.assertRaises(ValueError): expand(bad)

    def test_every_stage_keeps_required_diagnostic_scope(self):
        self.assertTrue(all(set(r['diagnostics']) <= {'operating_stock', 'feed_stock', 'early_capital'}
                            for r in self.rows))
        self.assertTrue(all('early_capital' in r['diagnostics'] for r in self.rows if r['stage'] in ('D', 'R')))


if __name__ == '__main__': unittest.main()

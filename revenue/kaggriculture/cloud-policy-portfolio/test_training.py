# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
import tempfile
import unittest
from features import predict
from train import fit, rows_from_panels, cross_validate


def row(seed, x, winner):
    return {'seed': seed, 'opponent': 'a' if seed % 2 else 'b', 'features': {'x': x},
            'labels': {p: {'outcome': 'W' if p == winner else 'L', 'margin': 1 if p == winner else -1,
                           'own_cash': 2 if p == winner else 0, 'rival_cash': 1}
                       for p in ('sell', 'carrot_sell')}}


class TrainingTests(unittest.TestCase):
    def test_held_data_never_enters_fit(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'panel.json'
            p.write_text(json.dumps({'panel': 'validation', 'games': []}))
            with self.assertRaises(ValueError):
                rows_from_panels([p])

    def test_real_split_and_seed_holdout(self):
        rows = [row(i, 0, 'sell') for i in range(4)] + [row(i, 1, 'carrot_sell') for i in range(4, 8)]
        tree = fit(rows)
        self.assertEqual(predict(tree, {'x': 0}), 'sell')
        self.assertEqual(predict(tree, {'x': 1}), 'carrot_sell')
        for fold in cross_validate(rows, 'seed'):
            self.assertEqual(fold['train_rows'], 7)
            self.assertEqual(fold['evaluation']['rows'], 1)

    def test_equal_results_preserve_sell(self):
        rows = [row(i, i % 2, 'sell') for i in range(8)]
        for r in rows:
            r['labels']['carrot_sell'] = dict(r['labels']['sell'])
        self.assertEqual(fit(rows)['policy'], 'sell')

    def test_unknown_counterfactual_preserved_and_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'panel.json'
            p.write_text(json.dumps({'panel': 'development', 'games': [
                {'seed': 1, 'opponent': 'a', 'candidate_seat': 0, 'arm': 'sell', 'status': 'complete'}]}))
            rows, excluded = rows_from_panels([p])
            self.assertEqual(rows, [])
            self.assertEqual(excluded[0]['reason'], 'missing_coherent_counterfactual')


if __name__ == '__main__':
    unittest.main()

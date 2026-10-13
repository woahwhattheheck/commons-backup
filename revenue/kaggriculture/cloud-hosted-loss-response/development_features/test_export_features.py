# SPDX-License-Identifier: MIT
"""Importer regressions. All observation fixtures below are synthetic, not games."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import export_features as e

FEATURE_SOURCE = e.HERE.parents[1] / 'cloud-policy-portfolio' / 'features.py'


def snapshot(step=360, money=123):
    return {'step': step, 'prices': {'prices': {'WHEAT': 4}, 'inventory': {'WHEAT': -7}},
            'shops': {'unlocked_shops': ['BAKERY']},
            'farms': [{'money': money, 'tiles': [[{'crop': 'WHEAT', 'yield_units': 3}]]}, {'money': 456, 'tiles': [[]]}],
            'private': [{'shed': {'WHEAT': 2}, 'seeds': {'WHEAT': 8}}, {'secret_other_shed': 999}],
            'actions': [{'do_not_export': 'current-action'}, {'do_not_export': 'rival-action'}],
            'seed': 99, 'terminal_score': 999999, 'future_prices': {'WHEAT': 900}}


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scores = e.load_scores(e.HERE / 'development-scores.csv')
        cls.extract = staticmethod(e.load_extractor(FEATURE_SOURCE))
        cls.key = ('dev_sell', 9850001, 'arlene', 0)

    def game(self, key=None):
        key = key or self.key
        labels = self.scores[key]
        scores = [labels['own_cash'], labels['rival_cash']]
        if key[3]:
            scores.reverse()
        return {'seed': key[1], 'opponent': key[2], 'candidate_seat': key[3],
                'status': 'complete', 'failure': None, 'scores': scores,
                'trace_sha256': labels['trace_sha256'],
                'timeline': [snapshot(0), snapshot(24), snapshot(360), snapshot(718, 999999)]}

    def test_real_development_labels_are_complete(self):
        result = e.build(self.scores, [])
        self.assertEqual(result['summary'], {'development_pairs': 18, 'label_rows': 36,
                                           'available_checkpoints': 0, 'new_games': 0,
                                           'full_prefix_proven_pairs': 0})
        self.assertEqual({p['own_cash_delta'] for p in result['pairs']}, {240, 340})
        self.assertEqual({p['rival_cash_delta'] for p in result['pairs']}, {0})
        for row in result['records']:
            self.assertIsNone(row['features'])
            self.assertIsNone(row['observation'])
        for pair in result['pairs']:
            self.assertIsNone(pair['continuation_pair_eligible'])

    def test_pinned_feature_implementation(self):
        features = self.extract(e.observation(snapshot(), 0))
        self.assertEqual(features['inventory_WHEAT'], -7)
        self.assertEqual(features['own_money'], 123)
        self.assertEqual(features['own_crop_WHEAT'], 1)
        self.assertEqual(features['own_held_WHEAT'], 3)
        self.assertEqual(features['shop_BAKERY'], 1)

    def test_exact_feature_pin_not_a_retyped_implementation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'features.py'
            p.write_bytes(Path(FEATURE_SOURCE).read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'differs'):
                e.load_extractor(p)

    def test_projection_has_only_own_private_and_public_fields(self):
        raw = snapshot()
        before = copy.deepcopy(raw)
        own = e.observation(raw, 0)
        self.assertEqual(set(own), {'step', 'player', 'market', 'town', 'farms', 'private'})
        self.assertNotIn('secret_other_shed', json.dumps(own))
        own['private']['shed']['WHEAT'] = -1
        self.assertEqual(raw, before)
        self.assertEqual(e.observation(raw, 1)['private'], raw['private'][1])

    def test_import_excludes_future_rows_and_labels_from_features(self):
        game = self.game()
        before = copy.deepcopy(game)
        row = e.import_game(game, self.key, self.scores[self.key], self.extract)
        self.assertEqual(row['features']['own_money'], 123)
        self.assertNotIn('seed', row['features'])
        self.assertNotIn('opponent', row['features'])
        self.assertNotIn('scores', row['features'])
        self.assertNotIn('secret_other_shed', json.dumps(row))
        self.assertEqual(set(row['sampled_prefix']), {'0', '24'})
        self.assertEqual(game, before)

    def test_missing_checkpoint_does_not_guess_features(self):
        game = self.game()
        game['timeline'] = [snapshot(359)]
        row = e.import_game(game, self.key, self.scores[self.key], self.extract)
        self.assertEqual(row['availability'], 'checkpoint_missing')
        self.assertIsNone(row['observation'])
        self.assertIsNone(row['features'])

    def test_duplicate_checkpoint_rejected(self):
        game = self.game()
        game['timeline'].append(snapshot())
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            e.import_game(game, self.key, self.scores[self.key], self.extract)

    def test_wrong_seat_trace_score_and_failure_are_not_joined(self):
        mutations = [('candidate_seat', 1), ('trace_sha256', '0' * 64),
                     ('scores', [0, 0]), ('status', 'failed'), ('failure', {'error': 'fixture'})]
        for field, value in mutations:
            with self.subTest(field=field):
                game = self.game()
                game[field] = value
                with self.assertRaises(ValueError):
                    e.import_game(game, self.key, self.scores[self.key], self.extract)

    def test_held_report_is_not_read(self):
        with self.assertRaisesRegex(ValueError, 'development'):
            e.build(self.scores, [Path('held-seed.json')], self.extract)

    def test_report_requires_exact_bytes_and_engine(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'synthetic.json'
            raw = json.dumps({'engine_ref': e.ENGINE_REF, 'games': []}).encode()
            p.write_bytes(raw)
            spec = ('dev_sell', len(raw), hashlib.sha256(raw).hexdigest())
            self.assertEqual(e.read_original(p, spec)['games'], [])
            p.write_bytes(raw + b'\n')
            with self.assertRaisesRegex(ValueError, 'bytes'):
                e.read_original(p, spec)
            raw = json.dumps({'engine_ref': 'wrong', 'games': []}).encode()
            p.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'engine'):
                e.read_original(p, ('dev_sell', len(raw), hashlib.sha256(raw).hexdigest()))

    def test_complete_synthetic_transport_keeps_full_prefix_unknown(self):
        # Synthetic transport exercises parsing only. It is never a game result.
        with tempfile.TemporaryDirectory() as d:
            paths, specs = [], {}
            for name, (panel, _, _) in e.REPORTS.items():
                games = [self.game(k) for k in self.scores if e.report_for(k) == name]
                raw = json.dumps({'engine_ref': e.ENGINE_REF, 'games': games}).encode()
                p = Path(d) / name
                p.write_bytes(raw)
                paths.append(p)
                specs[name] = (panel, len(raw), hashlib.sha256(raw).hexdigest())
            with patch.dict(e.REPORTS, specs, clear=True):
                result = e.build(self.scores, paths, self.extract)
                with self.assertRaisesRegex(ValueError, 'duplicate'):
                    e.build(self.scores, paths + [paths[0]], self.extract)
            self.assertEqual(result['summary']['available_checkpoints'], 36)
            for pair in result['pairs']:
                self.assertTrue(pair['checkpoint_observation_equal'])
                self.assertTrue(pair['sampled_prefix_equal'])
                self.assertIsNone(pair['full_prefix_equal'])
                self.assertIsNone(pair['continuation_pair_eligible'])

    def test_duplicate_or_held_label_is_not_accepted(self):
        content = (e.HERE / 'development-scores.csv').read_text()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'scores.csv'
            for invalid in (content + content.splitlines()[1] + '\n', content.replace('9850001', '9850101')):
                path.write_text(invalid)
                with self.assertRaises(ValueError):
                    e.load_scores(path)

    def test_cli_exports_real_index_deterministically(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'index.json'
            command = [sys.executable, '-B', str(e.HERE / 'export_features.py'), '--output', str(p)]
            subprocess.run(command, check=True, capture_output=True)
            first = p.read_bytes()
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(first, p.read_bytes())
            self.assertEqual(json.loads(first)['summary']['available_checkpoints'], 0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--feature-source', type=Path, default=FEATURE_SOURCE)
    args, rest = parser.parse_known_args()
    FEATURE_SOURCE = args.feature_source
    unittest.main(argv=[sys.argv[0], *rest])

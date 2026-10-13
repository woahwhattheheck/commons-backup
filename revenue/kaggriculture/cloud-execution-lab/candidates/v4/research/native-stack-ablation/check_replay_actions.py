# SPDX-License-Identifier: Apache-2.0
"""Explicit-root full-corpus replay and corrupted-input rejection checks."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

import replay_actions as r
from run_native_ablation import digest, encoded

ROOT = PANEL = None
VERIFIED = []


class ReplayChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.games = json.loads((PANEL/'RESULTS.json').read_bytes())
        cls.first = cls.games[0]
        cls.tape = PANEL / cls.first['tape_file']

    def test_01_complete_corpus(self):
        for game in self.games:
            with self.subTest(game=game['id']):
                receipt = r.replay(ROOT, game, PANEL/game['tape_file'])
                self.assertTrue(receipt['replay_verified'])
                VERIFIED.append(receipt)
        self.assertEqual(len(self.games), len(VERIFIED))

    def temporary_tape(self, directory, actions):
        path = Path(directory)/'mutant.json.gz'
        path.write_bytes(gzip.compress(encoded(actions), mtime=0))
        game = copy.deepcopy(self.first)
        game['tape_sha256'] = digest(path.read_bytes())
        return path, game

    def test_02_compressed_hash_corruption(self):
        game = dict(self.first, tape_sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'Compressed action tape'):
            r.replay(ROOT, game, self.tape)

    def test_03_decoded_hash_corruption(self):
        game = dict(self.first, action_sha256='0'*64)
        with self.assertRaisesRegex(ValueError,'Decoded action tape'):
            r.replay(ROOT, game, self.tape)

    def test_04_truncated_tape(self):
        actions = r.read_tape(self.tape, self.first)[:-1]
        with tempfile.TemporaryDirectory() as d:
            path, game = self.temporary_tape(d, actions)
            with self.assertRaisesRegex(ValueError,'719'):
                r.replay(ROOT, game, path)

    def test_05_missing_actor(self):
        actions = r.read_tape(self.tape, self.first)
        actions[7] = actions[7][:1]
        with tempfile.TemporaryDirectory() as d:
            path, game = self.temporary_tape(d, actions)
            with self.assertRaisesRegex(ValueError,'two-player'):
                r.replay(ROOT, game, path)

    def test_06_forged_seed(self):
        game = dict(self.first, seed=self.first['seed']+1)
        with self.assertRaisesRegex(ValueError,'trace or terminal'):
            r.replay(ROOT, game, self.tape)

    def test_07_forged_score_and_atomic_snapshot_failure(self):
        game = copy.deepcopy(self.first); game['scores'][0] += 1
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)/'must-not-exist.gz'
            with self.assertRaisesRegex(ValueError,'trace or terminal'):
                r.replay(ROOT, game, self.tape, output)
            self.assertFalse(output.exists())
            self.assertEqual([], list(Path(d).iterdir()))

    def test_08_changed_action_with_recomputed_tape_pins(self):
        actions = r.read_tape(self.tape, self.first)
        actions[0][0] = {'farmer':['PASS'], 'hands':[], 'market':[]}
        with tempfile.TemporaryDirectory() as d:
            path, game = self.temporary_tape(d, actions)
            game['action_sha256'] = digest(encoded(actions))
            with self.assertRaisesRegex(ValueError,'trace or terminal'):
                r.replay(ROOT, game, path)

    def test_09_wrong_source_and_noninteger_seat(self):
        with self.assertRaisesRegex(ValueError,'different source'):
            r.replay(ROOT, dict(self.first, source_manifest_sha256='0'*64), self.tape)
        with self.assertRaisesRegex(ValueError,'integer seed'):
            r.replay(ROOT, dict(self.first, candidate_seat=True), self.tape)

    def test_10_decompression_limit(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'big.gz'
            path.write_bytes(gzip.compress(b' '*(r.MAX_TAPE_BYTES+1), mtime=0))
            game = dict(self.first, tape_sha256=digest(path.read_bytes()))
            with self.assertRaisesRegex(ValueError,'size limit'):
                r.read_tape(path, game)

    def test_11_owned_observation_snapshots(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)/'snapshots.gz'
            receipt = r.replay(ROOT, self.first, self.tape, output)
            self.assertTrue(receipt['replay_verified'])
            with gzip.open(output, 'rt') as handle:
                rows = [json.loads(line) for line in handle]
            self.assertEqual(719, len(rows))
            self.assertEqual(list(range(719)), [row['step'] for row in rows])
            for row in (rows[0], rows[122], rows[-1]):
                self.assertIsNone(row['configuration'].get('seed'))
                self.assertEqual([0,1], [o['player'] for o in row['observations']])
                self.assertEqual(2, len(row['actions']))
            with self.assertRaisesRegex(ValueError,'new path'):
                r.replay(ROOT, self.first, self.tape, output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--panel', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    ROOT, PANEL = args.root.resolve(), args.panel.resolve()
    program = unittest.main(argv=['check_replay_actions.py','-v'], exit=False)
    result = {'tests_run':program.result.testsRun, 'successful':program.result.wasSuccessful(),
              'certified_games':len(VERIFIED), 'receipts':VERIFIED}
    args.receipt.write_bytes(encoded(result)+b'\n')
    raise SystemExit(not program.result.wasSuccessful())

# SPDX-License-Identifier: Apache-2.0
"""Support-reader fail-closed tests; synthetic records are not engagement."""
import copy
import hashlib
import lzma
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import harvest_support_recheck as check
import r04_cow_fert_salvage as helper


def records():
    farm = {'farmer': [0, 0], 'hands': [], 'tiles': [[None] * 10 for _ in range(10)]}
    obs = {'player': 0, 'step': 23, 'farms': [farm, copy.deepcopy(farm)],
           'private': {'shed': {}, 'inventories': [{}]}}
    action = {'farmer': ['PASS'], 'hands': [], 'market': []}
    rows = []
    for step in range(23, 696, 24):
        item = {'opponent': 'fixture', 'seed': 1, 'seat': 0, 'step': step,
                'observation': copy.deepcopy(obs), 'action': copy.deepcopy(action)}
        item['observation']['step'] = step
        rows.append(item)
    return rows


class SupportReader(unittest.TestCase):
    def test_exact_corpus_bytes(self):
        raw = b'{"ok":true}\n'
        compressed = lzma.compress(raw)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'x.xz'
            path.write_bytes(compressed)
            self.assertEqual(check.read_corpus(path, hashlib.sha256(compressed).hexdigest(),
                                              hashlib.sha256(raw).hexdigest()), [{'ok': True}])

    def test_four_fragments_restore_exact_bytes(self):
        raw = b'{"ok":true}\n'
        data = lzma.compress(raw)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'x.xz'
            cuts = [len(data) * i // 4 for i in range(5)]
            for i in range(1, 5):
                path.with_name(path.name + '.part%02d' % i).write_bytes(data[cuts[i - 1]:cuts[i]])
            self.assertEqual(check.read_corpus(path, hashlib.sha256(data).hexdigest(),
                                              hashlib.sha256(raw).hexdigest()), [{'ok': True}])

    def test_missing_fragment_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'x.xz'
            path.with_name(path.name + '.part01').write_bytes(b'not complete')
            with self.assertRaises(FileNotFoundError):
                check.read_corpus(path, '0' * 64, '0' * 64)

    def test_changed_compressed_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'x.xz'
            path.write_bytes(b'not the artifact')
            with self.assertRaisesRegex(ValueError, 'compressed corpus mismatch'):
                check.read_corpus(path, '0' * 64, '0' * 64)

    def test_changed_raw_digest_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'x.xz'
            data = lzma.compress(b'{}\n')
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'raw corpus mismatch'):
                check.read_corpus(path, hashlib.sha256(data).hexdigest(), '0' * 64)

    def test_changed_helper_rejected_before_import(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'x.py'
            path.write_text('raise RuntimeError("must not import")\n')
            with self.assertRaisesRegex(ValueError, 'helper source mismatch'):
                check.authenticate_helper(path, '0' * 40)

    def test_complete_coverage_and_identity(self):
        rows = records()
        original = copy.deepcopy(rows)
        result = check.review(rows, helper, [('fixture', 1, 0)], helper.STANDARD)
        self.assertEqual(result['boundaries'], 29)
        self.assertEqual(result['input_nonmutation_checks'], 116)
        self.assertEqual(result['off_identity_checks'], 58)
        self.assertEqual(result['proposals_harvest_only'], 0)
        self.assertEqual(result['proposals_completed_service'], 0)
        self.assertEqual(rows, original)

    def test_missing_boundary_rejected(self):
        with self.assertRaisesRegex(ValueError, 'incomplete boundary coverage'):
            check.review(records()[:-1], helper, [('fixture', 1, 0)], helper.STANDARD)

    def test_duplicate_boundary_rejected(self):
        rows = records()
        with self.assertRaisesRegex(ValueError, 'duplicate boundary'):
            check.review(rows + rows[:1], helper, [('fixture', 1, 0)], helper.STANDARD)

    def test_observation_seat_mismatch_rejected(self):
        rows = records()
        rows[0]['observation']['player'] = 1
        with self.assertRaisesRegex(ValueError, 'observation identity mismatch'):
            check.review(rows, helper, [('fixture', 1, 0)], helper.STANDARD)

    def test_malformed_cell_plan_rejected(self):
        with self.assertRaisesRegex(ValueError, 'invalid panel cells'):
            check.review([], helper, [], helper.STANDARD)

    def test_input_mutation_rejected(self):
        def bad(action, obs, cfg, **kwargs):
            obs['step'] = -1
            return action
        with self.assertRaisesRegex(ValueError, 'mutated a captured input'):
            check.review(records(), SimpleNamespace(apply_cow_fert_salvage=bad),
                         [('fixture', 1, 0)], helper.STANDARD)

    def test_off_copy_rejected(self):
        def bad(action, obs, cfg, **kwargs):
            return copy.deepcopy(action)
        with self.assertRaisesRegex(ValueError, 'OFF identity failure'):
            check.review(records(), SimpleNamespace(apply_cow_fert_salvage=bad),
                         [('fixture', 1, 0)], helper.STANDARD)

    def test_surplus_rows_preserved(self):
        rows = records()
        for row in rows:
            row['action']['hands'] = [['PLANT', 'WHEAT']]
        before = copy.deepcopy(rows)
        result = check.review(rows, helper, [('fixture', 1, 0)], helper.STANDARD)
        self.assertEqual(result['complete_actor_vectors'], 0)
        self.assertEqual(rows, before)
        self.assertEqual(result['proposals_completed_service'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)

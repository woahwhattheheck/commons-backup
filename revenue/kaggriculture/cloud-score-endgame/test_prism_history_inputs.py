# SPDX-License-Identifier: Apache-2.0
"""Causal data-boundary regressions; no engine, actor, or random game calls."""
from copy import deepcopy
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from prism_history_inputs import checked_member, encoded, extract_payload, run, sha


def fixture():
    cfg = {'episodeSteps': 5, 'turnsPerDay': 2, 'seed': 998, 'shedCapacity': 100}
    rows = []
    for i in range(5):
        observations = []
        for p in (0, 1):
            observations.append({'day': i//2, 'hour': i%2, 'step': i-1,
                'player': p, 'farms': [{'money': i}, {'money': 2*i}],
                'market': {'inventory': {'MILK': i}}, 'town': {'unlocked_shops': []},
                'private': {'shed': {'MILK': 30*p+i}, 'inventories': [{}], 'seeds': {}},
                'remainingOverageTime': 88, 'evaluation_only_label': 'forbidden'})
        rows.append({'step': i-1, 'observations': observations,
            'actions': [{'market': [['SELL', 'MILK', i+p]]} for p in (0, 1)],
            'status': ['DONE', 'DONE'] if i == 4 else ['ACTIVE', 'ACTIVE'],
            'rewards': [999, 998]})
    return rows, cfg


class BoundaryTests(unittest.TestCase):
    def test_exact_temporal_alignment_both_seats(self):
        rows, cfg = fixture()
        for seat in (0, 1):
            packet = extract_payload(rows, cfg, seat)
            self.assertEqual([h['observation']['step'] for h in packet['history']], [0,1,2])
            self.assertEqual([h['own_action'] for h in packet['history']],
                             [r['actions'][seat] for r in rows[1:4]])
            self.assertEqual(packet['observation']['step'], 3)
            self.assertEqual(packet['observation']['private'], rows[3]['observations'][seat]['private'])
            self.assertEqual(packet['selected_action'], rows[4]['actions'][seat])

    def test_drop_other_actor_actions_private_state_and_all_outcomes(self):
        rows, cfg = fixture()
        for seat in (0,1):
            before = extract_payload(rows, cfg, seat)
            changed = deepcopy(rows)
            for r in changed:
                r['observations'][1-seat] = {'private': 'OTHER_PLAYER_SECRET'}
                r['actions'][1-seat] = {'hidden': 'ACTUAL_RIVAL_ACTION'}
                r['rewards'] = ['POSTGAME_LABEL', 44]
            self.assertEqual(before, extract_payload(changed, cfg, seat))

    def test_terminal_observation_never_changes_runtime(self):
        rows, cfg = fixture()
        before = extract_payload(rows, cfg, 0)
        rows[-1]['observations'] = [{'ALL': 'FUTURE'}, {'ALL': 'FUTURE'}]
        self.assertEqual(before, extract_payload(rows, cfg, 0))

    def test_final_selected_own_action_is_intentionally_bound(self):
        rows, cfg = fixture()
        before = extract_payload(rows, cfg, 0)
        rows[-1]['actions'][0] = {'market': [['SELL','MILK',87]]}
        after = extract_payload(rows, cfg, 0)
        self.assertEqual(before['history'], after['history'])
        self.assertEqual(before['observation'], after['observation'])
        self.assertNotEqual(before['selected_action'], after['selected_action'])

    def test_input_not_mutated(self):
        rows, cfg = fixture(); original = deepcopy((rows,cfg))
        packet = extract_payload(rows,cfg,0)
        packet['history'][0]['observation']['private']['shed']['MILK'] = 900
        packet['selected_action']['market'].clear()
        self.assertEqual((rows,cfg), original)

    def test_null_seed_omission_and_overage_normalization(self):
        rows,cfg = fixture(); packet = extract_payload(rows,cfg,0)
        self.assertNotIn('seed',packet['configuration'])
        self.assertEqual(packet['observation']['remainingOverageTime'],0)
        self.assertNotIn('evaluation_only_label',packet['observation'])
        self.assertNotIn('rewards',packet)
        self.assertNotIn('status',packet)

    def test_missing_duplicate_and_out_of_order_rows(self):
        rows,cfg = fixture()
        for changed in [rows[:-1], rows+[rows[-1]], [rows[0], rows[2], rows[1], *rows[3:]]]:
            with self.assertRaises(ValueError): extract_payload(changed,cfg,0)

    def test_clock_conflict_rejected(self):
        rows,cfg = fixture();rows[2]['observations'][0]['hour']=99
        with self.assertRaises(ValueError):extract_payload(rows,cfg,0)

    def test_wrong_actor_rejected(self):
        rows,cfg = fixture();rows[1]['observations'][0]['player']=1
        with self.assertRaises(ValueError):extract_payload(rows,cfg,0)

    def test_invalid_actor_ids(self):
        rows,cfg=fixture()
        for p in (True,False,2,-1,'0',None):
            with self.assertRaises(ValueError):extract_payload(rows,cfg,p)

    def test_early_or_missing_terminal_status(self):
        rows,cfg=fixture()
        for i in (1,4):
            bad=deepcopy(rows);bad[i]['status']=['DONE','ACTIVE']
            with self.assertRaises(ValueError):extract_payload(bad,cfg,0)

    def test_bad_member_hash_and_size(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('a','test')
        with zipfile.ZipFile(stream) as z:
            good={'a':{'size':4,'sha256':sha(b'test')}}
            self.assertEqual(checked_member(z,good,'a'),b'test')
            for bad in [{'a':{'size':5,'sha256':sha(b'test')}},
                        {'a':{'size':4,'sha256':sha(b'bad')}}]:
                with self.assertRaises(ValueError):checked_member(z,bad,'a')

    def test_whole_archive_mismatch_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'bad.zip'; source.write_bytes(b'bad')
            target=Path(d)/'out'
            with self.assertRaises(ValueError):run(source,target)
            self.assertFalse(target.exists())

    def test_canonical_and_gzip_reproducibility(self):
        rows,cfg=fixture()
        one=encoded(extract_payload(rows,cfg,0));two=encoded(extract_payload(rows,cfg,0))
        self.assertEqual(one,two)
        self.assertEqual(gzip.compress(one,mtime=0),gzip.compress(two,mtime=0))


if __name__ == '__main__': unittest.main(verbosity=2)

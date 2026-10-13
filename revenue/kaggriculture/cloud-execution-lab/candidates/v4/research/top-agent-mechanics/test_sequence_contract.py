# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import csv
import dataclasses
import importlib.util
import itertools
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

import mine_top_mechanics as m
from sequence_contract import collect_witnesses, sequence_windows

HERE = Path(__file__).resolve().parent


def event(step, verb, *, actor=None, slot=None, source='unit', player='0',
          match='m', team='T', ordinal=0, target=''):
    return m.Event(match, team, player, step, source, verb, target, None,
                   ordinal, actor=actor, slot=slot)


def features(rows):
    return m.features_by_team(rows)[0]['T']


def sequences(rows):
    return {f for f, _ in sequence_windows(rows, m.token)}


class SequenceContract(unittest.TestCase):
    def test_simultaneous_actors_not_player_sequence(self):
        rows = [event(4, 'PICKUP', actor='0'), event(4, 'FERTILIZE', actor='1')]
        self.assertFalse(sequences(rows))
        self.assertIn('same_step|unit:FERTILIZE+unit:PICKUP', features(rows))

    def test_ambiguity_breaks_instead_of_skip_through(self):
        rows = [event(1, 'NORTH'), event(2, 'WATER'), event(2, 'HARVEST'), event(3, 'SOUTH')]
        self.assertFalse(sequences(rows))

    def test_actor_sequence_survives_other_workers(self):
        rows = [event(1, 'PICKUP', actor='0'), event(1, 'NORTH', actor='1'),
                event(2, 'FERTILIZE', actor='0'), event(2, 'SOUTH', actor='1')]
        self.assertEqual(sequences(rows), {'actor_seq2|unit:PICKUP>unit:FERTILIZE',
                                          'actor_seq2|unit:NORTH>unit:SOUTH'})

    def test_unknown_actor_is_all_actor_barrier(self):
        rows = [event(1, 'PICKUP', actor='0'), event(2, 'PASS'), event(3, 'FERTILIZE', actor='0')]
        self.assertFalse(any(x.startswith('actor_seq') for x in sequences(rows)))
        self.assertIn('seq3|unit:PICKUP>unit:PASS>unit:FERTILIZE', sequences(rows))

    def test_duplicate_actor_breaks_one_actor_only(self):
        rows = [event(1, 'PICKUP', actor='0'), event(2, 'WATER', actor='0'),
                event(2, 'HARVEST', actor='0'), event(3, 'DROP', actor='0'),
                event(1, 'NORTH', actor='1'), event(3, 'SOUTH', actor='1')]
        self.assertEqual({f for f in sequences(rows) if f.startswith('actor_seq')},
                         {'actor_seq2|unit:NORTH>unit:SOUTH'})

    def test_market_explicit_slots_override_csv_order(self):
        rows = [event(3, 'HIRE', slot=8, source='market', ordinal=0),
                event(3, 'SELL', slot=2, source='market', ordinal=1)]
        self.assertEqual(sequences(rows), {'seq2|market:SELL>market:HIRE'})

    def test_missing_duplicate_or_bad_market_slots_are_barriers(self):
        for slots in [(None, None), (1, None), (1, 1), (-1, 2), (True, 2), (1.0, 2)]:
            with self.subTest(slots=slots):
                rows = [event(0, 'A', source='market'),
                        event(1, 'B', source='market', slot=slots[0]),
                        event(1, 'C', source='market', slot=slots[1]),
                        event(2, 'D', source='market')]
                self.assertFalse(sequences(rows))

    def test_market_sequences_cross_steps_but_not_sources(self):
        rows = [event(1, 'SELL', source='market', slot=0), event(1, 'PASS'),
                event(3, 'HIRE', source='market', slot=0)]
        self.assertEqual(sequences(rows), {'seq2|market:SELL>market:HIRE'})

    def test_unknown_seat_never_makes_sequence_or_coincidence(self):
        rows = [event(1, 'NORTH', player='?'), event(2, 'SOUTH', player='?'),
                event(2, 'SELL', source='market', player='?')]
        self.assertFalse(sequences(rows))
        self.assertFalse(any(f.startswith('same_step|') for f in features(rows)))

    def test_selfplay_seats_do_not_leak_features(self):
        rows = [event(1, 'WATER', player='0'), event(1, 'HARVEST', player='1')]
        self.assertFalse(sequences(rows))
        self.assertFalse(any(f.startswith('same_step|') for f in features(rows)))
        self.assertEqual(m.features_by_team(rows)[1], {'T': 1})
        self.assertFalse(sequences([event(1, 'WATER', player='0'), event(2, 'HARVEST', player='1')]))

    def test_selfplay_count_buckets_not_added(self):
        rows = [event(1, 'SELL', source='market', player=str(i)) for i in (0, 1)]
        self.assertIn('count_bucket|1|market:SELL', features(rows))
        self.assertNotIn('count_bucket|2-3|market:SELL', features(rows))

    def test_singleton_chronology_remains_backwards_compatible(self):
        rows = [event(20, 'HARVEST'), event(10, 'WATER')]
        self.assertEqual(sequences(rows), {'seq2|unit:WATER>unit:HARVEST'})
        self.assertFalse(any(f.startswith('actor_seq') for f in features(rows)))

    def test_actor_zero_is_known_and_third_event_has_both_windows(self):
        rows = [event(i, v, actor='0') for i, v in enumerate(['PICKUP', 'NORTH', 'DROP'])]
        seq = sequences(rows)
        self.assertIn('actor_seq3|unit:PICKUP>unit:NORTH>unit:DROP', seq)
        self.assertIn('actor_seq2|unit:NORTH>unit:DROP', seq)

    def test_permutations_are_feature_invariant(self):
        rows = [event(1, 'A', actor='0'), event(1, 'B', actor='1'),
                event(2, 'C', actor='0'), event(2, 'D', actor='1'),
                event(1, 'SELL', source='market', slot=1),
                event(1, 'HIRE', source='market', slot=2)]
        expected = features(rows)
        for perm in itertools.permutations(rows):
            shuffled = [dataclasses.replace(e, ordinal=i) for i, e in enumerate(perm)]
            self.assertEqual(features(shuffled), expected)

    def test_witnesses_preserve_row_and_identity(self):
        rows = [event(8, 'HIRE', slot=2, source='market', ordinal=7),
                event(8, 'SELL', slot=0, source='market', ordinal=91)]
        before = list(rows)
        witnesses = collect_witnesses(rows, m.token)
        self.assertIn('seq2|market:SELL>market:HIRE', witnesses)
        pair = witnesses['seq2|market:SELL>market:HIRE'][0]
        self.assertEqual([r['ordinal'] for r in pair], [91, 7])
        self.assertEqual([r['slot'] for r in pair], [0, 2])
        self.assertEqual(rows, before)
        json.dumps(witnesses, allow_nan=False)

    def test_witness_cap_and_bad_limits(self):
        rows = [event(i, 'PASS') for i in range(10)]
        self.assertEqual(len(collect_witnesses(rows, m.token, limit_per_feature=2)
                             ['seq2|unit:PASS>unit:PASS']), 2)
        for limit in [0, -1, True, 1.5]:
            with self.assertRaises(ValueError):
                collect_witnesses(rows, m.token, limit_per_feature=limit)

    def test_actor_and_order_alias_csv(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'rows.csv'
            p.write_text('match_id,team,player,step,action,hand_id,order_index\nm,T,0,1,WATER,0,2\n')
            row = m.read_events(p, 'unit')[0]
            self.assertEqual(row.actor, '0')
            self.assertEqual(row.slot, 2)

    def test_bad_slot_csv_is_rejected(self):
        for val in ['-1', '1.5', 'NaN', 'True']:
            with tempfile.TemporaryDirectory() as td, self.subTest(value=val):
                p = Path(td) / 'rows.csv'
                p.write_text('match_id,team,player,step,action,raw_slot\nm,T,0,1,SELL,' + val + '\n')
                with self.assertRaises(m.DataError):
                    m.read_events(p, 'market')

    def test_team_match_source_boundaries(self):
        rows = [event(1, 'NORTH', actor='0'), event(2, 'SOUTH', actor='0', match='other'),
                event(3, 'WATER', actor='0', team='other')]
        self.assertFalse(sequences(rows))

    def test_report_declares_its_observation_semantics(self):
        rows = [event(1, 'PASS', team=t) for t in ['A', 'B', 'C']]
        report = m.rank_features(rows, {'A', 'B'})
        self.assertEqual(report['schema'], 'titan-v4-top-agent-mechanics/v2')
        self.assertIn('not necessarily same actor', report['sequence_contract']['seq'])
        self.assertIn('not successful execution', report['sequence_contract']['scope'])


if __name__ == '__main__':
    unittest.main()

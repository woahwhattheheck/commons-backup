# SPDX-License-Identifier: MIT
"""Regression coverage for the real archived-state reader and export path."""
import copy
import json
import lzma
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import reached_states as rs


def frame(step=698, seat=0):
    farm = {'money': 100, 'farmer': [4, 4], 'hands': [[0, 0]],
            'tiles': [[{} for _ in range(10)] for _ in range(10)]}
    observation = {'step': step, 'day': step//24, 'hour': step%24,
        'player': seat, 'farms': [copy.deepcopy(farm), copy.deepcopy(farm)],
        'market': {'prices': {'EGG': 5}}, 'town': {},
        'private': {'shed': {'WHEAT': 95}, 'seeds': {},
                    'inventories': [{'EGG': 8}, {'MILK': 100}]},
        'remainingOverageTime': 12}
    return {'step': step, 'observation': observation,
        'configuration': {'shedCapacity': 100, 'turnsPerDay': 24,
                          'seed': 999, '__raw_path__': '/private/source'},
        'actions': [{'market': [['SELL', 'EGG', 999]]}, {'secret': 'rival-action'}]}


def record(seat=0, frames=None, arm='sell', seed=1, scores=None):
    return {'seed': seed, 'candidate_seat': seat, 'arm': arm,
        'opponent': 'apex', 'status': 'complete', 'failure': None,
        'scores': [100, 90] if scores is None else scores,
        'final_day': [frame(seat=seat)] if frames is None else frames,
        'terminal': {'private': ['not for actor', 'not for actor']}}


def records():
    return {'dev/sell-1-apex-0.json': json.dumps(record()),
            'held/sell-2-apex-0.json': json.dumps(record(seed=2))}


class IntakeTests(unittest.TestCase):
    def test_default_phase_is_development(self):
        cases, rows = rs.collect(records())
        self.assertEqual(len(rows), 1)
        self.assertTrue(cases[0]['case_id'].startswith('dev-'))
        self.assertEqual(rows[0]['seed'], 1)

    def test_held_is_explicit_and_labelled_consumed(self):
        with tempfile.TemporaryDirectory() as root:
            result = rs.export(records(), Path(root)/'held', phase='held')
            self.assertIn('not fresh validation', result['split_status'])
            self.assertTrue(result['cases'][0]['case_id'].startswith('held-'))

    def test_mixed_split_is_not_defaultable(self):
        with self.assertRaises(ValueError):
            rs.collect(records(), phase='all')

    def test_labels_and_coactions_never_enter_input(self):
        original = record()
        changed = copy.deepcopy(original)
        changed['scores'] = [99999, 0]
        changed['seed'] = 444
        changed['final_day'][0]['actions'] = ['unknown-future']
        a, _ = rs.collect({'dev/a.json': json.dumps(original)})
        b, _ = rs.collect({'dev/b.json': json.dumps(changed)})
        self.assertEqual(a[0]['inputs'], b[0]['inputs'])
        self.assertEqual(a[0]['input_sha256'], b[0]['input_sha256'])
        self.assertNotIn('seed', a[0]['inputs']['configuration'])
        self.assertNotIn('__raw_path__', a[0]['inputs']['configuration'])
        self.assertEqual(set(a[0]['inputs']), {'observation', 'configuration'})

    def test_unknown_top_level_observation_metadata_is_excluded(self):
        f = frame()
        f['observation']['future_actions'] = [1, 2, 3]
        self.assertNotIn('future_actions', rs.actor_input(f, 0)['observation'])

    def test_same_inputs_dedup_without_erasing_references(self):
        r = record()
        cases, rows = rs.collect({'dev/a.json': json.dumps(r), 'dev/b.json': json.dumps(r)})
        self.assertEqual((len(cases), len(rows), len(cases[0]['references'])), (1, 2, 2))

    def test_seat_one_owns_its_private_inventory(self):
        f = frame(seat=1)
        f['observation']['private']['shed'] = {'MILK': 7}
        result = rs.actor_input(f, 1)
        self.assertEqual(result['observation']['private']['shed'], {'MILK': 7})
        self.assertEqual(result['observation']['player'], 1)

    def test_cross_seat_private_data_is_not_relabelled(self):
        with self.assertRaises(ValueError):
            rs.actor_input(frame(seat=1), 0)

    def test_missing_step_is_not_guessed(self):
        f = frame()
        del f['observation']['step']
        with self.assertRaises(ValueError):
            rs.actor_input(f, 0)

    def test_clock_mismatch(self):
        f = frame(); f['observation']['hour'] += 1
        with self.assertRaises(ValueError): rs.actor_input(f, 0)

    def test_absent_360_does_not_create_directory(self):
        with tempfile.TemporaryDirectory() as root:
            dest = Path(root)/'out'
            with self.assertRaises(ValueError): rs.export(records(), dest, step=360)
            self.assertFalse(dest.exists())

    def test_frames_must_be_ordered(self):
        r = record(frames=[frame(699), frame(698)])
        with self.assertRaises(ValueError): rs.collect({'dev/a.json': json.dumps(r)})

    def test_complete_record_needs_retained_frames(self):
        with self.assertRaises(ValueError):
            rs.collect({'dev/a.json': json.dumps(record(frames=[]))})

    def test_failure_is_not_a_completed_case(self):
        r = record(); r['status'] = 'failed'
        with self.assertRaises(ValueError): rs.collect({'dev/a.json': json.dumps(r)})

    def test_unknown_or_empty_arm_is_error(self):
        for arms in ([], ['missing'], ['sell', 'missing']):
            with self.subTest(arms=arms), self.assertRaises(ValueError):
                rs.collect(records(), arms=arms)

    def test_pressure_distinguishes_workers_away_from_shed(self):
        m = rs.pressure(rs.actor_input(frame(), 0))
        self.assertEqual((m['ready_units'], m['ready_excess']), (8, 3))
        self.assertEqual((m['carried_units'], m['total_inventory_excess']), (108, 103))
        self.assertEqual(m['ready_workers'], [0])

    def test_all_four_shed_access_tiles_count(self):
        for pos in ([4,4], [4,5], [5,4], [5,5]):
            f = frame(); f['observation']['farms'][0]['farmer'] = pos
            self.assertEqual(rs.pressure(rs.actor_input(f,0))['ready_workers'], [0])

    def test_away_load_alone_is_not_current_admission_pressure(self):
        f = frame(); f['observation']['farms'][0]['farmer'] = [0, 0]
        result = rs.pressure(rs.actor_input(f, 0))
        self.assertEqual(result['ready_excess'], 0)
        self.assertGreater(result['total_inventory_excess'], 0)

    def test_worker_inventory_alignment(self):
        f = frame(); f['observation']['private']['inventories'] = []
        with self.assertRaises(ValueError): rs.pressure(rs.actor_input(f, 0))

    def test_source_and_return_are_detached(self):
        data = records(); before = copy.deepcopy(data)
        cases, _ = rs.collect(data)
        cases[0]['inputs']['observation']['private']['shed']['WHEAT'] = 0
        self.assertEqual(data, before)

    def test_no_overwrite_and_separate_evaluation_file(self):
        with tempfile.TemporaryDirectory() as root:
            dest = Path(root)/'out'
            catalog = rs.export(records(), dest)
            with self.assertRaises(FileExistsError): rs.export(records(), dest)
            payload = rs.decode((dest/catalog['cases'][0]['input_file']).read_bytes())
            self.assertEqual(set(payload), {'observation', 'configuration'})
            sidecar = rs.decode((dest/'evaluation-only.json').read_bytes())
            self.assertEqual(sidecar[0]['scores'], [100,90])
            self.assertNotIn('scores', catalog['cases'][0])

    def test_wrong_hash_and_decompression_limit(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'data.xz'; path.write_bytes(lzma.compress(rs.encoded(records())))
            with self.assertRaises(ValueError): rs.read_archive(path)
            pin = rs.digest(path.read_bytes())
            self.assertEqual(rs.read_archive(path, expected_sha256=pin), records())
            with self.assertRaises(ValueError):
                rs.read_archive(path, expected_sha256=pin, max_decoded_bytes=5)

    def test_duplicate_keys_nonfinite_values_and_paths(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
            with self.subTest(text=text), self.assertRaises(ValueError): rs.decode(text)
        for name in ('../oops.json','dev/../oops.json','/dev/a.json','dev\\a.json'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                rs.collect({name: json.dumps(record())})

    def test_cli_missing_archive_is_an_explicit_error(self):
        run = subprocess.run([sys.executable, str(Path(rs.__file__)), '/not/an/archive.xz',
                              '/unused/destination'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn('Case intake:', run.stderr)

    @unittest.skipUnless(os.environ.get('OSPREY_RAW_ARCHIVE'), 'Set OSPREY_RAW_ARCHIVE for retained-game intake')
    def test_real_development_records_and_frame_hashes(self):
        data = rs.read_archive(Path(os.environ['OSPREY_RAW_ARCHIVE']))
        cases, rows = rs.collect(data)
        self.assertEqual((len(data), len(rows), len(cases)), (64, 32, 376))
        self.assertEqual(sum(len(c['references']) for c in cases), 736)
        self.assertEqual({ref['step'] for c in cases for ref in c['references']}, set(range(696,719)))
        for c in cases:
            self.assertEqual(c['input_sha256'], rs.digest(rs.encoded(c['inputs'])))
        pressure, _ = rs.collect(data, only_pressure=True)
        self.assertEqual(pressure, [])
        with self.assertRaises(ValueError): rs.collect(data, step=360)


if __name__ == '__main__':
    unittest.main()

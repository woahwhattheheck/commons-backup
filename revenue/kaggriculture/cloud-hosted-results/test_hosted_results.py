import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import hosted_results as h


def replay(eid=100, own=0, rewards=None, statuses=None):
    rewards = [10.0, 5.0] if rewards is None else rewards
    statuses = ['DONE', 'DONE'] if statuses is None else statuses
    names = ['TITAN', 'RIVAL'] if own == 0 else ['RIVAL', 'TITAN']
    final = [{'status': statuses[s], 'observation': {'farms': [{'money': rewards[0]}, {'money': rewards[1]}]}}
             for s in (0, 1)]
    return {'info': {'EpisodeId': eid, 'Agents': [{'Name': n} for n in names]},
            'statuses': statuses, 'rewards': rewards,
            'configuration': {'episodeSteps': 2, 'actTimeout': 1},
            'steps': [[{'status': 'ACTIVE'}, {'status': 'ACTIVE'}], final]}


def record(eid=100):
    r = h.replay_record(replay(eid), 'TITAN')
    r.update(submission_id=123, own_log={'present': False})
    return r


def metadata(records, kind='complete_submission_history'):
    base = datetime(2026, 9, 7, tzinfo=timezone.utc)
    return {'kind': kind, 'submission_id': 123, 'as_of': '2026-09-08T00:00:00Z',
            'source': 'test-fixture-not-provider-evidence',
            'episodes': [{'episode_id': r['episode_id'], 'own_seat': r['own_seat'],
                          'completed_at': (base + timedelta(minutes=i)).isoformat(),
                          'opponent_rating_pre': 1500+i} for i, r in enumerate(records)]}


class ReplayTests(unittest.TestCase):
    def test_win(self):
        self.assertEqual(h.replay_record(replay(), 'TITAN')['outcome'], 'WIN')

    def test_seat_one_not_seat_zero(self):
        r = h.replay_record(replay(own=1), 'TITAN')
        self.assertEqual((r['own_seat'], r['outcome'], r['margin']), (1, 'LOSS', -5))

    def test_tie(self):
        self.assertEqual(h.replay_record(replay(rewards=[2, 2]), 'TITAN')['outcome'], 'TIE')

    def test_missing_reward_is_unknown_not_zero(self):
        r = h.replay_record(replay(rewards=[None, 5]), 'TITAN')
        self.assertEqual(r['outcome'], 'UNKNOWN')
        self.assertIsNone(r['own_reward'])

    def test_nonfinite_reward_is_unknown(self):
        for value in (float('nan'), float('inf'), True):
            with self.subTest(value=value):
                self.assertEqual(h.replay_record(replay(rewards=[value, 5]), 'TITAN')['outcome'], 'UNKNOWN')

    def test_missing_agent_rejected(self):
        with self.assertRaises(h.InputError): h.replay_record(replay(), 'ABSENT')

    def test_ambiguous_agent_rejected(self):
        r = replay()
        r['info']['Agents'][1]['Name'] = 'TITAN'
        with self.assertRaises(h.InputError): h.replay_record(r, 'TITAN')

    def test_bool_episode_id_rejected(self):
        with self.assertRaises(h.InputError): h.replay_record(replay(eid=True), 'TITAN')

    def test_active_not_scored(self):
        r = h.replay_record(replay(statuses=['ACTIVE', 'DONE']), 'TITAN')
        self.assertFalse(r['terminal_observed'])
        self.assertEqual(r['outcome'], 'UNKNOWN')

    def test_unknown_status_not_terminal(self):
        self.assertFalse(h.replay_record(replay(statuses=['UNRECOGNIZED', 'DONE']), 'TITAN')['terminal_observed'])

    def test_early_runtime_error_preserved(self):
        r = replay(statuses=['ERROR', 'DONE'], rewards=[None, 5])
        r['configuration']['episodeSteps'] = 720
        result = h.replay_record(r, 'TITAN')
        self.assertTrue(result['terminal_observed'])
        self.assertTrue(result['own_runtime_fault_status_observed'])
        self.assertFalse(result['horizon_complete'])
        self.assertEqual(result['integrity_issues'], [])

    def test_done_truncation_detected(self):
        r = replay(); r['configuration']['episodeSteps'] = 720
        self.assertIn('state_count_not_expected_horizon', h.replay_record(r, 'TITAN')['integrity_issues'])

    def test_final_status_mismatch(self):
        r = replay(); r['steps'][-1][0]['status'] = 'ERROR'
        self.assertIn('seat_0_terminal_status_mismatch', h.replay_record(r, 'TITAN')['integrity_issues'])

    def test_money_mismatch(self):
        r = replay(); r['steps'][-1][0]['observation']['farms'][0]['money'] = 99
        self.assertIn('terminal_money_reward_mismatch', h.replay_record(r, 'TITAN')['integrity_issues'])

    def test_invalid_native_shape(self):
        for r in ([], {}, {'info': {}}, {'info': {'EpisodeId': 1, 'Agents': []}}):
            with self.subTest(value=r), self.assertRaises(h.InputError): h.replay_record(r, 'TITAN')


class LogTests(unittest.TestCase):
    def test_valid_log(self):
        r = h.summarize_log([[{'duration': .2, 'stdout': '', 'stderr': ''}]], 1, 1)
        self.assertTrue(r['matches_replay_action_rounds'])
        self.assertEqual(r['duration_s']['max'], .2)

    def test_missing_invalid_durations_not_fabricated(self):
        rows = [[{'duration': None}, {'duration': -1}, {'duration': float('nan')}, {'duration': True}]]
        r = h.summarize_log(rows, 1, 1)
        self.assertEqual(r['invalid_duration_records'], 4)
        self.assertIsNone(r['duration_s']['max'])

    def test_log_fault_text_count_not_error_claim(self):
        r = h.summarize_log([[{'duration': 1.1, 'stderr': 'diagnostic', 'stdout': 'text'}]], 1, 1)
        self.assertEqual(r['nonempty_stderr_records'], 1)
        self.assertEqual(r['nonempty_stdout_records'], 1)
        self.assertEqual(r['duration_above_configured_timeout'], 1)

    def test_round_mismatch_and_multiple_records(self):
        r = h.summarize_log([[{'duration': .1}, {'duration': .2}]], 2, 1)
        self.assertFalse(r['matches_replay_action_rounds'])
        self.assertFalse(r['exactly_one_record_each_round'])

    def test_bad_log_shape_rejected(self):
        with self.assertRaises(h.InputError): h.summarize_log([{'duration': .2}], 1, 1)


class CoverageTests(unittest.TestCase):
    def test_selected_never_recent_even_60_rows(self):
        rs = [record(i) for i in range(60)]
        coverage = h.apply_history(rs, metadata(rs, 'selected_development'), 123)
        self.assertFalse(h.rolling(rs, coverage, 20)['computed'])

    def test_latest_20_by_explicit_time_not_episode_id(self):
        rs = [record(1000-i) for i in range(60)]
        coverage = h.apply_history(rs, metadata(rs), 123)
        result = h.rolling(list(reversed(rs)), coverage, 20)
        self.assertTrue(result['computed'])
        self.assertEqual(result['episode_ids'], [1000-i for i in range(40, 60)])

    def test_exact_50(self):
        rs = [record(i) for i in range(50)]
        coverage = h.apply_history(rs, metadata(rs), 123)
        self.assertEqual(h.rolling(rs, coverage, 50)['summary']['episodes'], 50)

    def test_insufficient_episodes(self):
        rs = [record(i) for i in range(4)]
        coverage = h.apply_history(rs, metadata(rs), 123)
        self.assertEqual(h.rolling(rs, coverage, 20)['reason'], 'insufficient_episodes')

    def test_missing_dates(self):
        rs = [record(i) for i in range(20)]
        meta = metadata(rs); meta['episodes'][0]['completed_at'] = None
        coverage = h.apply_history(rs, meta, 123)
        self.assertEqual(h.rolling(rs, coverage, 20)['reason'], 'missing_authoritative_completion_timestamps')

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(h.InputError): h.parse_time('2026-09-08T01:00:00')

    def test_timezone_normalization(self):
        self.assertEqual(h.parse_time('2026-09-08T01:00:00+01:00'), h.parse_time('2026-09-08T00:00:00Z'))

    def test_wrong_submission_rejected(self):
        rs = [record()]
        with self.assertRaises(h.InputError): h.apply_history(rs, metadata(rs), 999)

    def test_wrong_seat_rejected(self):
        rs = [record()]; meta = metadata(rs); meta['episodes'][0]['own_seat'] = 1
        with self.assertRaises(h.InputError): h.apply_history(rs, meta, 123)

    def test_incomplete_metadata_set_rejected(self):
        rs = [record()]; meta = metadata(rs); meta['episodes'] = []
        with self.assertRaises(h.InputError): h.apply_history(rs, meta, 123)

    def test_duplicate_metadata_rejected(self):
        rs = [record()]; meta = metadata(rs); meta['episodes'] *= 2
        with self.assertRaises(h.InputError): h.apply_history(rs, meta, 123)

    def test_future_completion_rejected(self):
        rs = [record()]; meta = metadata(rs); meta['episodes'][0]['completed_at'] = '2027-01-01T00:00:00Z'
        with self.assertRaises(h.InputError): h.apply_history(rs, meta, 123)

    def test_nonfinite_rating_rejected(self):
        rs = [record()]; meta = metadata(rs); meta['episodes'][0]['opponent_rating_pre'] = float('nan')
        with self.assertRaises(h.InputError): h.apply_history(rs, meta, 123)

    def test_boundary_timestamp_tie_not_broken_by_id(self):
        rs = [record(i) for i in range(21)]; meta = metadata(rs)
        meta['episodes'][1]['completed_at'] = meta['episodes'][0]['completed_at']
        coverage = h.apply_history(rs, meta, 123)
        self.assertEqual(h.rolling(rs, coverage, 20)['reason'], 'completion_timestamp_tie_crosses_window_boundary')

    def test_missing_ratings_retains_denominator(self):
        rs = [record(i) for i in range(20)]; meta = metadata(rs)
        for row in meta['episodes']: row['opponent_rating_pre'] = None
        coverage = h.apply_history(rs, meta, 123)
        result = h.rolling(rs, coverage, 20)['summary']
        self.assertEqual(result['episodes'], 20)
        self.assertEqual(result['opponent_rating_pre']['n'], 0)

    def test_error_episode_not_dropped_from_recent_window(self):
        rs = [record(i) for i in range(20)]
        rs[0].update(outcome='UNKNOWN', own_reward=None, margin=None, own_runtime_fault_status_observed=True)
        coverage = h.apply_history(rs, metadata(rs), 123)
        result = h.rolling(rs, coverage, 20)['summary']
        self.assertEqual((result['episodes'], result['wins'], result['unknown_outcomes']), (20, 19, 1))
        self.assertEqual(result['wins_per_episode'], .95)
        self.assertEqual(result['resolved_outcome_win_rate'], 1)


class InputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self): self.tmp.cleanup()

    def make_json(self, name, data):
        path = self.root/name; path.write_text(json.dumps(data)); return path

    def test_duplicate_replay_counted_once(self):
        first = self.make_json('100.json', replay())
        second = self.make_json('100(1).json', replay())
        result = h.analyze([first, second], 'TITAN')
        self.assertEqual(result['sample_summary']['episodes'], 1)
        self.assertEqual(result['duplicates']['replays'], 1)

    def test_conflicting_duplicate_rejected(self):
        first = self.make_json('100.json', replay())
        second = self.make_json('100(1).json', replay(rewards=[20, 5]))
        with self.assertRaises(h.InputError): h.analyze([first, second], 'TITAN')

    def test_exact_own_log_only(self):
        rp = self.make_json('100.json', replay(own=1))
        lp = self.make_json('100-0.json', [[{'duration': .2}]])
        result = h.analyze([rp, lp], 'TITAN')
        self.assertFalse(result['episodes'][0]['own_log']['present'])
        self.assertEqual(result['unmatched_log_keys'], [[100, 0]])

    def test_copied_filename_log_recognized(self):
        rp = self.make_json('100.json', replay())
        lp = self.make_json('100-0(1).json', [[{'duration': .2}]])
        self.assertTrue(h.analyze([rp, lp], 'TITAN')['episodes'][0]['own_log']['present'])

    def test_manifest_hash_mismatch_rejected(self):
        path = self.root/'bad.zip'
        with zipfile.ZipFile(path, 'w') as z:
            raw = json.dumps(replay()).encode()
            z.writestr('originals/100.json', raw)
            z.writestr('MANIFEST.json', json.dumps({'files': [{'name': '100.json', 'bytes': len(raw), 'sha256': 'bad'}]}))
        with self.assertRaises(h.InputError): h.analyze([path], 'TITAN')

    def test_zip_traversal_name_rejected(self):
        path = self.root/'bad.zip'
        with zipfile.ZipFile(path, 'w') as z: z.writestr('../100.json', json.dumps(replay()))
        with self.assertRaises(h.InputError): h.analyze([path], 'TITAN')

    def test_unbound_submission_not_invented(self):
        path = self.make_json('100.json', replay())
        with self.assertRaises(h.InputError): h.analyze([path], 'TITAN', 123)

    def test_empty_input_rejected(self):
        with self.assertRaises(h.InputError): h.analyze([], 'TITAN')

    def test_cli_cannot_overwrite_input(self):
        path = self.make_json('100.json', replay()); before = path.read_bytes()
        result = subprocess.run([sys.executable, '-B', str(Path(h.__file__)), str(path), '--agent-name', 'TITAN', '--output', str(path)], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(path.read_bytes(), before)

    def test_cli_cannot_overwrite_metadata(self):
        path = self.make_json('100.json', replay())
        meta = self.make_json('history.json', metadata([record()])); before = meta.read_bytes()
        result = subprocess.run([sys.executable, '-B', str(Path(h.__file__)), str(path), '--agent-name', 'TITAN', '--history-metadata', str(meta), '--output', str(meta)], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(meta.read_bytes(), before)

    def test_cli_output_formats_must_be_distinct(self):
        path = self.make_json('100.json', replay()); output = self.root/'report.json'
        result = subprocess.run([sys.executable, '-B', str(Path(h.__file__)), str(path), '--agent-name', 'TITAN', '--output', str(output), '--markdown', str(output)], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())

    def test_atomic_output_does_not_mutate_hardlinked_input(self):
        import os
        path = self.make_json('100.json', replay()); before = path.read_bytes()
        output = self.root/'report.json'; os.link(path, output)
        result = subprocess.run([sys.executable, '-B', str(Path(h.__file__)), str(path), '--agent-name', 'TITAN', '--output', str(output)], capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(json.loads(output.read_text())['sample_summary']['episodes'], 1)

    def test_cli_invalid_input_exits_two(self):
        path = self.make_json('invalid.json', {})
        result = subprocess.run([sys.executable, '-B', str(Path(h.__file__)), str(path), '--agent-name', 'TITAN', '--output', str(self.root/'out.json')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.root/'out.json').exists())




class PublicationTextTests(unittest.TestCase):
    def test_report_does_not_invent_publication_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '100.json'
            path.write_text(json.dumps(replay()))
            text = h.markdown(h.analyze([path], 'TITAN'))
        self.assertNotIn('have not been published', text)
        self.assertIn('Publication status is recorded separately', text)


if __name__ == '__main__': unittest.main(verbosity=2)

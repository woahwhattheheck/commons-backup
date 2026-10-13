"""Behavioral and mutation tests; all records are fictional."""
from copy import deepcopy
import importlib.util
import itertools
import json
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('tern63f_recovery_lab', HERE / 'lab.py')
lab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab)


def examples():
    return lab.loads_strict((HERE / 'examples.json').read_text(encoding='utf-8'))


def packet(actions=None):
    return {'schema_version': 1, 'synthetic': True, 'scenarios': [
        {'id': 'TEST', 'title': 'Fictional test',
         'resources': [{'id': 'pool', 'initial': 2, 'capacity': 20}],
         'actions': actions or [{'at': 0, 'op': 'verify', 'label': 'final'}]}]}


def run(actions):
    return lab.run_packet(packet(actions))['results'][0]


def action(op, at=0, **kw):
    return dict(op=op, at=at, **kw)


class BehavioralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = lab.run_packet(examples())
        cls.by_id = {r['id']: r for r in cls.report['results']}

    def checkpoint(self, sid, label):
        return next(c for c in self.by_id[sid]['checkpoints'] if c['label'] == label)

    def test_all_six_scenarios_finish_with_model_invariants(self):
        self.assertEqual(len(self.by_id), 6)
        self.assertTrue(all(r['final']['all_model_invariants_hold'] for r in self.by_id.values()))

    def test_config_rollback_without_migrating_storage(self):
        bad = self.checkpoint('R63-CONFIG', 'incompatible_reader')
        self.assertFalse(bad['invariants']['service_readable'])
        self.assertIsNone(bad['observed']['fictional-pool'])
        good = self.by_id['R63-CONFIG']['final']
        self.assertEqual(good['layout'], 'v1')
        self.assertEqual(good['verified_recovery_minutes'], 3)

    def test_readability_does_not_establish_write_recovery(self):
        c = self.checkpoint('R63-SNAPSHOT', 'healthy_but_missing_writes')
        self.assertTrue(c['invariants']['service_readable'])
        self.assertEqual(c['observed']['fictional-pool'], 2)
        self.assertEqual(c['expected_from_accepted_log']['fictional-pool'], 7)
        self.assertEqual(c['unapplied_event_ids'], ['ESS-001', 'ESS-002'])
        self.assertIsNone(c['verified_recovery_minutes'])

    def test_snapshot_does_not_rewind_incident_or_accepted_log(self):
        c = self.by_id['R63-SNAPSHOT']['final']
        self.assertEqual(c['accepted_event_count'], 2)
        self.assertEqual(c['verified_recovery_minutes'], 4)
        self.assertEqual(c['observed']['fictional-pool'], 7)

    def test_old_worker_cannot_consume_new_payload(self):
        result = self.by_id['R63-FORWARD']
        delivery = next(x for x in result['history'] if x['op'] == 'deliver')
        self.assertEqual(delivery['deliveries'][0]['outcome'], 'blocked')
        c = self.checkpoint('R63-FORWARD', 'old_binary_is_not_data_rollback')
        self.assertFalse(c['invariants']['service_readable'])
        self.assertEqual(c['unapplied_event_ids'], ['RIS-001'])

    def test_forward_repair_preserves_new_event(self):
        c = self.by_id['R63-FORWARD']['final']
        self.assertEqual(c['observed']['fictional-pool'], 6)
        self.assertEqual(c['verified_recovery_minutes'], 6)

    def test_idempotent_then_nonidempotent_delivery(self):
        good = self.checkpoint('R63-REPLAY', 'duplicate_safely_skipped')
        bad = self.checkpoint('R63-REPLAY', 'healthy_but_double_applied')
        self.assertTrue(good['all_model_invariants_hold'])
        self.assertIsNone(good['verified_recovery_minutes'])  # no incident yet
        self.assertEqual(bad['multiply_applied_event_ids'], ['IAM-001'])
        self.assertEqual(bad['observed']['fictional-pool'], 6)
        self.assertTrue(bad['invariants']['service_readable'])
        self.assertFalse(bad['invariants']['applied_at_most_once'])

    def test_restored_dedup_record_and_replay_stay_consistent(self):
        c = self.by_id['R63-REPLAY']['final']
        self.assertEqual(c['application_counts'], {'IAM-001': 1})
        self.assertEqual(c['observed']['fictional-pool'], 4)

    def test_expand_does_not_make_old_worker_dual_write(self):
        c = self.checkpoint('R63-MIXED', 'split_views')
        self.assertTrue(c['invariants']['service_readable'])
        self.assertEqual(c['stored_rows']['fictional-pool'], {'units': 5, 'quantity': 2})
        self.assertFalse(c['invariants']['legacy_and_new_views_agree'])
        self.assertFalse(c['invariants']['balances_match_accepted_log'])

    def test_bridge_does_not_silently_choose_conflicting_field(self):
        c = self.checkpoint('R63-MIXED', 'bridge_refuses_conflicting_fields')
        self.assertFalse(c['invariants']['service_readable'])
        self.assertEqual(c['unapplied_event_ids'], ['MIX-002'])
        self.assertEqual(c['application_counts'], {'MIX-001': 1})

    def test_dual_rebuild_then_contract_preserves_all_allocations(self):
        c = self.by_id['R63-MIXED']['final']
        self.assertEqual(c['stored_rows'], {'fictional-pool': {'quantity': 6}})
        self.assertTrue(c['all_model_invariants_hold'])

    def test_net_zero_events_cannot_hide_missing_work(self):
        c = self.checkpoint('R63-NETZERO', 'totals_match_but_work_is_missing')
        self.assertTrue(c['invariants']['balances_match_accepted_log'])
        self.assertFalse(c['invariants']['accepted_events_accounted_for'])
        self.assertFalse(c['all_model_invariants_hold'])
        self.assertEqual(c['unapplied_event_ids'], ['NET-001', 'NET-002'])

    def test_capacity_violation_is_detected_after_duplicate_application(self):
        p = packet([action('submit', event_id='A', resource='pool', delta=10),
                    action('deliver', event_id='A'), action('deliver', event_id='A', idempotent=False),
                    action('verify', label='final')])
        c = lab.run_packet(p)['results'][0]['final']
        self.assertFalse(c['invariants']['capacity_valid'])

    def test_all_24_delivery_permutations_are_idempotent(self):
        for permutation in itertools.permutations(['A', 'A', 'B', 'B']):
            with self.subTest(order=permutation):
                actions = [action('expand'), action('runtime', reader='bridge', writer='bridge', worker='bridge'),
                           action('submit', event_id='A', resource='pool', delta=2),
                           action('submit', event_id='B', resource='pool', delta=3)]
                actions += [action('deliver', event_id=e) for e in permutation]
                actions += [action('verify', label='final')]
                c = run(actions)['final']
                self.assertEqual(c['observed'], {'pool': 7})
                self.assertEqual(c['application_counts'], {'A': 1, 'B': 1})
                self.assertTrue(c['all_model_invariants_hold'])

    def test_multiple_resources_are_not_conflated(self):
        p = packet([action('submit', event_id='A', resource='pool', delta=2), action('replay'), action('verify', label='final')])
        p['scenarios'][0]['resources'].append({'id': 'other', 'capacity': 50, 'initial': 8})
        c = lab.run_packet(p)['results'][0]['final']
        self.assertEqual(c['observed'], {'pool': 4, 'other': 8})

    def test_deterministic_and_does_not_mutate_inputs(self):
        p = examples()
        copy = deepcopy(p)
        first, second = lab.run_packet(p), lab.run_packet(p)
        self.assertEqual(first, second)
        self.assertEqual(p, copy)

    def test_input_digest_ignores_object_key_order_not_action_order(self):
        p = packet()
        reordered = json.loads(json.dumps(p, sort_keys=True))
        self.assertEqual(lab.run_packet(p)['input_sha256'], lab.run_packet(reordered)['input_sha256'])
        changed = deepcopy(p)
        changed['scenarios'][0]['title'] = 'Changed'
        self.assertNotEqual(lab.run_packet(p)['input_sha256'], lab.run_packet(changed)['input_sha256'])

    def test_no_incident_means_no_recovery_duration(self):
        self.assertIsNone(lab.run_packet(packet())['results'][0]['final']['verified_recovery_minutes'])

    def test_snapshot_can_be_restored_twice_without_alias_mutation(self):
        c = run([action('snapshot', name='S'), action('submit', event_id='A', resource='pool', delta=2),
                 action('deliver', event_id='A'), action('restore', name='S'), action('replay'),
                 action('restore', name='S'), action('verify', label='final')])['final']
        self.assertEqual(c['observed']['pool'], 2)
        self.assertEqual(c['unapplied_event_ids'], ['A'])

    def test_md_escapes_inert_labels(self):
        p = packet()
        p['scenarios'][0]['title'] = '<script>|[click](https://example.invalid)'
        markdown = lab.render_markdown(lab.run_packet(p))
        self.assertNotIn('<script>', markdown)
        self.assertNotIn('[click](', markdown)
        self.assertIn('&#124;', markdown)


class ValidationTests(unittest.TestCase):
    def invalid(self, mutate):
        p = packet()
        mutate(p)
        with self.assertRaises(lab.InputError):
            lab.run_packet(p)

    def test_very_large_integer_is_a_controlled_input_error(self):
        with self.assertRaises(lab.InputError):
            lab.loads_strict('{"x":' + '9' * 5000 + '}')

    def test_unpaired_surrogate_is_not_renderable_metadata(self):
        self.invalid(lambda p: p['scenarios'][0].update(title='bad' + chr(0xD800)))

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(lab.InputError):
            lab.loads_strict('{"x": 1, "x": 2}')

    def test_nonfinite_json_rejected(self):
        for token in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(token=token), self.assertRaises(lab.InputError):
                lab.loads_strict('{"x":' + token + '}')

    def test_booleans_are_not_version_or_capacity(self):
        self.invalid(lambda p: p.update(schema_version=True))
        self.invalid(lambda p: p['scenarios'][0]['resources'][0].update(capacity=True))

    def test_non_synthetic_rejected(self):
        for v in (False, 'true', 1, None):
            self.invalid(lambda p: p.update(synthetic=v))

    def test_unknown_fields_rejected(self):
        self.invalid(lambda p: p.update(university_ready=True))
        self.invalid(lambda p: p['scenarios'][0]['actions'][0].update(lable='misspelled'))

    def test_duplicate_scenario_and_resource_rejected(self):
        self.invalid(lambda p: p['scenarios'].append(deepcopy(p['scenarios'][0])))
        self.invalid(lambda p: p['scenarios'][0]['resources'].append(deepcopy(p['scenarios'][0]['resources'][0])))

    def test_backward_clock_and_duplicate_verification_label(self):
        for actions in (
            [action('verify', at=2, label='one'), action('verify', at=1, label='two')],
            [action('verify', label='one'), action('verify', label='one')],
        ):
            with self.assertRaises(lab.InputError): run(actions)

    def test_final_verification_required(self):
        with self.assertRaises(lab.InputError): run([action('expand')])

    def test_unknown_action_or_runtime_version(self):
        for a in (action('live_deploy'), action('runtime', reader='v3'), action('runtime'), action('runtime', reader=[])):
            with self.assertRaises(lab.InputError): run([a, action('verify', label='end')])

    def test_invalid_delta_or_idempotent_type(self):
        for delta in (True, 0, 1.5, '2'):
            with self.assertRaises(lab.InputError):
                run([action('submit', event_id='A', resource='pool', delta=delta), action('verify', label='end')])
        with self.assertRaises(lab.InputError): run([action('replay', idempotent='false'), action('verify', label='end')])

    def test_unknown_snapshot_and_duplicate_snapshot(self):
        for actions in ([action('restore', name='absent')], [action('snapshot', name='A'), action('snapshot', name='A')]):
            with self.assertRaises(lab.InputError): run(actions + [action('verify', label='end')])

    def test_unknown_event_and_resource(self):
        for a in (action('deliver', event_id='absent'), action('submit', event_id='A', resource='absent', delta=1)):
            with self.assertRaises(lab.InputError): run([a, action('verify', label='end')])

    def test_duplicate_accepted_event_rejected(self):
        a = action('submit', event_id='A', resource='pool', delta=1)
        with self.assertRaises(lab.InputError): run([a, deepcopy(a), action('verify', label='end')])

    def test_capacity_overflow_and_underflow_rejected_at_acceptance(self):
        for delta in (-3, 19):
            with self.assertRaises(lab.InputError):
                run([action('submit', event_id='A', resource='pool', delta=delta), action('verify', label='end')])

    def test_impossible_migration_phase_and_second_incident(self):
        for actions in ([action('contract')], [action('expand'), action('expand')],
                        [action('incident', note='one'), action('incident', note='two')]):
            with self.assertRaises(lab.InputError): run(actions + [action('verify', label='end')])

    def test_control_characters_and_oversize_input(self):
        self.invalid(lambda p: p['scenarios'][0].update(title='bad\nlabel'))
        with self.assertRaises(lab.InputError): lab.loads_strict(' ' * (lab.MAX_BYTES + 1))

    def test_cli_json_and_markdown(self):
        for fmt in ('json', 'markdown'):
            result = subprocess.run([sys.executable, str(HERE / 'lab.py'), str(HERE / 'examples.json'), '--format', fmt], capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            if fmt == 'json': self.assertEqual(len(json.loads(result.stdout)['results']), 6)
            else: self.assertIn('healthy_but_missing_writes'.replace('_', '&#95;'), result.stdout)

    def test_cli_invalid_path_is_error_not_partial_report(self):
        result = subprocess.run([sys.executable, str(HERE / 'lab.py'), str(HERE / 'does-not-exist.json')], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()

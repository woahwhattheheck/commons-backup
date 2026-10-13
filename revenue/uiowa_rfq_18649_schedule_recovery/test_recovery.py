"""Offline contract, precedence, load, recovery and export regressions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from engine import Edge, ROLES, Task, load_profile, number, role_values, schedule
from recovery import HERE, PAYMENTS, analyze, build_suite, export, validate_case, validate_plan


def inputs():
    return (json.loads((HERE/'staffing-source.json').read_text()),
            json.loads((HERE/'scenario-inputs.json').read_text()))


def roles(value):
    return dict.fromkeys(ROLES, value)


class PrecedenceTests(unittest.TestCase):
    def test_finish_start(self):
        s = schedule([Task('A', 3), Task('B', 2)], [Edge('A', 'B', lag=1)])
        self.assertEqual((s['tasks']['B']['start'], s['finish']), (4, 6))
        self.assertEqual(s['critical_tasks'], ['A', 'B'])

    def test_start_start_and_finish_finish(self):
        s = schedule([Task('A', 10, 5), Task('B', 4)],
                     [Edge('A', 'B', 'SS', 2), Edge('A', 'B', 'FF', 1)])
        self.assertEqual((s['tasks']['B']['start'], s['finish']), (12, 16))
        self.assertEqual(s['critical_edges'][0]['relation'], 'FF')

    def test_negative_ff_weight_is_not_a_negative_input_lag(self):
        s = schedule([Task('A', 2), Task('B', 10)], [Edge('A', 'B', 'FF')])
        self.assertEqual(s['tasks']['B']['start'], 0)
        self.assertEqual(s['tasks']['A']['float_days'], 8)

    def test_branch_float(self):
        s = schedule([Task('A', 5), Task('B', 2), Task('C', 1)],
                     [Edge('A', 'C'), Edge('B', 'C')])
        self.assertEqual(s['tasks']['B']['float_days'], 3)
        self.assertEqual(set(s['critical_tasks']), {'A', 'C'})

    def test_multiple_critical_paths_are_retained(self):
        s = schedule([Task('A', 5), Task('B', 5), Task('C', 0)],
                     [Edge('A', 'C'), Edge('B', 'C')])
        self.assertEqual(len(s['critical_edges']), 2)
        self.assertEqual(s['driving_chain'], ['A', 'C'])

    def test_release_can_drive_final_date(self):
        s = schedule([Task('A', 2), Task('B', 1, 10)], [Edge('A', 'B')])
        self.assertEqual(s['finish'], 11)
        self.assertEqual(s['driving_chain'], ['B'])
        self.assertEqual(s['tasks']['A']['float_days'], 8)

    def test_unknown_release_propagates_only_to_descendants(self):
        s = schedule([Task('A', 2, None), Task('B', 3), Task('C', 4)], [Edge('A', 'B')])
        self.assertIsNone(s['finish'])
        self.assertEqual(s['finish_lower_bound'], 4)
        self.assertEqual(s['tasks']['B']['unknown_inputs'], ['A'])
        self.assertEqual(s['tasks']['C']['finish'], 4)
        self.assertIsNone(s['critical_tasks'])

    def test_zero_is_a_known_release(self):
        self.assertEqual(schedule([Task('A', 0, 0)], [])['finish'], 0)

    def test_order_independent_dates_and_float(self):
        tasks = [Task('A', 5), Task('B', 3), Task('C', 4), Task('D', 1)]
        edges = [Edge('A', 'C', 'SS', 1), Edge('B', 'C'), Edge('C', 'D')]
        reference = schedule(tasks, edges)
        rng = random.Random(134)
        for _ in range(20):
            rng.shuffle(tasks); rng.shuffle(edges)
            actual = schedule(tasks, edges)
            self.assertEqual(actual['tasks'], reference['tasks'])
            self.assertEqual(actual['critical_tasks'], reference['critical_tasks'])

    def test_cycles_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cycle'):
            schedule([Task('A', 1), Task('B', 1)], [Edge('A', 'B'), Edge('B', 'A')])

    def test_invalid_dependencies(self):
        variants = [[Edge('A', 'MISSING')], [Edge('A', 'A')], [Edge('A', 'B', 'SF')],
                    [Edge('A', 'B', lag=-1)], [Edge('A', 'B'), Edge('A', 'B')]]
        for edges in variants:
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                schedule([Task('A', 1), Task('B', 1)], edges)

    def test_invalid_numeric_inputs(self):
        for value in [True, False, -1, float('nan'), float('inf'), '3', None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                number(value, 'value')
        for value in [True, -1, float('nan'), float('inf')]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                schedule([Task('A', value)], [])

    def test_duplicate_empty_and_horizon_limits(self):
        for tasks in [[], [Task('A', 1), Task('A', 2)], [Task('', 1)],
                      [Task('A', 1, 10001)], [Task(str(i), 1) for i in range(501)]]:
            with self.subTest(count=len(tasks)), self.assertRaises(ValueError):
                schedule(tasks, [])

    def test_role_schema_and_unknown_rate(self):
        self.assertIsNone(role_values(roles(None), 'rates', nullable=True)['Clark'])
        for values in [{}, {'Clark': 2}, dict(roles(1), other=2), roles(None)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                role_values(values, 'hours')

    def test_fractional_interval_conserves_effort(self):
        s = schedule([Task('A', 2.5, 4)], [])
        p = load_profile(s['tasks'], {'A': roles(10)}, roles(50))
        self.assertEqual([w['hours']['Clark'] for w in p['weekly']], [4, 6])
        self.assertEqual(p['peak_hours_per_day']['Clark'], 4)

    def test_capacity_is_interval_based_not_only_weekly(self):
        s = schedule([Task('A', 1)], [])
        p = load_profile(s['tasks'], {'A': roles(20)}, roles(40))
        self.assertEqual(p['weekly'][0]['hours']['Clark'], 20)
        self.assertEqual(len(p['overloads']), 3)
        self.assertFalse(p['resource_leveled'])
        self.assertFalse(p['availability_confirmed'])

    def test_zero_duration_effort_rejected(self):
        s = schedule([Task('A', 0)], [])
        with self.assertRaises(ValueError):
            load_profile(s['tasks'], {'A': roles(1)}, roles(40))


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.config = inputs()
        cls.results = build_suite(cls.source, cls.config)
        cls.by_key = {(r['target_weeks'], r['id']): r for r in cls.results}

    def result(self, weeks, name):
        return self.by_key[weeks, name]

    def test_sixteen_explicit_cases(self):
        self.assertEqual(len(self.results), 16)

    def test_native_baseline_windows_and_hours_roundtrip(self):
        for plan in self.source['plans']:
            baseline = self.result(plan['target_weeks'], 'baseline')
            self.assertEqual(baseline['total_hours'], plan['totals'])
            for task in plan['tasks']:
                row = baseline['schedule']['tasks'][task['id']]
                self.assertEqual(row['start'], (task['start_week']-1)*5)
                self.assertEqual(row['finish'], task['end_week']*5)
                self.assertEqual(baseline['hours'][task['id']], task['hours'])

    def test_baseline_weekly_load_reconstructed_from_native_tasks(self):
        for plan in self.source['plans']:
            baseline = self.result(plan['target_weeks'], 'baseline')
            for w in baseline['capacity']['weekly']:
                for role in ROLES:
                    native = sum(t['hours'][role]/(t['end_week']-t['start_week']+1)
                                 for t in plan['tasks'] if t['start_week'] <= w['week'] <= t['end_week'])
                    self.assertAlmostEqual(w['hours'][role], native)

    def test_all_precedence_constraints_hold(self):
        for r in self.results:
            rows = r['schedule']['tasks']
            for edge in r['dependencies']:
                a, b = rows[edge['from']], rows[edge['to']]
                if a['start'] is None or b['start'] is None:
                    continue
                left = b['finish'] if edge['relation'] == 'FF' else b['start']
                right = a['start'] if edge['relation'] == 'SS' else a['finish']
                self.assertGreaterEqual(left+1e-8, right+edge['lag'])

    def test_critical_members_have_zero_float(self):
        for r in self.results:
            for key in r['schedule']['critical_tasks'] or []:
                self.assertAlmostEqual(r['schedule']['tasks'][key]['float_days'], 0)

    def test_delayed_comments_do_not_shift_qualifying_draft(self):
        for weeks in (6, 8):
            baseline, late = self.result(weeks, 'baseline'), self.result(weeks, 'delayed_comments')
            self.assertEqual(late['milestones'][1]['artifact_readiness_day'], baseline['milestones'][1]['artifact_readiness_day'])
            self.assertEqual(late['vs_baseline']['finish_shift_days'], 10)
            self.assertIn('A10', late['vs_baseline']['unchanged_tasks'])

    def test_comment_wait_is_relative_after_late_reviews(self):
        case = dict(self.config['scenarios'][1], comment_delay_days=10)
        for plan in self.source['plans']:
            r = analyze(plan, case, self.config['rates_usd_per_hour'])
            self.assertEqual(r['schedule']['finish'], plan['target_weeks']*5+20)
            rows = r['schedule']['tasks']
            self.assertEqual(rows['COMMENTS']['finish'], max(rows['A12']['finish'], rows['A13']['finish'])+10)

    def test_partial_evidence_does_not_freeze_independent_work(self):
        for weeks in (6, 8):
            r = self.result(weeks, 'partial_evidence')
            self.assertIn('A03', r['vs_baseline']['unchanged_tasks'])
            self.assertIn('A10', r['vs_baseline']['unchanged_tasks'])
            self.assertEqual(r['vs_baseline']['finish_shift_days'], 10)

    def test_recovery_retains_post_delivery_reconciliation(self):
        for weeks in (6, 8):
            r = self.result(weeks, 'recover_evidence'); rows = r['schedule']['tasks']
            self.assertGreaterEqual(rows['A08']['finish'], rows['EVIDENCE']['finish']+2)
        self.assertEqual(self.result(6, 'recover_evidence')['schedule']['finish'], 32)
        self.assertEqual(self.result(8, 'recover_evidence')['schedule']['finish'], 40)

    def test_provisional_synthesis_cannot_close_before_matrix(self):
        for weeks in (6, 8):
            r = self.result(weeks, 'recover_interviews'); rows = r['schedule']['tasks']
            self.assertGreaterEqual(rows['A09']['finish'], rows['A08']['finish'])
            self.assertEqual(r['recovery_days_vs_parent'], 5)

    def test_review_surge_retains_original_effort_and_exposes_overload(self):
        for weeks in (6, 8):
            late, recovery = self.result(weeks, 'delayed_comments'), self.result(weeks, 'recover_comments')
            self.assertEqual(recovery['hours']['A14'], late['hours']['A14'])
            self.assertEqual(recovery['hours']['A15'], late['hours']['A15'])
            self.assertEqual(recovery['recovery_days_vs_parent'], 2)
            self.assertTrue(recovery['capacity']['overloads'])
            self.assertEqual(recovery['schedule']['tasks']['A14']['duration'], 3)

    def test_eight_week_baseline_has_no_modeled_capacity_overload(self):
        self.assertFalse(self.result(8, 'baseline')['capacity']['overloads'])
        self.assertTrue(self.result(8, 'recover_interviews')['capacity']['overloads'])

    def test_unknown_evidence_preserves_unknown_finish_and_cost(self):
        for weeks in (6, 8):
            r = self.result(weeks, 'unknown_evidence')
            self.assertIsNone(r['schedule']['finish'])
            self.assertEqual(r['total_hours'], roles(None))
            self.assertEqual(r['labor_cost_usd_by_role'], roles(None))
            self.assertGreater(r['known_noncoordination_hours']['TJLabs'], 0)
            self.assertIn('A16', r['capacity']['unscheduled_tasks'])
            self.assertIsNotNone(r['schedule']['tasks']['A10']['finish'])

    def test_unknown_interviews_and_comments(self):
        for field in ('interview_delay_days', 'comment_delay_days'):
            case = dict(self.config['scenarios'][0], **{field: None})
            for plan in self.source['plans']:
                r = analyze(plan, case, self.config['rates_usd_per_hour'])
                self.assertIsNone(r['schedule']['finish'])
                if field == 'comment_delay_days':
                    self.assertIsNotNone(r['schedule']['tasks']['DRAFT']['finish'])

    def test_proposed_payment_triggers_never_become_earned_or_paid(self):
        for r in self.results:
            self.assertEqual(sum(m['proposed_amount_usd'] for m in r['milestones']), 24000)
            self.assertEqual([m['trigger'] for m in r['milestones']], [p[2] for p in PAYMENTS])
            for m in r['milestones']:
                self.assertFalse(m['invoice_earned']); self.assertFalse(m['paid'])
                self.assertIsNone(m['actual_trigger_day'])
                self.assertEqual(m['trigger_status'], 'NOT_VERIFIED')
            self.assertFalse(r['scheduling_authority'])

    def test_unpriced_role_is_not_free(self):
        for r in self.results:
            self.assertIn('University', r['unpriced_roles'])
            self.assertIsNone(r['labor_cost_usd_by_role']['University'])
            self.assertIsNone(r['vs_baseline']['extra_labor_cost_usd_by_role']['University'])

    def test_coordination_extension_and_explicit_rework_reconcile(self):
        r = self.result(6, 'late_interviews')
        self.assertAlmostEqual(r['vs_baseline']['extra_hours_by_role']['TJLabs'], 8)
        self.assertAlmostEqual(r['vs_baseline']['extra_labor_cost_usd_by_role']['TJLabs'], 640)
        for result in self.results:
            if result['schedule']['finish'] is not None:
                for role in ROLES:
                    self.assertAlmostEqual(sum(w['hours'][role] for w in result['capacity']['weekly']), result['total_hours'][role])

    def test_inputs_are_not_mutated(self):
        source, config = inputs(); before = copy.deepcopy((source, config))
        build_suite(source, config)
        self.assertEqual((source, config), before)

    def test_native_array_input_is_supported(self):
        self.assertEqual(build_suite(self.source['plans'], self.config), self.results)

    def test_invalid_source_shapes_are_rejected(self):
        for field, value in [('target_weeks', True), ('status', 'LIVE'), ('scheduling_authority', True), ('tasks', [])]:
            plan = copy.deepcopy(self.source['plans'][0]); plan[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): validate_plan(plan)
        plan = copy.deepcopy(self.source['plans'][0]); plan['totals']['TJLabs'] += 1
        with self.assertRaisesRegex(ValueError, 'reconcile'): validate_plan(plan)

    def test_double_delay_and_coordination_drift_rejected(self):
        plan = copy.deepcopy(self.source['plans'][0]); plan['assumptions']['evidence_delay_weeks'] = 1
        with self.assertRaisesRegex(ValueError, 'undelayed'): validate_plan(plan)
        plan = copy.deepcopy(self.source['plans'][0]); plan['tasks'][-1]['start_week'] = 2
        with self.assertRaisesRegex(ValueError, 'entire'): validate_plan(plan)

    def test_changed_native_windows_require_explicit_adapter_reconciliation(self):
        source, config = inputs()
        for row in source['plans'][0]['tasks']:
            if row['id'] == 'A15': row['start_week'] = 1
        with self.assertRaisesRegex(ValueError, 'incompatible'): build_suite(source, config)

    def test_bad_scenarios_are_rejected(self):
        for field, value in [('id', ''), ('interview_delay_days', True), ('evidence_delay_days', -1),
                             ('comment_delay_days', float('inf')), ('extra_hours', {'MISSING': roles(1)}),
                             ('recovery', 'invented'), ('compared_to', [])]:
            case = copy.deepcopy(self.config['scenarios'][0]); case[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): validate_case(case)
        case = dict(self.config['scenarios'][0], surprise=1)
        with self.assertRaises(ValueError): validate_case(case)

    def test_recovery_conditions_and_positive_windows_required(self):
        for index, field in [(5, 'post_delivery_days'), (6, 'recovery_window_days')]:
            for value in [0, -1, None, True]:
                case = copy.deepcopy(self.config['scenarios'][index]); case[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError): validate_case(case)
        case = dict(self.config['scenarios'][5], requires=[])
        with self.assertRaises(ValueError): validate_case(case)

    def test_suite_identity_and_baseline_checks(self):
        source, config = inputs(); config['scenarios'][1]['id'] = 'baseline'
        with self.assertRaises(ValueError): build_suite(source, config)
        source, config = inputs(); config['scenarios'][0]['comment_delay_days'] = 1
        with self.assertRaises(ValueError): build_suite(source, config)
        source, config = inputs(); config['scenarios'][1]['compared_to'] = 'missing'
        with self.assertRaises(ValueError): build_suite(source, config)
        source, config = inputs(); config['assumption_note'] = ''
        with self.assertRaises(ValueError): build_suite(source, config)

    def test_exports_reproduce_exactly(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/'a', Path(folder)/'b'
            export(self.results, a); export(self.results, b)
            self.assertEqual(sorted(p.name for p in a.iterdir()), ['WORKED_CALENDARS.md', 'calendar-6-week.md', 'calendar-8-week.md', 'scenarios.json', 'summary.csv'])
            for file in a.iterdir(): self.assertEqual(file.read_bytes(), (b/file.name).read_bytes())
            self.assertIn('UNKNOWN', (a/'summary.csv').read_text())
            self.assertIn('No / No / No', (a/'calendar-6-week.md').read_text())

    def test_cli_and_optimized_cli_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder)/'normal', Path(folder)/'optimized'
            for mode, out in [([], a), (['-O'], b)]:
                result = subprocess.run([sys.executable, *mode, str(HERE/'recovery.py'), '--out', str(out)],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('16 hypothetical', result.stdout)
            for file in a.iterdir(): self.assertEqual(file.read_bytes(), (b/file.name).read_bytes())

    def test_invalid_cli_does_not_create_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            source, out = Path(folder)/'bad.json', Path(folder)/'out'
            source.write_text('{broken')
            result = subprocess.run([sys.executable, str(HERE/'recovery.py'), '--staffing-plans', str(source), '--out', str(out)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 2)
            self.assertIn('Invalid planning input', result.stderr)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()

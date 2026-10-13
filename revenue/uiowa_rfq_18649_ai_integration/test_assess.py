"""Regression coverage for arithmetic, missing evidence, semantics and file interchange."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assess
from example_cases import doc


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.data = copy.deepcopy(doc)
        self.a = self.data['cases'][0]['alternatives'][1]
        self.req = self.data['cases'][0]['requirements']

    def out(self):
        return assess.assess(self.data)['cases'][0]['alternatives'][1]

    def test_three_cases_nine_alternatives(self):
        result = assess.assess(self.data)
        self.assertEqual(len(result['cases']), 3)
        self.assertEqual(sum(len(c['alternatives']) for c in result['cases']), 9)
        self.assertTrue(result['synthetic'])

    def test_supported_is_not_production_readiness(self):
        self.assertEqual(self.out()['status'], 'supported_by_inputs')
        self.assertIn('not production readiness', assess.assess(self.data)['caveat'])

    def test_acknowledgement_and_completion_are_distinct(self):
        result = self.out()
        self.assertEqual(result['latency_ms']['high'], 250)
        self.assertEqual(result['completion_ms']['high'], 316250)
        self.assertGreater(result['completion_ms']['low'], result['latency_ms']['high'])

    def test_synchronous_completion_uses_response_path(self):
        result = assess.assess(self.data)['cases'][0]['alternatives'][0]
        self.assertEqual(result['latency_ms'], result['completion_ms'])

    def test_unknown_latency_is_not_zero(self):
        self.a['response_stages'][0]['ms']['high'] = None
        result = self.out()
        self.assertIsNone(result['latency_ms']['high'])
        self.assertEqual(result['checks']['response_latency'], 'unknown')
        self.assertEqual(result['latency_ms']['known_low_subtotal'], 90)

    def test_partial_interval_never_passes_budget(self):
        self.a['response_stages'][0]['ms']['low'] = None
        self.assertEqual(self.out()['checks']['response_latency'], 'unknown')

    def test_boundary_and_overlap(self):
        self.req['response_budget_ms'] = 250
        self.assertEqual(self.out()['checks']['response_latency'], 'supported_by_inputs')
        self.req['response_budget_ms'] = 100
        self.assertEqual(self.out()['checks']['response_latency'], 'conditional')
        self.req['response_budget_ms'] = 80
        self.assertEqual(self.out()['checks']['response_latency'], 'conflict')

    def test_percentiles_cannot_be_summed(self):
        self.a['latency_basis'] = 'p95'
        with self.assertRaises(assess.InputError): self.out()

    def test_frechet_bounds_not_implicit_independence(self):
        result = self.out()['response_availability']
        self.assertAlmostEqual(result['lower'], .9995)
        self.assertAlmostEqual(result['upper'], .9997)
        self.assertIsNone(result['independent_estimate'])

    def test_explicit_independence_is_only_an_estimate(self):
        self.a['independence_assumed'] = True
        result = self.out()['response_availability']
        self.assertAlmostEqual(result['independent_estimate'], .9998 * .9997)
        self.assertAlmostEqual(result['lower'], .9995)
        self.assertIn('not AI completion', result['scope'])

    def test_mismatched_availability_windows_unknown(self):
        self.a['response_dependencies'][0]['window'] = 'other-window'
        result = self.out()
        self.assertEqual(result['checks']['response_availability'], 'unknown')
        self.assertIsNone(result['response_availability']['upper'])

    def test_missing_window_unknown(self):
        self.req['availability_window'] = None
        self.assertEqual(self.out()['checks']['response_availability'], 'unknown')

    def test_unknown_dependency_is_not_perfect_uptime(self):
        self.a['response_dependencies'][0]['availability'] = None
        self.assertEqual(self.out()['checks']['response_availability'], 'unknown')
        self.assertIsNone(self.out()['response_availability']['lower'])

    def test_known_dependency_can_prove_conflict_despite_unknown(self):
        self.a['response_dependencies'][0]['availability'] = None
        self.a['response_dependencies'][1]['availability'] = .9
        self.assertEqual(self.out()['checks']['response_availability'], 'conflict')

    def test_availability_target_inside_bounds_conditional(self):
        self.req['response_availability_target'] = .9996
        self.assertEqual(self.out()['checks']['response_availability'], 'conditional')

    def test_joint_probability_bounds_for_random_inputs(self):
        random.seed(80)
        for count in range(1, 12):
            ps = [random.random() for _ in range(count)]
            result = assess.availability([{'name':str(i),'availability':p,'window':'w'} for i,p in enumerate(ps)], True, 'w')
            self.assertLessEqual(result['lower'], result['independent_estimate'] + 1e-12)
            self.assertLessEqual(result['independent_estimate'], result['upper'] + 1e-12)

    def test_empty_dependencies_not_perfect_availability(self):
        self.a['response_dependencies'] = []
        with self.assertRaises(assess.InputError): self.out()

    def test_one_time_and_recurring_effort_not_added(self):
        result = self.out()
        self.assertEqual(result['integration_hours']['low'], 96)
        self.assertEqual(result['maintenance_hours_per_month']['low'], 16)
        self.assertEqual(result['migration_hours']['low'], 36)

    def test_missing_effort_and_capacity_stay_unknown(self):
        self.a['maintenance_tasks'][0]['hours_per_month']['high'] = None
        self.assertEqual(self.out()['checks']['maintenance_capacity'], 'unknown')
        self.assertIsNone(self.out()['maintenance_hours_per_month']['low'])

    def test_missing_owner_and_task_owner(self):
        self.a['owners']['support'] = None
        self.a['integration_tasks'][0]['owner_role'] = None
        result = self.out()
        self.assertEqual(result['checks']['ownership'], 'unknown')
        self.assertEqual(result['missing_owners'], ['support'])
        self.assertTrue(result['unowned_tasks'])

    def test_unknown_data_zone_and_retention(self):
        self.a['data_flows'][0]['zone'] = None
        self.a['data_flows'][0]['retention_days'] = None
        result = self.out()
        self.assertEqual(result['checks']['data_zone:A1'], 'unknown')
        self.assertEqual(result['checks']['retention:A1'], 'unknown')

    def test_explicit_data_boundary_conflict(self):
        self.a['data_flows'][0]['zone'] = 'outside'
        self.a['data_flows'][0]['retention_days'] = 31
        result = self.out()
        self.assertEqual(result['checks']['data_zone:A1'], 'conflict')
        self.assertEqual(result['checks']['retention:A1'], 'conflict')

    def test_missing_capability_explained(self):
        self.req['required_capabilities'].append('source_citations')
        result = self.out()
        self.assertEqual(result['missing_capabilities'], ['source_citations'])
        self.assertEqual(result['checks']['capability_match'], 'conflict')

    def test_asserted_portability_is_conditional(self):
        self.a['portability']['adapter_swap']['state'] = 'asserted'
        self.assertEqual(self.out()['checks']['portability:adapter_swap'], 'conditional')

    def test_demonstrated_requires_retained_reference(self):
        self.a['portability']['adapter_swap']['evidence_refs'] = []
        with self.assertRaises(assess.InputError): self.out()

    def test_empty_evidence_is_not_supported(self):
        self.a['evidence_refs'] = []
        self.assertEqual(self.out()['checks']['evidence_coverage'], 'unknown')

    def test_references_must_resolve(self):
        self.a['evidence_refs'].append('MISSING')
        with self.assertRaises(assess.InputError): self.out()

    def test_fallback_claim_without_test_is_conditional(self):
        self.a['degraded_mode']['tested'] = False
        self.assertEqual(self.out()['checks']['degraded_mode'], 'conditional')

    def test_manual_queue_does_not_prove_core_continuity(self):
        self.a['degraded_mode']['behavior'] = 'manual_queue'
        self.assertEqual(self.out()['checks']['degraded_mode'], 'conditional')

    def test_fallback_test_requires_reference(self):
        self.a['degraded_mode']['evidence_refs'] = []
        with self.assertRaises(assess.InputError): self.out()

    def test_cannot_relabel_synthetic_as_real(self):
        self.data['synthetic'] = False
        with self.assertRaises(assess.InputError): self.out()

    def test_invalid_numeric_inputs(self):
        for value in [True, -1, float('inf'), float('nan'), '3', 10**400]:
            with self.subTest(value=str(value)[:20]):
                with self.assertRaises(assess.InputError): assess.number(value,'x')

    def test_aggregate_overflow_is_an_input_error(self):
        with self.assertRaises(assess.InputError):
            assess.total([{'name':str(i),'hours':{'low':1e308,'high':1e308}} for i in range(3)], 'hours', 'tasks')

    def test_malformed_enum_types_are_input_errors(self):
        for key in ['pattern', 'latency_basis']:
            data = copy.deepcopy(self.data)
            data['cases'][0]['alternatives'][0][key] = []
            with self.assertRaises(assess.InputError): assess.assess(data)
        self.a['portability']['adapter_swap']['state'] = []
        with self.assertRaises(assess.InputError): self.out()

    def test_invalid_ranges(self):
        for value in [{'low':3,'high':1}, {'low':1}, {'low':0,'high':1,'extra':2}]:
            with self.assertRaises(assess.InputError): assess.interval(value,'x')

    def test_duplicate_ids_rejected(self):
        self.data['cases'].append(copy.deepcopy(self.data['cases'][0]))
        with self.assertRaises(assess.InputError): assess.assess(self.data)

    def test_duplicate_item_and_flow_ids(self):
        self.a['data_flows'].append(copy.deepcopy(self.a['data_flows'][0]))
        with self.assertRaises(assess.InputError): self.out()
        with self.assertRaises(assess.InputError):
            assess.total([{'name':'x','ms':{'low':1,'high':2}}]*2,'ms','stages')

    def test_json_duplicates_nonfinite_and_bad_bytes(self):
        for raw in [b'{"a":1,"a":2}',b'{"n":NaN}',b'{"n":Infinity}',b'\xff',b'{']:
            with self.assertRaises(assess.InputError): assess.load(raw)

    def test_csv_and_markdown_preserve_unicode_and_unknowns(self):
        self.data['cases'][0]['id'] = '=SUM(1,2)'
        self.data['cases'][0]['title'] = 'Δ | long\nreview <tag>'
        report = assess.assess(self.data)
        rows = list(csv.DictReader(io.StringIO(assess.csv_text(report))))
        self.assertTrue(rows[0]['case_id'].startswith("'="))
        rendered = assess.markdown(report)
        self.assertIn('Δ \\| long / review &lt;tag&gt;', rendered)
        self.assertIn('UNKNOWN',rendered)
        self.assertIn('SYNTHETIC: TRUE',rendered)

    def test_cli_reproducible_and_source_bound(self):
        root = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp/'cases.json'
            source.write_text(json.dumps(self.data),encoding='utf-8')
            for name in ['first','second']:
                run = subprocess.run([sys.executable,str(root/'assess.py'),str(source),'--out',str(tmp/name)],capture_output=True,text=True)
                self.assertEqual(run.returncode,0,run.stderr)
            for name in ['assessment.json','assessment.md','checks.csv']:
                self.assertEqual((tmp/'first'/name).read_bytes(),(tmp/'second'/name).read_bytes())
            output=json.loads((tmp/'first'/'assessment.json').read_text())
            self.assertEqual(output['input_sha256'],hashlib.sha256(source.read_bytes()).hexdigest())

    def test_cli_bad_input_does_not_write_output(self):
        root=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp); source=tmp/'bad.json'; source.write_text('{')
            run=subprocess.run([sys.executable,str(root/'assess.py'),str(source),'--out',str(tmp/'out')],capture_output=True,text=True)
            self.assertEqual(run.returncode,2)
            self.assertFalse((tmp/'out').exists())

    def test_cli_cannot_overwrite_input(self):
        root=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp); source=tmp/'assessment.json'; original=json.dumps(self.data); source.write_text(original)
            run=subprocess.run([sys.executable,str(root/'assess.py'),str(source),'--out',str(tmp)],capture_output=True,text=True)
            self.assertEqual(run.returncode,2)
            self.assertEqual(source.read_text(),original)


if __name__ == '__main__':
    unittest.main()

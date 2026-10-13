import contextlib
import copy
import csv
import hashlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

import lifecycle as l
from synthetic import history


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.data = history()

    def report(self):
        return l.analyze(self.data)

    def bad(self, contains=None):
        with self.assertRaises(l.ContractError) as error:
            self.report()
        if contains:
            self.assertIn(contains, str(error.exception))

    def art(self, ident):
        return next(a for a in self.data['artifacts'] if a['id'] == ident)

    def comparison(self, ident):
        return next(c for c in self.report()['comparisons'] if c['id'] == ident)

    def test_worked_story(self):
        r = self.report()
        self.assertEqual((len(r['timeline']), len(r['runs']), len(r['events'])), (4, 6, 4))
        self.assertEqual(r['provenance'], 'SYNTHETIC_SUPPLIED_OBSERVATIONS')
        self.assertEqual(r['authority'], 'DRAFT_ANALYSIS_ONLY')

    def test_missing_is_not_zero(self):
        c = self.comparison('regression')['metrics']['correctness']
        self.assertEqual(c['paired'], 3)
        self.assertEqual(c['excluded_case_ids'], ['c4'])
        self.assertEqual(c['coverage'], 'subset_only')
        self.assertAlmostEqual(c['delta'], -2/3, places=6)
        r = next(r for r in self.report()['runs'] if r['run_id'] == 'r2')
        self.assertEqual(r['metrics']['correctness']['missing'], 1)
        self.assertEqual(r['error_case_ids'], ['c4'])

    def test_repair_and_cost_tradeoff(self):
        c = self.comparison('repair')
        self.assertAlmostEqual(c['metrics']['correctness']['delta'], 2/3, places=6)
        self.assertEqual(c['metrics']['latency_ms']['delta'], 100)
        self.assertEqual(c['metrics']['latency_ms']['better_direction'], 'lower')
        self.assertIn('prompt', c['changed_components'])

    def test_changed_eval_incomparable(self):
        c = self.comparison('changed-evaluation')
        self.assertEqual(c['status'], 'incomparable')
        self.assertEqual(c['metrics'], {})

    def test_replays_compare_output_not_scores(self):
        a, b = self.report()['replays']
        self.assertEqual(a['status'], 'exact_on_recorded_cases')
        self.assertEqual(b['status'], 'different_recorded_outputs')
        self.assertEqual(b['mismatch_case_ids'], ['c2'])

    def test_duplicate_identifiers(self):
        for key in ('artifacts', 'cases', 'evaluation_sets', 'versions', 'runs', 'comparisons', 'replays', 'events'):
            with self.subTest(key=key):
                self.data = history()
                self.data[key].append(copy.deepcopy(self.data[key][0]))
                self.bad('duplicate')

    def test_duplicate_json_and_nonfinite(self):
        for text in ('{"a":1,"a":2}', '{"a": NaN}', '{"a": Infinity}'):
            with self.subTest(text=text), self.assertRaises(l.ContractError):
                l.load(text)

    def test_invalid_types_bounds_and_unknown_fields(self):
        for key, value in [('correctness', 1), ('completeness', True), ('usefulness', 1.1),
                           ('repair_minutes', -1), ('latency_ms', float('inf'))]:
            with self.subTest(key=key):
                self.data = history()
                self.data['runs'][0]['observations'][0][key] = value
                self.bad()
        self.data = history(); self.data['typo'] = 1; self.bad('unexpected')

    def test_digest_mismatch(self):
        self.art('prompt1')['text'] += '!'
        self.bad('digest mismatch')

    def test_inline_unretained_is_inconsistent(self):
        self.art('prompt1')['retained'] = False
        self.bad('retention')

    def test_wrong_artifact_kind_and_broken_reference(self):
        self.data['versions'][0]['components']['model'] = 'prompt1'
        self.bad('expected kind model')
        self.data = history(); self.data['events'][0]['evidence_refs'] = ['absent']; self.bad('unresolved')

    def test_manifest_binds_inputs_and_answers(self):
        a = self.art('expected1')
        a['text'] = 'A changed expected answer'
        a['sha256'] = hashlib.sha256(a['text'].encode()).hexdigest()
        self.bad('declared case manifest')

    def test_manifest_binds_protocol(self):
        self.data['evaluation_sets'][0]['protocol_id'] = 'different-protocol'
        self.bad('declared case manifest')

    def test_missing_definition_blocks_delta(self):
        self.art('rubric')['text'] = None
        c = self.comparison('regression')
        self.assertEqual(c['status'], 'incomparable')
        self.assertEqual(c['metrics'], {})

    def test_missing_case_bytes_blocks_delta(self):
        self.art('in2')['text'] = None
        self.assertEqual(self.comparison('regression')['status'], 'incomparable')

    def test_missing_metadata_not_success(self):
        v = self.report()['timeline'][-1]
        self.assertIn('support owner not recorded', v['reproduction_gaps'])
        self.assertIn('environment: not_retained', v['reproduction_gaps'])
        self.assertEqual(v['replay_ids'], [])

    def test_zero_is_observed(self):
        self.data['runs'][0]['observations'][0]['repair_minutes'] = 0
        c = self.comparison('regression')['metrics']['repair_minutes']
        self.assertEqual(c['paired'], 3)
        self.assertEqual(c['baseline_mean'], 1)

    def test_all_missing_is_null(self):
        for o in self.data['runs'][0]['observations']:
            o['repair_minutes'] = None
        c = self.comparison('regression')['metrics']['repair_minutes']
        self.assertEqual(c['paired'], 0)
        self.assertIsNone(c['delta'])
        self.assertIsNone(c['baseline_mean'])

    def test_absent_case_visible(self):
        self.data['runs'][0]['observations'].pop()
        r = next(r for r in self.report()['runs'] if r['run_id'] == 'r1')
        self.assertEqual(r['missing_case_ids'], ['c4'])
        self.assertEqual(self.report()['replays'][0]['status'], 'incomplete')

    def test_error_cannot_be_scored(self):
        self.data['runs'][0]['observations'][0]['error'] = 'timeout'
        self.bad('masquerade')

    def test_registered_output_not_demonstrated_replay(self):
        self.art('r1-repeat-o1')['text'] = None
        self.assertEqual(self.report()['replays'][0]['status'], 'incomplete')

    def test_naive_and_reverse_chronology(self):
        for value in ('2026-09-01T09:00:00', 'not-a-date', '2026-08-31T09:00:00Z'):
            with self.subTest(value=value):
                self.data = history(); self.data['runs'][0]['started_at'] = value; self.bad()
        self.data = history(); self.data['versions'][0]['parent_id'] = 'v4'; self.bad('parent')

    def test_timezone_normalization(self):
        self.data['runs'][0]['started_at'] = '2026-09-01T06:00:00-04:00'
        self.assertEqual(self.report()['runs'][0]['run_id'], 'r1')

    def test_explicit_comparison_not_latest_run(self):
        self.data['runs'].reverse()
        self.assertEqual(self.comparison('regression')['candidate_run'], 'r2')

    def test_cross_version_replay_rejected(self):
        self.data['replays'][0]['repeat_run'] = 'r2'
        self.bad('same version')

    def test_same_run_comparison_rejected(self):
        self.data['comparisons'][0]['candidate_run'] = 'r1'
        self.bad('distinct')

    def test_event_resolution_and_unsupported_closure(self):
        events = {e['id']: e for e in self.report()['events']}
        self.assertEqual(events['incident1']['resolution_event_id'], 'resolution1')
        self.assertEqual(events['incident2']['incident_state'], 'open')
        self.data['events'][2]['evidence_refs'] = []
        self.assertEqual(self.report()['events'][0]['incident_state'], 'resolution_claim_without_evidence')

    def test_event_must_bind_right_version(self):
        self.data['events'][0]['related_run_ids'] = ['r1']
        self.bad('mismatch')

    def test_duplicate_resolution_rejected(self):
        e = copy.deepcopy(self.data['events'][2]); e['id'] = 'resolution2'
        self.data['events'].append(e); self.bad('duplicate resolution')

    def test_table_escape_and_csv(self):
        self.data['versions'][0]['reason'] = '<script>|\nA & B'
        text = l.markdown(self.report())
        self.assertNotIn('<script>', text)
        self.assertIn('&lt;script&gt;&#124;', text)
        rows = list(csv.DictReader(io.StringIO(l.comparison_csv(self.report()))))
        self.assertEqual(len(rows), 11)
        self.assertEqual(next(r for r in rows if r['status'] == 'incomparable')['delta'], '')

    def test_collection_order_independent(self):
        expected = self.report()
        for key in ('artifacts', 'cases', 'evaluation_sets', 'versions', 'runs', 'comparisons', 'replays', 'events'):
            self.data[key].reverse()
        for v in self.data['versions']:
            v['components'] = dict(reversed(list(v['components'].items())))
        self.assertEqual(self.report(), expected)

    def test_unverified_real_metadata_label(self):
        self.data['synthetic'] = False
        self.assertIn('NOT_INDEPENDENTLY_VERIFIED', self.report()['provenance'])

    def test_cli_all_formats_and_schema(self):
        script = str(Path(l.__file__))
        for fmt in ('json', 'markdown', 'csv'):
            with self.subTest(fmt=fmt):
                p = subprocess.run([sys.executable, script, '-', '--format', fmt], input=json.dumps(self.data),
                                   capture_output=True, text=True, timeout=15)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertTrue(p.stdout)
        p = subprocess.run([sys.executable, script, '--schema'], capture_output=True, text=True, timeout=15)
        self.assertEqual(json.loads(p.stdout), l.SCHEMA)

    def test_cli_failure_does_not_emit_report(self):
        p = subprocess.run([sys.executable, str(Path(l.__file__)), '-'], input='{"schema_version": "1.0"}',
                           capture_output=True, text=True, timeout=15)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(p.stdout, '')
        self.assertIn('INVALID_INPUT', p.stderr)

    def test_checked_in_examples_current(self):
        root = Path(l.__file__).parent
        self.assertEqual(json.loads((root/'lifecycle.schema.json').read_text()), l.SCHEMA)
        self.assertEqual((root/'WORKED_EXAMPLE.md').read_text(), l.markdown(self.report()))


if __name__ == '__main__':
    unittest.main()

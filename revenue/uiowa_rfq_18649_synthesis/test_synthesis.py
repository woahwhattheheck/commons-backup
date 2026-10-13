"""Executable acceptance cases for UIOWA-028; all evidence is fictional."""
import copy
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

import synthesis as s

BASE = Path(__file__).resolve().parent


class SynthesisTests(unittest.TestCase):
    def setUp(self):
        self.packet = s.load_json((BASE / 'fixtures/synthetic.json').read_text())

    def themes(self, practice, packet=None):
        report = s.synthesize(packet or self.packet)
        return [t for t in report['themes'] if t['practice_key'] == practice]

    def test_shared_gap_reach_not_independence_and_dissent_survives(self):
        t, = self.themes('business-recovery-check')
        self.assertEqual(t['groups'], ['ESS', 'IAM', 'RIS'])
        self.assertEqual(t['declared_support_clusters'], 1)
        self.assertEqual(t['source_count'], 1)
        self.assertEqual(t['relationship'], 'inherited_dependency')
        self.assertEqual(t['status'], 'contested')
        self.assertEqual(t['recommendation_shape'], 'focused_follow_up')
        self.assertEqual(t['dissent_ids'], ['IAM-COUNTEREXAMPLE'])
        self.assertIn('IAM-COUNTEREXAMPLE', {x['source_id'] for x in t['sources']})

    def test_shared_strength_has_one_support_cluster(self):
        t, = self.themes('release-identity')
        self.assertEqual(t['relationship'], 'shared_capability')
        self.assertEqual(t['declared_support_clusters'], 1)
        self.assertEqual(len(t['finding_ids']), 3)
        self.assertEqual(t['coverage_scope'], 'sampled_all_three_groups')
        self.assertIn('no population prevalence', t['inference_limit'])

    def test_same_symptom_different_causes_remain_separate(self):
        themes = self.themes('delivery-wait')
        self.assertEqual(len(themes), 2)
        for t in themes:
            self.assertEqual(t['relationship'], 'local_exception')
            self.assertEqual(t['recommendation_shape'], 'group_specific_action')
            self.assertEqual(len(t['related_findings_outside_theme']), 1)

    def test_manual_and_automated_outcomes_compose_without_ranking(self):
        themes = self.themes('requirements-review')
        t = next(x for x in themes if x['relationship'] == 'repeated_local_practice')
        self.assertEqual(t['groups'], ['ESS', 'RIS'])
        self.assertEqual(t['groups_not_covered_by_this_theme'], ['IAM'])
        self.assertEqual(t['declared_support_clusters'], 2)
        self.assertNotIn('maturity', t)
        self.assertIn('Manual', t['findings'][0]['context'])
        self.assertIn('Automated', t['findings'][1]['context'])

    def test_unknown_is_not_gap(self):
        unknown = next(t for t in self.themes('requirements-review') if t['groups'] == ['IAM'])
        self.assertEqual(unknown['states'], ['unknown'])
        self.assertEqual(unknown['source_count'], 0)
        self.assertEqual(unknown['status'], 'unresolved')
        self.assertEqual(unknown['recommendation_shape'], 'focused_follow_up')

    def test_policy_and_inapplicable_remain_distinct(self):
        themes = self.themes('ai-summary-review')
        self.assertEqual(len(themes), 2)
        policy = next(t for t in themes if t['groups'] == ['ESS'])
        self.assertEqual(policy['basis'], 'reported_or_mixed')
        self.assertEqual(policy['status'], 'unresolved')
        other = next(t for t in themes if t['groups'] == ['IAM'])
        self.assertEqual(other['states'], ['not_applicable'])

    def test_policy_cannot_be_promoted_to_observed(self):
        self.packet['findings'][-2]['basis'] = 'observed'
        with self.assertRaisesRegex(s.InputError, 'artifact/metric'):
            s.synthesize(self.packet)

    def test_hypothesis_same_label_does_not_make_common_cause(self):
        selected = [f for f in self.packet['findings'] if f['practice_key'] == 'delivery-wait']
        for f in selected:
            f['mechanism_basis'] = 'hypothesis'
            f['mechanism_id'] = 'same-unproven-cause'
        themes = self.themes('delivery-wait')
        self.assertEqual(len(themes), 2)
        self.assertTrue(all(t['status'] == 'unresolved' for t in themes))

    def test_different_time_windows_do_not_compare(self):
        f = next(f for f in self.packet['findings'] if f['finding_id'] == 'F-WAIT-RIS')
        f['window_start'] = '2026-07-01'
        f['window_end'] = '2026-07-31'
        themes = self.themes('delivery-wait')
        self.assertTrue(all(t['related_findings_outside_theme'] == [] for t in themes))

    def test_transitive_origins_and_equal_digests_form_one_cluster(self):
        rows = {'a': {'origin_id':'one'}, 'b': {'origin_id':'one','content_sha256':'a'*64},
                'c': {'origin_id':'two','content_sha256':'a'*64}, 'd':{'origin_id':'two'}}
        result = s.correlation_map(rows)
        self.assertEqual(set(result.values()), {'a'})

    def test_missing_origin_is_explicit_not_independent(self):
        self.packet['sources'][0]['origin_id'] = None
        t, = self.themes('business-recovery-check')
        self.assertEqual(t['unknown_origin_ids'], ['RECOVERY-EXERCISE'])
        self.assertIn('independence', t['inference_limit'])

    def test_duplicate_source_and_finding_ids_rejected(self):
        for field in ('sources', 'findings'):
            p = copy.deepcopy(self.packet)
            p[field].append(p[field][0])
            with self.assertRaisesRegex(s.InputError, 'duplicate'):
                s.synthesize(p)

    def test_unknown_source_reference_rejected(self):
        self.packet['findings'][0]['support_ids'] = ['nonexistent']
        with self.assertRaisesRegex(s.InputError, 'unknown source'):
            s.synthesize(self.packet)

    def test_missing_support_requires_unknown(self):
        self.packet['findings'][0]['support_ids'] = []
        with self.assertRaisesRegex(s.InputError, 'requires support'):
            s.synthesize(self.packet)

    def test_dates_and_shared_dependency_validated(self):
        for field, value, expected in [('window_start','2026-99-01','calendar date'),
                                       ('window_start','2026-09-01','reversed'),
                                       ('dependency_id',None,'dependency_id')]:
            p = copy.deepcopy(self.packet)
            p['findings'][0][field] = value
            with self.assertRaisesRegex(s.InputError, expected):
                s.synthesize(p)

    def test_invalid_json_duplicate_keys_and_nonfinite_rejected(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '[]', '{bad}'):
            with self.assertRaises(s.InputError):
                s.load_json(raw)

    def test_order_invariance(self):
        expected = s.synthesize(self.packet)
        self.packet['sources'].reverse()
        self.packet['findings'].reverse()
        self.assertEqual(s.synthesize(self.packet), expected)

    def test_report_keeps_all_context_and_evidence_roles(self):
        self.packet['findings'][0]['limitation_ids'] = ['AI-POLICY']
        report = s.synthesize(self.packet)
        t = next(t for t in report['themes'] if t['practice_key'] == 'business-recovery-check')
        self.assertIn('AI-POLICY', t['limitation_ids'])
        self.assertIn('AI-POLICY', {x['source_id'] for x in t['sources']})
        md = s.render_markdown(report)
        for source in self.packet['sources']:
            self.assertIn(source['source_id'], md)
            self.assertIn(source['locator'], md)

    def test_csv_and_markdown_unicode_multiline_and_formula_handling(self):
        for f in self.packet['findings'][:3]:
            f['practice_key'] = '=SUM(1,2)'
            f['statement'] = 'Fictional naïve | 日本語\nsecond line <unsafe>'
        report = s.synthesize(self.packet)
        rows = list(csv.DictReader(io.StringIO(s.render_csv(report))))
        row = next(r for r in rows if r['practice_key'].startswith("'="))
        self.assertEqual(json.loads(row['groups']), ['ESS','IAM','RIS'])
        md = s.render_markdown(report)
        self.assertIn('naïve &#124; 日本語<br>second line &lt;unsafe&gt;', md)
        self.assertEqual(next(t for t in report['themes'] if t['practice_key'].startswith('='))['practice_key'], '=SUM(1,2)')

    def test_cli_all_formats_execute_and_do_not_mutate_input(self):
        path = BASE / 'fixtures/synthetic.json'
        before = path.read_bytes()
        for fmt in ('json','csv','markdown'):
            run = subprocess.run([sys.executable, str(BASE/'synthesis.py'), str(path), '--format',fmt],
                                 capture_output=True, text=True, check=False)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn('synthetic' if fmt!='csv' else 'theme_id', run.stdout)
        self.assertEqual(path.read_bytes(),before)

    def test_cli_missing_file_is_useful_error(self):
        run = subprocess.run([sys.executable,str(BASE/'synthesis.py'),str(BASE/'does-not-exist.json')],
                             capture_output=True,text=True,check=False)
        self.assertEqual(run.returncode,2)
        self.assertIn('synthesis:',run.stderr)
        self.assertEqual(run.stdout,'')


if __name__ == '__main__':
    unittest.main()

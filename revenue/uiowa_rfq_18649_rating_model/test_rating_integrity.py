from __future__ import annotations
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

TARGET=Path(os.environ.get('AUDIT_TARGET',Path(__file__).parent)).resolve()
spec=importlib.util.spec_from_file_location('_uiowa022_integrity_subject',TARGET/'rating_model.py')
if spec is None or spec.loader is None:
    raise RuntimeError('Cannot load selected rating_model.py')
model=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=model
spec.loader.exec_module(model)


def row(cid='SYN-A',area='security',service='ESS',rank=4,**fields):
    r=dict(criterion_id=cid,area=area,service=service,assessment_status='assessed',
           criticality='important',maturity_rank=rank,maturity_label=f'anchor-{rank}',
           confidence='high',material_gap=False,evidence_ids=['SYN-E'])
    r.update(fields)
    return r


def unknown(cid='SYN-U',area='security',service='ESS'):
    return dict(criterion_id=cid,area=area,service=service,
                assessment_status='unassessed',criticality='important')


class RatingIntegrityTests(unittest.TestCase):
    def invalid_settings(self,setting):
        with self.assertRaises(model.ModelError):
            model.compose({'criteria':[row()], 'settings':setting})

    def test_boolean_false_threshold_is_rejected(self):
        self.invalid_settings({'min_coverage_for_characterization':False})
    def test_boolean_true_threshold_is_rejected(self):
        self.invalid_settings({'min_coverage_for_characterization':True})
    def test_string_threshold_is_rejected(self):
        self.invalid_settings({'min_coverage_for_characterization':'0'})
    def test_null_settings_is_rejected(self):
        self.invalid_settings(None)
    def test_false_settings_is_rejected(self):
        self.invalid_settings(False)
    def test_list_settings_is_rejected(self):
        self.invalid_settings([])
    def test_populated_list_settings_has_model_error(self):
        self.invalid_settings([1])
    def test_non_object_settings_has_model_error(self):
        self.invalid_settings('bad')
    def test_fractional_spread_is_rejected(self):
        self.invalid_settings({'mixed_maturity_spread':2.9})
    def test_boolean_spread_is_rejected(self):
        self.invalid_settings({'mixed_maturity_spread':True})
    def test_string_spread_is_rejected(self):
        self.invalid_settings({'mixed_maturity_spread':'2'})
    def test_unknown_setting_is_rejected(self):
        self.invalid_settings({'min_coverage_for_characterisation':.9})
    def test_nonfinite_settings_are_rejected(self):
        for key in ['min_coverage_for_characterization','mixed_maturity_spread']:
            for value in [float('nan'),float('inf'),-float('inf')]:
                with self.subTest(key=key,value=value):
                    self.invalid_settings({key:value})
    def test_out_of_range_settings_rejected(self):
        for v in [-.1,1.1,10**400]:
            self.invalid_settings({'min_coverage_for_characterization':v})
        for v in [0,-1]:
            self.invalid_settings({'mixed_maturity_spread':v})
    def test_explicit_numeric_zero_is_still_supported(self):
        p={'criteria':[row()]+[unknown(str(i)) for i in range(9)],
           'settings':{'min_coverage_for_characterization':0}}
        r=model.compose(p)['area_summaries']['security']
        self.assertEqual(r['coverage'],.1)
        self.assertEqual(r['composition_status'],'coherent_pattern')
    def test_integral_float_spread_matches_schema(self):
        r=model.compose({'criteria':[row()], 'settings':{'mixed_maturity_spread':2.0}})
        self.assertEqual(r['settings']['mixed_maturity_spread'],2)
    def test_valid_default_and_boundaries(self):
        for cov in [0,.1,.6,1]:
            r=model.compose({'criteria':[row()], 'settings':{'min_coverage_for_characterization':cov}})
            self.assertEqual(r['settings']['min_coverage_for_characterization'],cov)
        self.assertEqual(model.compose({'criteria':[row()]})['settings']['min_coverage_for_characterization'],.6)
    def test_service_tuple_collision_preserves_both_groups(self):
        p={'criteria':[row('C1',area='a',service='b::c',rank=1),row('C2',area='a::b',service='c',rank=4)]}
        r=model.compose(p)['service_summaries']
        self.assertEqual(len(r),2)
        self.assertEqual(sum(s['counts']['total'] for s in r.values()),2)
        self.assertEqual({(s['area'],s['service']) for s in r.values()},{('a','b::c'),('a::b','c')})
    def test_percent_escape_cannot_alias_literal_id(self):
        pairs=[('a:b','c'),('a%3Ab','c'),('a','b::c'),('a::b','c'),('a%','b')]
        r=model.compose({'criteria':[row(str(i),area=a,service=s) for i,(a,s) in enumerate(pairs)]})
        self.assertEqual(len(r['service_summaries']),len(pairs))
    def test_ordinary_service_keys_remain_compatible(self):
        r=model.compose({'criteria':[row()]})['service_summaries']
        self.assertIn('security::ESS',r)
    def test_unicode_identifiers_preserved(self):
        names=['Équipe','E\u0301quipe','身份::组','身份%3A%3A组']
        r=model.compose({'criteria':[row(str(i),service=s) for i,s in enumerate(names)]})
        self.assertEqual(len(r['service_summaries']),4)
        self.assertEqual({s['service'] for s in r['service_summaries'].values()},set(names))
    def test_markdown_retains_mixed_service_evidence(self):
        p={'criteria':[row('E',service='ESS',rank=4),row('R',service='RIS',rank=1),row('I',service='IAM',rank=3)]}
        r=model.compose(p)
        self.assertEqual(r['area_summaries']['security']['composition_status'],'mixed_practice')
        md=model.render_markdown(r)
        self.assertIn('## Service summaries',md)
        for service in ['ESS','RIS','IAM']:
            self.assertIn(f'| {service} |',md)
        self.assertIn('1–1 (spread 0)',md)
        self.assertIn('4–4 (spread 0)',md)
    def test_markdown_pipe_does_not_add_columns(self):
        p={'criteria':[row('GAP|ONE',area='security | deployment',criticality='critical',material_gap=True)]}
        md=model.render_markdown(model.compose(p))
        tab=[line for line in md.splitlines() if line.startswith('|')]
        self.assertEqual(tab[0].count('|'),8)
        self.assertEqual(tab[2].count('|'),8)
        self.assertIn('GAP&#124;ONE',md)
    def test_markdown_linebreak_does_not_split_record(self):
        p={'criteria':[row('GAP\nONE',criticality='critical',material_gap=True)]}
        md=model.render_markdown(model.compose(p))
        self.assertIn('GAP<br>ONE',md)
    def test_markdown_html_and_backticks_remain_text(self):
        p={'criteria':[row('SYN',area='<em>SEC</em>',maturity_label='a`b')]}
        md=model.render_markdown(model.compose(p))
        self.assertNotIn('<em>',md)
        self.assertIn('&lt;em&gt;',md)
        self.assertIn('&#96;',md)
    def test_legacy_saved_report_is_rendered_without_guessed_identity(self):
        r=model.compose({'criteria':[row(service='b::c'),row('R',service='RIS',rank=1)]})
        for summary in r['service_summaries'].values():
            summary.pop('area',None)
            summary.pop('service',None)
        r.pop('service_key_encoding',None)
        before=copy.deepcopy(r)
        md=model.render_markdown(r)
        self.assertIn('Unresolved legacy identity',md)
        self.assertIn('Combined group ID:',md)
        self.assertIn('cannot be recovered',md)
        self.assertEqual(r,before)
    def test_key_encoding_is_explicit(self):
        r=model.compose({'criteria':[row()]})
        self.assertEqual(r['service_key_encoding'],'percent-colon-v1')
    def test_key_encoding_is_reversible_for_delimiter_and_percent(self):
        from urllib.parse import unquote
        pairs=[('a:b','c'),('a%3Ab','c'),('a','b::c'),('a::b','c'),('身份%','组::x')]
        r=model.compose({'criteria':[row(str(i),area=a,service=s) for i,(a,s) in enumerate(pairs)]})
        reconstructed={tuple(unquote(v) for v in key.split('::')) for key in r['service_summaries']}
        self.assertEqual(reconstructed,set(pairs))
    def test_report_does_not_change_structured_result(self):
        r=model.compose({'criteria':[row()]})
        before=copy.deepcopy(r)
        model.render_markdown(r)
        self.assertEqual(r,before)
    def test_low_coverage_stays_insufficient(self):
        p={'criteria':[row()]+[unknown(str(i)) for i in range(9)]}
        s=model.compose(p)['area_summaries']['security']
        self.assertEqual(s['composition_status'],'insufficient_coverage')
        self.assertEqual(s['coverage'],.1)
    def test_critical_gap_stays_visible(self):
        p={'criteria':[row('G',rank=1,criticality='critical',material_gap=True),row('S')]}
        s=model.compose(p)['area_summaries']['security']
        self.assertEqual(s['composition_status'],'critical_gap_present')
        self.assertEqual(s['critical_gap_ids'],['G'])
    def test_unassessed_and_na_remain_distinct(self):
        n=unknown('NA');n.update(assessment_status='not_applicable',applicability_reason='Synthetic boundary')
        s=model.compose({'criteria':[unknown(),n]})['area_summaries']['security']
        self.assertEqual(s['composition_status'],'unassessed')
        self.assertEqual(s['counts']['eligible'],1)
        self.assertEqual(s['counts']['not_applicable'],1)
        self.assertIsNone(s['maturity_range'])
    def test_low_confidence_does_not_reduce_rank(self):
        s=model.compose({'criteria':[row(confidence='low')]})['area_summaries']['security']
        self.assertEqual(s['minimum_confidence'],'low')
        self.assertEqual(s['maturity_distribution_by_rank'],{'4':1})
    def test_boolean_rank_stays_rejected(self):
        with self.assertRaises(model.ModelError):
            model.compose({'criteria':[row(rank=True)]})
    def test_unassessed_zero_stays_rejected(self):
        u=unknown();u['maturity_rank']=0
        with self.assertRaises(model.ModelError):
            model.compose({'criteria':[u]})
    def test_duplicate_ids_stay_rejected(self):
        with self.assertRaises(model.ModelError):
            model.compose({'criteria':[row(),row()]})
    def test_input_is_not_mutated(self):
        p={'criteria':[row()]};before=copy.deepcopy(p)
        model.compose(p)
        self.assertEqual(p,before)
    def test_cli_writes_service_preserving_outputs(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);p=d/'in.json';j=d/'out.json';m=d/'out.md'
            p.write_text(json.dumps({'criteria':[row()]}),encoding='utf-8')
            proc=subprocess.run([sys.executable]+(['-O'] if sys.flags.optimize else [])+[str(TARGET/'rating_model.py'),str(p),'--json-out',str(j),'--markdown-out',str(m)],capture_output=True,text=True,timeout=10)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertIn('security::ESS',json.loads(j.read_text())['service_summaries'])
            self.assertIn('## Service summaries',m.read_text())

if __name__=='__main__':
    unittest.main(verbosity=2)

"""Behavioral regressions for UIOWA-038; all records are fictional."""
from __future__ import annotations
import copy
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

if __package__:
    from . import register as r
else:
    import register as r

HERE = Path(__file__).resolve().parent

def fixture():
    return r.loads((HERE / 'examples/synthetic_register.json').read_text(encoding='utf-8'))

class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.reg = fixture()

    def rejected(self, mutate):
        mutate(self.reg)
        with self.assertRaises(r.RegisterError):
            r.normalize(self.reg)

    def test_complete_fixture_shape(self):
        self.assertEqual(r.normalize(self.reg), self.reg)

    def test_multiple_findings_do_not_multiply_recommendations_or_effort(self):
        s = r.summary(self.reg)
        self.assertEqual((s['unique_recommendations'], s['finding_links']), (5, 9))
        self.assertEqual(s['known_effort_subtotal'], dict(low=6.0, high=12.0, unit='person_days'))
        self.assertFalse(s['effort_total_complete'])
        self.assertEqual(s['unknown_effort_ids'], ['REC-SYN-03'])

    def test_an_additional_link_does_not_add_effort(self):
        before = r.summary(self.reg)
        self.reg['recommendations'][0]['finding_ids'].append('F-SYN-06')
        after = r.summary(self.reg)
        self.assertEqual(after['known_effort_subtotal'], before['known_effort_subtotal'])
        self.assertEqual(after['unique_recommendations'], before['unique_recommendations'])
        self.assertEqual(after['finding_links'], before['finding_links'] + 1)

    def test_duplicate_recommendation_id_is_not_silently_summed(self):
        self.rejected(lambda v: v['recommendations'].append(copy.deepcopy(v['recommendations'][0])))

    def test_same_title_different_ids_are_not_silently_merged(self):
        self.reg['recommendations'][1]['practice_change'] = self.reg['recommendations'][0]['practice_change']
        self.assertEqual(r.summary(self.reg)['unique_recommendations'], 5)

    def test_duplicate_finding_id_rejected(self):
        self.rejected(lambda v: v['findings'].append(copy.deepcopy(v['findings'][0])))

    def test_duplicate_link_is_not_double_counted(self):
        self.rejected(lambda v: v['recommendations'][0]['finding_ids'].append('F-SYN-01'))

    def test_duplicate_scope_rejected(self):
        self.rejected(lambda v: v['recommendations'][0]['scope'].append(v['recommendations'][0]['scope'][0]))

    def test_unknown_and_known_zero_remain_distinct(self):
        recs = r.from_view(r.roadmap_view(self.reg))['recommendations']
        self.assertIsNone(recs[2]['effort']['low'])
        self.assertEqual(recs[3]['effort']['low'], 0)
        self.assertIsNone(recs[2]['phase'])
        self.assertEqual(recs[3]['phase'], '0-90')

    def test_empty_register_never_establishes_complete_total(self):
        self.reg['recommendations'] = []
        self.reg['findings'] = []
        self.assertFalse(r.summary(self.reg)['effort_total_complete'])
        self.assertIn('register is empty', r.render(self.reg))

    def test_all_known_efforts_sum_once(self):
        self.reg['recommendations'][2]['effort'] = dict(low=1,high=2,unit='person_days',basis='Fictional estimate.')
        s = r.summary(self.reg)
        self.assertTrue(s['effort_total_complete'])
        self.assertEqual(s['known_effort_subtotal']['low'], 7)
        self.assertEqual(s['known_effort_subtotal']['high'], 14)

    def test_preserve_unresolved_finding(self):
        self.reg['recommendations'][0]['finding_ids'].append('F-UNRESOLVED')
        self.assertIn('FINDING_UNRESOLVED', [i['code'] for i in r.review_items(self.reg)])
        self.assertEqual(r.from_view(r.report_view(self.reg)), self.reg)

    def test_preserve_unresolved_dependency(self):
        self.reg['recommendations'][0]['dependencies'] = ['REC-UNRESOLVED']
        view = r.roadmap_view(self.reg)
        self.assertEqual(view['items'][0]['prerequisites'], ['REC-UNRESOLVED'])
        self.assertIn('DEPENDENCY_UNRESOLVED', [i['code'] for i in view['review_items']])
        self.assertEqual(r.from_view(view), self.reg)

    def test_out_of_scope_finding_names_the_link(self):
        self.reg['recommendations'][0]['finding_ids'].append('F-SYN-04')
        self.assertIn(dict(recommendation_id='REC-SYN-01', code='FINDING_OUTSIDE_SCOPE', detail='F-SYN-04'), r.review_items(self.reg))

    def test_scope_unknown_not_inferred(self):
        self.reg['recommendations'][0]['scope'] = []
        view = r.roadmap_view(self.reg)
        self.assertEqual(view['items'][0]['owner_groups'], [])
        self.assertIsNone(view['items'][0]['owner_group'])
        self.assertIn('SCOPE_UNKNOWN', [i['code'] for i in view['review_items']])

    def test_shared_recommendation_does_not_pick_a_false_owner_group(self):
        row = r.roadmap_view(self.reg)['items'][0]
        self.assertEqual(row['owner_groups'], ['ESS','RIS'])
        self.assertIsNone(row['owner_group'])

    def test_single_group_projection_matches_original_vocabulary(self):
        row = r.roadmap_view(self.reg)['items'][1]
        self.assertEqual(row['owner_group'], 'ESS')
        self.assertEqual(row['prerequisites'], ['REC-SYN-01'])
        self.assertEqual(row['phase'], '90-180')

    def test_report_many_to_many_links_retained(self):
        links = r.report_view(self.reg)['finding_links']
        self.assertEqual(links[0]['recommendation_ids'], ['REC-SYN-01','REC-SYN-02','REC-SYN-05'])

    def test_both_views_roundtrip_all_fields(self):
        for fn in (r.report_view, r.roadmap_view):
            with self.subTest(fn=fn.__name__):
                self.assertEqual(r.from_view(r.loads(r.dumps(fn(self.reg)))), self.reg)

    def test_edited_projection_is_not_silently_discarded(self):
        view = r.roadmap_view(self.reg)
        view['items'][1]['phase'] = '180+'
        with self.assertRaisesRegex(r.RegisterError,'edit the register/CSV'):
            r.from_view(view)

    def test_boolean_number_projection_substitution_rejected(self):
        view = r.report_view(self.reg)
        view['summary']['effort_total_complete'] = 0
        with self.assertRaises(r.RegisterError):
            r.from_view(view)

    def test_mutated_source_digest_rejected(self):
        view = r.report_view(self.reg)
        view['source_register']['recommendations'][0]['impact'] = 'Changed text'
        with self.assertRaises(r.RegisterError):
            r.from_view(view)

    def test_view_requires_complete_source_register(self):
        with self.assertRaises(r.RegisterError):
            r.from_view({'view_schema':r.SCHEMA+'/roadmap','items':[]})

    def test_csv_roundtrip_all_fields(self):
        tab = r.tables(self.reg)
        self.assertEqual(r.from_tables(tab['metadata.json'],tab['findings.csv'],tab['recommendations.csv']), self.reg)

    def test_csv_unicode_multiline_delimiters_and_formula_text_roundtrip(self):
        self.reg['recommendations'][0]['practice_change'] = '=HYPERLINK("fiction")\n+中文, café | naïve'
        tab = r.tables(self.reg)
        cells = list(csv.reader(io.StringIO(tab['recommendations.csv'])))
        self.assertTrue(cells[1][1].startswith('"'))
        self.assertNotIn(cells[1][1][0], '=+-@\t\r\n')
        self.assertEqual(r.from_tables(tab['metadata.json'],tab['findings.csv'],tab['recommendations.csv']), self.reg)

    def test_csv_edit_changes_canonical_record_and_all_views(self):
        tab = r.tables(self.reg)
        rows = list(csv.reader(io.StringIO(tab['recommendations.csv'])))
        phase = rows[0].index('phase')
        rows[1][phase] = '"90-180"'
        stream = io.StringIO(newline='')
        csv.writer(stream,lineterminator='\n').writerows(rows)
        edited = r.from_tables(tab['metadata.json'],tab['findings.csv'],stream.getvalue())
        self.assertEqual(edited['recommendations'][0]['phase'],'90-180')
        self.assertEqual(r.roadmap_view(edited)['items'][0]['phase'],'90-180')
        self.assertNotEqual(r.digest(edited),r.digest(self.reg))

    def test_csv_shifted_row_and_wrong_headers_rejected(self):
        tab = r.tables(self.reg)
        for bad in (tab['recommendations.csv'].replace('recommendation_id','id',1), tab['recommendations.csv'] + 'one,two\n'):
            with self.subTest(bad=bad[-20:]), self.assertRaises(r.RegisterError):
                r.from_tables(tab['metadata.json'],tab['findings.csv'],bad)

    def test_empty_csv_cell_is_not_null(self):
        tab = r.tables(self.reg)
        rows = list(csv.reader(io.StringIO(tab['recommendations.csv'])))
        rows[1][rows[0].index('phase')] = ''
        stream = io.StringIO(newline='')
        csv.writer(stream).writerows(rows)
        with self.assertRaises(r.RegisterError):
            r.from_tables(tab['metadata.json'],tab['findings.csv'],stream.getvalue())

    def test_dictionary_order_not_material_to_digest(self):
        reordered = dict(reversed(list(self.reg.items())))
        self.assertEqual(r.digest(reordered), r.digest(self.reg))

    def test_list_order_preserved_not_rewritten_into_a_schedule(self):
        self.reg['recommendations'].reverse()
        tab = r.tables(self.reg)
        self.assertEqual(r.from_tables(tab['metadata.json'],tab['findings.csv'],tab['recommendations.csv']),self.reg)
        self.assertNotIn('execution_order', r.roadmap_view(self.reg))

    def test_unrecognized_group_dimension_phase_rejected(self):
        for parent,key,bad in [('finding','group','ALL'),('finding','dimension','software_development'),('rec','phase','NOW')]:
            self.reg = fixture()
            row = self.reg['findings'][0] if parent == 'finding' else self.reg['recommendations'][0]
            row[key] = bad
            with self.subTest(key=key), self.assertRaises(r.RegisterError):
                r.normalize(self.reg)

    def test_missing_extra_and_non_draft_fields_rejected(self):
        for change in (lambda v:v.pop('assumptions'),lambda v:v.update(approved=True),lambda v:v.update(record_status='APPROVED')):
            self.reg=fixture()
            self.rejected(change)

    def test_non_list_links_rejected(self):
        self.rejected(lambda v:v['recommendations'][0].update(finding_ids='F-SYN-01,F-SYN-02'))

    def test_nonfinite_boolean_negative_huge_and_half_ranges_rejected(self):
        for low,high in [(True,2),(-1,2),(float('inf'),float('inf')),(float('nan'),2),(10**400,10**400),(1,None),(3,2)]:
            self.reg=fixture()
            self.reg['recommendations'][0]['effort'].update(low=low,high=high)
            with self.subTest(low=str(low)[:20]), self.assertRaises(r.RegisterError):
                r.normalize(self.reg)

    def test_overflowing_subtotal_is_input_error_not_infinity(self):
        for rec in self.reg['recommendations']:
            rec['effort'].update(low=1e308,high=1e308,basis='Fictional pathological number')
        with self.assertRaises(r.RegisterError):
            r.summary(self.reg)

    def test_numeric_effort_requires_basis(self):
        self.rejected(lambda v:v['recommendations'][0]['effort'].update(basis=None))

    def test_numeric_outcome_requires_basis(self):
        self.rejected(lambda v:v['recommendations'][1]['outcome_measure'].update(basis=None))

    def test_unknown_measure_is_not_zero(self):
        view = r.report_view(self.reg)
        self.assertIsNone(view['source_register']['recommendations'][0]['outcome_measure']['baseline'])
        self.assertEqual(view['source_register']['recommendations'][1]['outcome_measure']['baseline'],0)

    def test_duplicate_json_keys_and_non_strict_literals_rejected(self):
        for text in ('{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}'):
            with self.subTest(text=text), self.assertRaises(r.RegisterError):
                r.loads(text)

    def test_bad_unicode_blank_and_control_text_rejected(self):
        for value in ('\ud800','  ','bad\x00text'):
            self.reg=fixture()
            self.rejected(lambda v:v['recommendations'][0].update(practice_change=value))

    def test_markdown_not_html_injection_or_broken_table(self):
        self.reg['recommendations'][0]['practice_change']='<script>fiction</script>|line\nnext'
        rendered=r.render(self.reg)
        self.assertNotIn('<script>',rendered)
        self.assertIn('&lt;script&gt;',rendered)
        self.assertIn('\\|line<br>next',rendered)
        self.assertIn('UNASSIGNED',rendered)

class FilesystemAndCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.reg = fixture()
    def tearDown(self):
        self.tmp.cleanup()
    def cli(self,*args,optimized=False):
        return subprocess.run([sys.executable]+(['-O'] if optimized else [])+[str(HERE/'register.py'),*map(str,args)],cwd=self.root,text=True,encoding='utf-8',capture_output=True,timeout=15)

    def test_export_import_cli_normal_and_optimized_from_foreign_cwd(self):
        source = HERE/'examples/synthetic_register.json'
        for optimized in (False,True):
            with self.subTest(optimized=optimized):
                out=self.root/('opt' if optimized else 'normal')
                p=self.cli('export',source,'--out',out,optimized=optimized)
                self.assertEqual(p.returncode,0,p.stderr)
                back=self.root/(out.name+'.json')
                p=self.cli('import',out,'--out',back,optimized=optimized)
                self.assertEqual(p.returncode,0,p.stderr)
                self.assertEqual(r.loads(r.read(back)),self.reg)
                for kind in ('report','roadmap'):
                    restored=self.root/(out.name+kind+'.json')
                    p=self.cli('import-view',out/(kind+'.json'),'--out',restored,optimized=optimized)
                    self.assertEqual(p.returncode,0,p.stderr)
                    self.assertEqual(r.loads(r.read(restored)),self.reg)

    def test_check_reports_unknowns_without_clearing_them(self):
        p=self.cli('check',HERE/'examples/synthetic_register.json')
        self.assertEqual(p.returncode,1,p.stderr)
        data=r.loads(p.stdout)
        self.assertEqual(data['record_status'],r.DRAFT)
        self.assertEqual(data['summary']['unknown_effort_ids'],['REC-SYN-03'])

    def test_bad_input_returns_two_without_traceback(self):
        bad=self.root/'bad.json';bad.write_text('{"x":NaN}')
        p=self.cli('check',bad)
        self.assertEqual(p.returncode,2)
        self.assertNotIn('Traceback',p.stderr)

    def test_existing_directory_and_file_survive(self):
        for name,isdir in [('directory',True),('file',False)]:
            dst=self.root/name
            if isdir:
                dst.mkdir(); victim=dst/'evidence';victim.write_bytes(b'KEEP')
            else:
                victim=dst;victim.write_bytes(b'KEEP')
            with self.assertRaises(OSError):r.export_bundle(self.reg,dst)
            self.assertEqual(victim.read_bytes(),b'KEEP')

    def test_final_symlink_not_followed_for_output(self):
        target=self.root/'target';target.mkdir();(target/'evidence').write_bytes(b'KEEP')
        link=self.root/'link'
        try:link.symlink_to(target,target_is_directory=True)
        except OSError as exc:self.skipTest(str(exc))
        with self.assertRaises(OSError):r.export_bundle(self.reg,link)
        self.assertEqual(list(target.iterdir()),[target/'evidence'])

    def test_existing_import_output_not_replaced(self):
        out=self.root/'bundle';r.export_bundle(self.reg,out)
        target=self.root/'keep.json';target.write_bytes(b'KEEP')
        p=self.cli('import',out,'--out',target)
        self.assertEqual(p.returncode,2)
        self.assertEqual(target.read_bytes(),b'KEEP')

    def test_partial_export_failure_preserves_written_evidence(self):
        out=self.root/'partial'
        real=r.write_new
        def fail(path,content):
            if path.name=='recommendations.csv':raise OSError('injected storage failure')
            real(path,content)
        with mock.patch.object(r,'write_new',side_effect=fail), self.assertRaises(OSError):
            r.export_bundle(self.reg,out)
        self.assertEqual((out/'metadata.json').read_text(),r.tables(self.reg)['metadata.json'])
        self.assertTrue((out/'findings.csv').is_file())
        self.assertFalse((out/'register.json').exists())

    def test_output_is_deterministic_and_input_is_unmodified(self):
        old=r.dumps(self.reg)
        a=self.root/'a';b=self.root/'b'
        r.export_bundle(self.reg,a);r.export_bundle(self.reg,b)
        self.assertEqual(r.dumps(self.reg),old)
        self.assertEqual(sorted(p.name for p in a.iterdir()),sorted(p.name for p in b.iterdir()))
        for p in a.iterdir():self.assertEqual(p.read_bytes(),(b/p.name).read_bytes())

    def test_oversized_and_non_utf8_input_rejected(self):
        for name,data in [('large',b' '*(r.MAX_BYTES+1)),('encoding',b'\xff')]:
            p=self.root/name;p.write_bytes(data)
            with self.subTest(name=name), self.assertRaises(r.RegisterError):r.read(p)

if __name__=='__main__':unittest.main()

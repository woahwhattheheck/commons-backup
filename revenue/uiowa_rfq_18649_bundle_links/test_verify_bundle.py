from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from build_example import build, HERE
from verify_bundle import Bundle, check, markdown_anchors


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'bundle'
        self.root.mkdir()
        self.write('review.html', '<h1 id="home">Review</h1>\n')
        self.write('source.html', '<h2 id="one">One</h2>\n<h2 id="two">Two</h2>\n')
        self.write('source.md', '# One\n\n## Two\nA unique phrase.\n')
        self.write('rows.csv', 'id,note\nE-1,"first\nsecond"\nE-2,last\n')

    def write(self, path, text):
        dest = self.root/path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding='utf-8')
        return dest

    def result(self, target='source.html#one', **extra):
        ref = {'id':'r1','source':'review.html','target':target}
        ref.update(extra)
        return Bundle(self.root).verify(ref)

    def status(self, expected, target='source.html#one', **extra):
        result = self.result(target, **extra)
        self.assertEqual(result.status, expected, result)
        return result

    def test_existing_html_anchor(self):
        self.status('VERIFIED')

    def test_same_document_anchor(self):
        self.status('VERIFIED', '#home')

    def test_missing_anchor_names_suggestion(self):
        self.assertIn('one',self.status('MISSING_ANCHOR','source.html#on').suggestions)

    def test_duplicate_anchor_is_ambiguous(self):
        self.write('source.html','<p id="one"></p><a name="one">again</a>')
        self.status('AMBIGUOUS_ANCHOR')

    def test_same_element_id_and_name_is_one_destination(self):
        self.write('source.html','<a id="one" name="one">single</a>')
        self.status('VERIFIED')

    def test_legacy_named_anchor(self):
        self.write('source.html','<a name="one">single</a>')
        self.status('VERIFIED')

    def test_percent_encoded_unicode_path_and_anchor(self):
        self.write('sources/évidence.html','<p id="café">x</p>')
        self.status('VERIFIED','sources/%C3%A9vidence.html#caf%C3%A9')

    def test_relative_parent_path(self):
        self.write('nested/review.html','review')
        self.status('VERIFIED','../source.html#one',source='nested/review.html')

    def test_missing_target(self):
        self.status('MISSING_TARGET','missing.html#one')

    def test_rename_suggestion_uses_exact_content_not_redirect(self):
        data = (self.root/'source.html').read_bytes()
        (self.root/'source.html').rename(self.root/'renamed.html')
        result = self.status('MISSING_TARGET','source.html#one',sha256=hashlib.sha256(data).hexdigest())
        self.assertEqual(result.suggestions,['renamed.html'])

    def test_unicode_normalization_collision(self):
        self.write('é.html','x')
        self.write('e\u0301.html','y')
        self.status('AMBIGUOUS_PATH','é.html')

    def test_case_collision(self):
        self.write('SOURCE.html','x')
        self.status('AMBIGUOUS_PATH')

    def test_case_mismatch_not_silent_pass(self):
        self.status('PATH_SPELLING_MISMATCH','Source.html#one')

    def test_external_never_claimed_verified(self):
        self.status('EXTERNAL_UNCHECKED','https://example.invalid/docs#one')

    def test_protocol_relative_external(self):
        self.status('EXTERNAL_UNCHECKED','//example.invalid/docs')

    def test_absolute_path_not_portable(self):
        self.status('NONPORTABLE_TARGET','/source.html')

    def test_parent_outside_bundle_not_inspected(self):
        self.status('OUTSIDE_BUNDLE','../outside.txt')

    def test_symlink_outside_bundle_not_inspected(self):
        outside = self.root.parent/'outside.txt'
        outside.write_text('no read', encoding='utf-8')
        (self.root/'alias.txt').symlink_to(outside)
        self.status('OUTSIDE_BUNDLE','alias.txt')

    def test_windows_path_diagnosed(self):
        self.status('NONPORTABLE_TARGET',r'folder\file.html')

    def test_encoded_backslash_diagnosed(self):
        self.status('NONPORTABLE_TARGET','folder%5Cfile.html')

    def test_invalid_percent_escape(self):
        self.status('INVALID_URL_ENCODING','%zz.html')

    def test_percent_encoded_nul(self):
        self.status('NONPORTABLE_TARGET','%00.html')

    def test_query_dependent_navigation_unresolved(self):
        self.status('UNSUPPORTED_QUERY','source.html?tab=a#one')

    def test_base_href_detected_in_html_scan(self):
        self.write('review.html','<base href="nested/"><a href="source.html#one">x</a>')
        self.assertEqual(Bundle(self.root).scan_html('review.html')[0].status,'UNSUPPORTED_BASE')

    def test_base_href_detected_in_manifest_citation(self):
        self.write('review.html','<base href="nested/">')
        self.status('UNSUPPORTED_BASE')

    def test_changed_source_bytes(self):
        self.status('CONTENT_CHANGED',sha256='0'*64)

    def test_invalid_sha(self):
        self.status('INVALID_REFERENCE',sha256='not-a-sha')

    def test_whole_binary_file_is_supported(self):
        (self.root/'scan.pdf').write_bytes(b'%PDF not-a-real-pdf')
        self.status('VERIFIED','scan.pdf')

    def test_binary_page_locator_is_not_fake_verified(self):
        (self.root/'scan.pdf').write_bytes(b'%PDF not-a-real-pdf')
        self.status('UNSUPPORTED_LOCATOR','scan.pdf',locator={'kind':'page','number':2})

    def test_markdown_simple_heading(self):
        self.status('VERIFIED','source.md#two')

    def test_markdown_repeated_heading_slug(self):
        self.write('source.md','# One\n# One\n# One-1\n# One\n')
        anchors = markdown_anchors((self.root/'source.md').read_text())
        self.assertEqual(set(anchors),{'one','one-1','one-1-1','one-2'})
        self.status('VERIFIED','source.md#one-2')

    def test_code_fence_headings_not_destinations(self):
        self.write('source.md','```md\n# Invisible\n```\n# Visible\n')
        self.status('MISSING_ANCHOR','source.md#invisible')

    def test_complex_markdown_not_guessed(self):
        self.write('source.md','# [Title](x)\n')
        self.status('MISSING_ANCHOR','source.md#title')

    def test_line_locator(self):
        self.status('VERIFIED','source.md',locator={'kind':'lines','start':2,'end':4})

    def test_missing_lines(self):
        self.status('MISSING_LINES','source.md',locator={'kind':'lines','start':2,'end':999})

    def test_boolean_not_a_line_number(self):
        self.status('INVALID_LOCATOR','source.md',locator={'kind':'lines','start':True})

    def test_unique_exact_quote(self):
        self.status('VERIFIED','source.md',locator={'kind':'quote','text':'A unique phrase.'})

    def test_missing_quote(self):
        self.status('MISSING_QUOTE','source.md',locator={'kind':'quote','text':'absent'})

    def test_overlapping_quote_is_ambiguous(self):
        self.write('source.md','aaa')
        self.status('AMBIGUOUS_QUOTE','source.md',locator={'kind':'quote','text':'aa'})

    def test_csv_multiline_record_preserved(self):
        self.status('VERIFIED','rows.csv',locator={'kind':'csv','column':'id','value':'E-1'})

    def test_duplicate_csv_record(self):
        self.write('rows.csv','id,note\nE-1,x\nE-1,y\n')
        self.status('AMBIGUOUS_RECORD','rows.csv',locator={'kind':'csv','column':'id','value':'E-1'})

    def test_missing_csv_record(self):
        self.status('MISSING_RECORD','rows.csv',locator={'kind':'csv','column':'id','value':'E-9'})

    def test_duplicate_csv_column(self):
        self.write('rows.csv','id,id\nE-1,E-1\n')
        self.status('INVALID_CSV_COLUMN','rows.csv',locator={'kind':'csv','column':'id','value':'E-1'})

    def test_malformed_csv_width(self):
        self.write('rows.csv','id,note\nE-1,x,y\n')
        self.status('MALFORMED_CSV','rows.csv',locator={'kind':'csv','column':'id','value':'E-1'})

    def test_missing_source(self):
        self.status('MISSING_SOURCE',source='no-source.html')

    def test_source_line_preserved(self):
        result = self.status('VERIFIED',source_line=1)
        self.assertEqual(result.source_line,1)

    def test_missing_source_line(self):
        self.status('MISSING_SOURCE_LINE',source_line=999)

    def test_html_links_and_lines_are_extracted(self):
        self.write('review.html','<p>Review</p>\n<a href="source.html#one">x</a>\n<img src="rows.csv">')
        results=Bundle(self.root).scan_html('review.html')
        self.assertEqual([r.status for r in results],['VERIFIED','VERIFIED'])
        self.assertEqual([r.source_line for r in results],[2,3])

    def test_invalid_reference_shapes(self):
        for ref in [None, [], {}, {'id':1,'source':'review.html','target':'source.md'}]:
            self.assertEqual(Bundle(self.root).verify(ref).status,'INVALID_REFERENCE')

    def test_empty_locator_diagnosed(self):
        self.status('INVALID_LOCATOR','source.md',locator={})

    def test_size_limit(self):
        result=Bundle(self.root,max_bytes=4).verify({'id':'a','source':'source.md','target':'source.md#two'})
        self.assertEqual(result.status,'INSPECTION_ERROR')

    def test_non_utf8_locator_diagnosed(self):
        (self.root/'source.md').write_bytes(b'\xff')
        self.status('UNREADABLE_TEXT','source.md#one')

    def test_duplicate_reference_ids(self):
        ref={'id':'x','source':'review.html','target':'source.html'}
        report=check(self.root,{'version':1,'citations':[ref,ref]})
        self.assertEqual(report['counts'],{'DUPLICATE_CITATION_ID':2})

    def test_declared_and_scanned_id_collision(self):
        self.write('review.html','<a href="source.html">source</a>')
        ref={'id':'review.html:1:1','source':'review.html','target':'source.html'}
        report=check(self.root,{'version':1,'citations':[ref],'scan_html':['review.html']})
        self.assertEqual(report['counts'],{'DUPLICATE_CITATION_ID':2})

    def test_empty_manifest_not_vacuous_success(self):
        self.assertEqual(check(self.root,{'version':1})['verdict'],'UNRESOLVED')

    def test_boolean_version_rejected(self):
        with self.assertRaises(ValueError): check(self.root,{'version':True})

    def test_determinism_and_manifest_not_mutated(self):
        manifest={'version':1,'scan_html':['review.html'],
                  'citations':[{'id':'a','source':'review.html','target':'source.html#one'}]}
        before=copy.deepcopy(manifest)
        self.assertEqual(check(self.root,manifest),check(self.root,manifest))
        self.assertEqual(manifest,before)


class RealPublishedIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'example'
        self.manifest=build(self.root)

    def test_actual_published_bytes_and_all_locators(self):
        snapshot=json.loads((HERE/'source_snapshot.json').read_text())
        for entry in snapshot['files']:
            data=(self.root/'sources'/entry['name']).read_bytes()
            self.assertEqual(hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest(),entry['git_blob'])
        report=check(self.root,self.manifest)
        self.assertEqual(report['verdict'],'VERIFIED',report)
        self.assertEqual((report['verified'],report['unresolved']),(19,0))

    def test_renamed_actual_bundle_break_is_visible(self):
        (self.root/'sources/évidence.html').rename(self.root/'sources/renamed.html')
        report=check(self.root,self.manifest)
        self.assertEqual(report['verdict'],'UNRESOLVED')
        self.assertEqual(report['counts']['MISSING_TARGET'],2)
        self.assertEqual(report['counts']['INSPECTION_ERROR'],1)

    def test_report_anchor_removed_is_visible(self):
        path=self.root/'sources/report.html'
        path.write_text(path.read_text().replace('id="L9"','id="old-L9"'))
        self.assertEqual(check(self.root,self.manifest)['counts']['MISSING_ANCHOR'],1)

    def test_builder_does_not_overwrite_existing_output(self):
        before=(self.root/'review.html').read_bytes()
        with self.assertRaises(ValueError): build(self.root)
        self.assertEqual((self.root/'review.html').read_bytes(),before)

    def test_cli_exit_codes_and_machine_readable_output(self):
        command=[sys.executable,str(HERE/'verify_bundle.py'),str(self.root),str(self.root/'citations.json')]
        completed=subprocess.run(command,capture_output=True,text=True,check=False)
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertEqual(json.loads(completed.stdout)['verified'],19)
        (self.root/'sources/report.html').unlink()
        self.assertEqual(subprocess.run(command,capture_output=True).returncode,1)
        (self.root/'citations.json').write_text('{broken')
        self.assertEqual(subprocess.run(command,capture_output=True).returncode,2)

    def test_example_rebuild_is_byte_identical(self):
        other=Path(self.tmp.name)/'other'
        build(other)
        names=sorted(p.relative_to(self.root) for p in self.root.rglob('*') if p.is_file())
        self.assertEqual(names,sorted(p.relative_to(other) for p in other.rglob('*') if p.is_file()))
        for name in names:
            self.assertEqual((self.root/name).read_bytes(),(other/name).read_bytes())


if __name__ == '__main__':
    unittest.main()

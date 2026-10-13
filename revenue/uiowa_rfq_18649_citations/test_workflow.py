"""Portable export, replay and canonical-component contract regressions."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from .canonical_093 import audit_rehearsal, read_csv
from .contract import CitationError, canonical, digest, load_json
from .export import build_files, check_links, write_new_bundle
from .integration import workshare_modules
from .resolver import Resolver
from .sample import make_sample


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'inputs'
        self.root.mkdir()
        self.packet, self.report = make_sample(self.root)

    def files(self):
        return build_files(Resolver(self.packet, self.report, self.root))[1]

    def test_exports_all_four_source_versions_without_mutating_inputs(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        files = self.files()
        originals = [name for name in files if name.startswith('original/')]
        self.assertEqual(len(originals), 4)
        self.assertIn('original/documents/iam-v2.md', files)
        self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes()
                                  for p in self.root.rglob('*') if p.is_file()})

    def test_two_operators_produce_identical_bytes(self):
        self.assertEqual(self.files(), self.files())

    def test_unpacked_bundle_replays_every_file_byte_exactly(self):
        out = self.root.parent / 'first'
        write_new_bundle(Resolver(self.packet, self.report, self.root), out)
        replay = build_files(Resolver(load_json(out / 'packet.json'),
                                     load_json(out / 'compiler-report.json'), out / 'original'))[1]
        original = {str(p.relative_to(out)): p.read_bytes() for p in out.rglob('*') if p.is_file()}
        self.assertEqual(replay, original)

    def test_manifest_binds_every_other_file(self):
        files = self.files()
        manifest = json.loads(files['manifest.json'])
        self.assertFalse(manifest['manifest_includes_itself'])
        self.assertEqual({row['path'] for row in manifest['files']}, set(files) - {'manifest.json'})
        for row in manifest['files']:
            self.assertEqual(row['bytes'], len(files[row['path']]))
            self.assertEqual(row['sha256'], digest(files[row['path']]))

    def test_all_exported_html_anchors_and_paths_exist(self):
        receipt = check_links(self.files())
        self.assertEqual(receipt['html_files_checked'], 5)
        self.assertGreater(receipt['internal_links_checked'], 20)
        self.assertEqual(receipt['broken_links'], 0)

    def test_unicode_hash_and_percent_filename_is_a_real_file_link(self):
        source = self.packet['sources'][0]
        alias = 'documents/Résumé #1 100% – notes.md'
        (self.root / source['path']).rename(self.root / alias)
        source['aliases'] = [alias]
        files = self.files()
        self.assertIn('original/' + alias, files)
        index = files['index.html'].decode()
        self.assertIn('%23', index)
        self.assertIn('%25', index)
        self.assertEqual(check_links(files)['broken_links'], 0)

    def test_broken_export_link_is_diagnosed(self):
        files = self.files()
        del files['original/documents/ess-release.md']
        with self.assertRaisesRegex(CitationError, 'Missing link target'):
            check_links(files)

    def test_duplicate_export_anchor_is_diagnosed(self):
        with self.assertRaisesRegex(CitationError, 'Duplicate HTML anchor'):
            check_links({'index.html': b'<p id="same"></p><p id="same"></p>'})

    def test_literal_markup_in_analyst_text_never_becomes_active_html(self):
        self.packet['findings'][0]['statement'] = '<script>alert("not executable")</script>'
        files = self.files()
        html = files['index.html'].decode()
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_new_destination_does_not_overwrite_previous_work(self):
        out = self.root.parent / 'existing'
        out.mkdir()
        sentinel = out / 'owner.txt'
        sentinel.write_text('keep', encoding='utf-8')
        with self.assertRaises(FileExistsError):
            write_new_bundle(Resolver(self.packet, self.report, self.root), out)
        self.assertEqual(sentinel.read_text(), 'keep')
        self.assertEqual(list(out.iterdir()), [sentinel])

    def test_recommendation_cannot_point_to_missing_finding(self):
        self.packet['recommendations'][0]['finding_ids'] = ['ABSENT']
        with self.assertRaisesRegex(CitationError, 'Recommendation'):
            self.files()

    def test_summary_cannot_point_to_missing_recommendation(self):
        self.packet['executive_summary']['recommendation_ids'] = ['ABSENT']
        with self.assertRaisesRegex(CitationError, 'Executive summary'):
            self.files()

    def test_duplicate_findings_do_not_overwrite(self):
        self.packet['findings'].append(copy.deepcopy(self.packet['findings'][0]))
        with self.assertRaisesRegex(CitationError, 'duplicate finding_id'):
            self.files()

    def test_recomputed_checksum_cannot_hide_semantic_report_edit(self):
        self.report['assessment_matrix'][0]['status'] = 'READY'
        _, _, core = workshare_modules()
        unsigned = {k: v for k, v in self.report.items() if k != 'receipt_sha256'}
        self.report['receipt_sha256'] = core._sha256_value(unsigned)
        self.packet['compiler_receipt_sha256'] = self.report['receipt_sha256']
        with self.assertRaisesRegex(ValueError, 'semantic recompile mismatch'):
            self.files()

    def test_returned_trace_does_not_mutate_resolver_snapshot(self):
        resolver = Resolver(self.packet, self.report, self.root)
        first = resolver.run()
        first['recommendations'].clear()
        first['assessment_matrix'].clear()
        first['external_authority']['contact_buyer'] = True
        second = resolver.run()
        self.assertEqual(len(second['recommendations']), 2)
        self.assertEqual(len(second['assessment_matrix']), 12)
        self.assertFalse(second['external_authority']['contact_buyer'])

    def test_json_duplicate_and_nonfinite_values_rejected(self):
        path = self.root / 'bad.json'
        for raw in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}']:
            path.write_text(raw, encoding='utf-8')
            with self.assertRaises(CitationError):
                load_json(path)

    def test_canonical_093_uses_actual_registers_and_does_not_invent_sources(self):
        upstream = Path(__file__).resolve().parent.parent / 'uiowa_rfq_18649_traceability_rehearsal'
        result = audit_rehearsal(upstream)
        self.assertEqual(result['existing_record_counts'],
                         {'evidence': 8, 'findings': 3, 'recommendations': 2, 'report_statements': 5})
        self.assertEqual(result['original_source_citations_asserted'], 0)
        self.assertEqual(len(result['requests']), 8)
        for request in result['requests']:
            self.assertIsNone(request['original_source_sha256'])
            self.assertIsNone(request['original_source_version'])
            self.assertTrue(request['affected_findings'])
            self.assertTrue(request['affected_statements'])
        self.assertEqual(result['requests'][0]['register_lines'], [2, 2])

    def test_csv_physical_locator_survives_multiline_field(self):
        path = self.root / 'rows.csv'
        path.write_text('id,text\nA,"one\ntwo"\nB,three\n', encoding='utf-8')
        rows, _ = read_csv(path)
        self.assertEqual(rows[0]['lines'], [2, 3])
        self.assertEqual(rows[1]['lines'], [4, 4])
        self.assertEqual(rows[0]['fields']['text'], 'one\ntwo')

    def test_duplicate_and_ragged_csv_headers_are_not_silently_accepted(self):
        path = self.root / 'bad.csv'
        for raw in ['id,id\nA,B\n', 'id,text\nA\n', 'id,text\nA,B,C\n']:
            path.write_text(raw, encoding='utf-8')
            with self.assertRaises(CitationError):
                read_csv(path)


if __name__ == '__main__':
    unittest.main()

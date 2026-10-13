"""Executable integration regressions for UIOWA-035. Synthetic data only."""
from __future__ import annotations
import contextlib
import copy
import csv
import io
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
import matrix_dataset as md


def specimen():
    m = md.Matrix.empty()
    for i, c in enumerate(m.ordered()[:9]):
        md.edit_cell(m, c.group, c.area, assessment_status=md.ASSESSED,
                     maturity_rank=i % 5 + 1, rationale='Synthetic rationale',
                     evidence_refs=['EV-SYN-1'], strengths=['Observed practice'])
    md.edit_cell(m, 'IAM', 'security', assessment_status=md.UNASSESSED,
                 follow_up_question='Which evidence resolves this?')
    md.edit_cell(m, 'IAM', 'deployment', assessment_status=md.NOT_APPLICABLE)
    md.edit_cell(m, 'IAM', 'AI', assessment_status=md.INSUFFICIENT_EVIDENCE,
                 follow_up_question='What is missing?')
    return m


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.m = specimen()

    def write_json(self, value):
        p = self.root / 'source.json'
        p.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return str(p)

    def csv_text(self, rows, header=None):
        s = io.StringIO(newline='')
        w = csv.DictWriter(s, fieldnames=header or md.CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)
        p = self.root / 'source.csv'
        p.write_bytes(s.getvalue().encode('utf-8'))
        return str(p)

    def roundtrip(self, matrix):
        for kind in ('json', 'csv'):
            p = str(self.root / ('out.' + kind))
            getattr(md, 'save_' + kind)(matrix, p)
            back = getattr(md, 'load_' + kind)(p)
            self.assertEqual([], md.round_trip_report(matrix, back), kind)
            self.assertEqual([], back.validate(), kind)
            self.assertEqual(md.to_json(matrix), md.to_json(back), kind)

    def test_specimen_has_twelve_cells_and_nine_assessed(self):
        self.assertEqual(12, len(self.m.cells))
        self.assertEqual(9, len(self.m.ranked_cells()))
        self.assertEqual([], self.m.validate())

    def test_all_nonrank_reasons_survive(self):
        self.roundtrip(self.m)
        for c in self.m.ordered():
            if c.assessment_status in md.NON_RANK_STATUSES:
                self.assertIsNone(c.maturity_rank)
                self.assertEqual('', c.maturity_label)

    def test_rank_one_is_distinct_from_unassessed(self):
        self.assertEqual(1, self.m.get('ESS', 'SD').maturity_rank)
        self.assertIsNone(self.m.get('IAM', 'SEC').maturity_rank)
        self.roundtrip(self.m)

    def test_semicolon_evidence_uri(self):
        self.m.get('ESS', 'SD').evidence_refs = ['https://example.invalid/evidence;revision=2']
        self.roundtrip(self.m)

    def test_all_list_fields_preserve_semicolons(self):
        for f in md.LIST_FIELDS:
            setattr(self.m.get('ESS', 'SD'), f, ['a;b', 'c;d'])
        self.roundtrip(self.m)

    def test_whitespace_empty_items_and_line_endings(self):
        self.m.get('ESS', 'SD').strengths = [' leading ', '', '\tTab', 'CR\rLF\nBoth\r\n']
        self.roundtrip(self.m)

    def test_quotes_commas_backslashes_and_unicode(self):
        self.m.get('ESS', 'SD').strengths = ['"quoted",text', '\\literal', 'Ünicode — 漢字', '🧪']
        self.roundtrip(self.m)

    def test_native_text_fields_are_not_trimmed(self):
        for f in ('rationale', 'scope_limit', 'follow_up_question'):
            setattr(self.m.get('ESS', 'SD'), f, '  retain\r\nthis\t ')
        self.roundtrip(self.m)

    def test_json_looking_legacy_list_is_not_sniffed(self):
        row = {f: '' for f in md.CELL_FIELDS}
        row.update(group='ESS', area='SD', assessment_status='unassessed',
                   follow_up_question='Question', strengths='["not", "an array"]')
        back = md.load_csv(self.csv_text([row], md.CELL_FIELDS))
        self.assertEqual(['["not", "an array"]'], back.get('ESS', 'SD').strengths)

    def test_legacy_semicolon_records_still_load(self):
        rows = []
        for cell in self.m.ordered():
            row = cell.to_row(); row.pop('list_encoding')
            for name in md.LIST_FIELDS:
                row[name] = ';'.join(getattr(cell, name))
            rows.append(row)
        back = md.load_csv(self.csv_text(rows, md.CELL_FIELDS))
        self.assertEqual([], md.round_trip_report(self.m, back))

    def test_csv_declares_encoding_on_every_record(self):
        p = md.save_csv(self.m, str(self.root / 'out.csv'))
        with open(p, newline='', encoding='utf-8') as s:
            rows = list(csv.DictReader(s))
        self.assertEqual({md.LIST_ENCODING}, {row['list_encoding'] for row in rows})
        self.assertTrue(all(isinstance(json.loads(row['evidence_refs']), list) for row in rows))

    def test_new_row_api_roundtrip(self):
        c = self.m.get('ESS', 'SD')
        self.assertEqual(c, md.Cell.from_row(c.to_row()))

    def test_boolean_rank_rejected(self):
        for value in (True, False):
            with self.subTest(value=value), self.assertRaises(md.DatasetError):
                md.Cell.from_row(dict(group='ESS', area='SD', maturity_rank=value))

    def test_fractional_rank_rejected(self):
        for value in (2.9, -1.4, 2.0, float('inf'), float('nan')):
            with self.subTest(value=value), self.assertRaises(md.DatasetError):
                md.Cell.from_row(dict(group='ESS', area='SD', maturity_rank=value))

    def test_rank_string_forms(self):
        for token, value in [(' 3 ', 3), ('+2', 2), ('01', 1), ('', None), ('  ', None)]:
            self.assertEqual(value, md.Cell.from_row(dict(group='ESS', area='SD', maturity_rank=token)).maturity_rank)
        for token in ['3.0', '2e0', 'True', 'n/a', '١', '9' * 5000]:
            with self.assertRaises(md.DatasetError):
                md.Cell.from_row(dict(group='ESS', area='SD', maturity_rank=token))

    def test_invalid_direct_rank_does_not_rank(self):
        for rank in (True, 1.0, 0, 6, [], {}):
            c = copy.deepcopy(self.m.get('ESS', 'SD')); c.maturity_rank = rank
            self.assertFalse(c.is_ranked())
            self.assertTrue(c.validate())

    def test_invalid_rank_edit_is_atomic(self):
        before = md.to_json(self.m)
        for rank in [True, 2.9, {}, 'n/a']:
            with self.assertRaises(md.DatasetError):
                md.edit_cell(self.m, 'ESS', 'SD', maturity_rank=rank)
            self.assertEqual(before, md.to_json(self.m))

    def test_invalid_list_edit_is_atomic(self):
        before = md.to_json(self.m)
        for value in [[None], [1], {'value': 'x'}, 3]:
            with self.assertRaises(md.DatasetError):
                md.edit_cell(self.m, 'ESS', 'SD', evidence_refs=value)
            self.assertEqual(before, md.to_json(self.m))

    def test_demote_discards_stale_rank(self):
        md.edit_cell(self.m, 'ESS', 'SD', assessment_status='unassessed', follow_up_question='Revisit')
        self.assertIsNone(self.m.get('ESS', 'SD').maturity_rank)
        self.roundtrip(self.m)

    def test_contradictory_edit_is_atomic(self):
        before = md.to_json(self.m)
        with self.assertRaises(md.DatasetError):
            md.edit_cell(self.m, 'ESS', 'SD', assessment_status='unassessed', maturity_rank=1)
        self.assertEqual(before, md.to_json(self.m))

    def test_label_derivation_retained(self):
        md.edit_cell(self.m, 'ESS', 'SD', maturity_rank=3, maturity_label='typed label')
        self.assertEqual('Practised', self.m.get('ESS', 'SD').maturity_label)

    def test_duplicate_json_row_refused(self):
        payload = md.to_json(self.m); payload['cells'].append(copy.deepcopy(payload['cells'][0]))
        with self.assertRaises(md.DatasetError):
            md.load_json(self.write_json(payload))

    def test_duplicate_alias_row_refused(self):
        payload = md.to_json(self.m); row = dict(payload['cells'][0], group='ess', area='SD')
        payload['cells'].append(row)
        with self.assertRaises(md.DatasetError):
            md.load_json(self.write_json(payload))

    def test_duplicate_csv_row_refused(self):
        rows = [c.to_row() for c in self.m.ordered()]; rows.append(dict(rows[0]))
        with self.assertRaises(md.DatasetError):
            md.load_csv(self.csv_text(rows))

    def test_duplicate_json_key_refused(self):
        p = self.root / 'source.json'; p.write_text('{"cells":[],"cells":[]}')
        with self.assertRaises(md.DatasetError):
            md.load_json(str(p))

    def test_bad_json_envelopes(self):
        for value in (None, [], {}, {'cells': None}, {'cells': 'data'}, {'cells': [None]}):
            with self.subTest(value=value), self.assertRaises(md.DatasetError):
                md.load_json(self.write_json(value))

    def test_nonfinite_json_rejected(self):
        for token in ('NaN', 'Infinity', '-Infinity'):
            p = self.root / 'source.json'; p.write_text('{"cells":[],"extra":' + token + '}')
            with self.assertRaises(md.DatasetError):
                md.load_json(str(p))

    def test_native_list_strings_are_not_silently_split(self):
        for value in ('a;b', None, {}, 1):
            payload = md.to_json(self.m); payload['cells'][0]['strengths'] = value
            with self.assertRaises(md.DatasetError):
                md.load_json(self.write_json(payload))

    def test_native_nontext_items_are_not_stringified(self):
        for value in [None, True, 2, {}]:
            payload = md.to_json(self.m); payload['cells'][0]['strengths'] = [value]
            with self.assertRaises(md.DatasetError):
                md.load_json(self.write_json(payload))

    def test_unknown_row_fields_refused(self):
        payload = md.to_json(self.m); payload['cells'][0]['overall_score'] = 0
        with self.assertRaises(md.DatasetError):
            md.load_json(self.write_json(payload))

    def test_native_json_cannot_smuggle_csv_encoding(self):
        payload = md.to_json(self.m); payload['cells'][0]['list_encoding'] = md.LIST_ENCODING
        with self.assertRaises(md.DatasetError):
            md.load_json(self.write_json(payload))

    def test_duplicate_csv_header_refused(self):
        p = self.root / 'source.csv'; p.write_text('group,group,area\nESS,RIS,SD\n')
        with self.assertRaises(md.DatasetError):
            md.load_csv(str(p))

    def test_missing_csv_column_refused(self):
        p = self.root / 'source.csv'; p.write_text('group,area\nESS,SD\n')
        with self.assertRaises(md.DatasetError):
            md.load_csv(str(p))

    def test_wrong_csv_record_width_refused(self):
        for suffix in ('ESS,SD\n', ','.join([''] * (len(md.CSV_FIELDS) + 1)) + '\n'):
            p = self.root / 'source.csv'; p.write_text(','.join(md.CSV_FIELDS) + '\n' + suffix)
            with self.assertRaises(md.DatasetError):
                md.load_csv(str(p))

    def test_bad_encoding_markers_refused(self):
        for marker in ('', 'legacy', 'json-array/v9'):
            row = self.m.get('ESS', 'SD').to_row(); row['list_encoding'] = marker
            with self.assertRaises(md.DatasetError):
                md.load_csv(self.csv_text([row]))

    def test_nonarray_encoded_csv_refused(self):
        for token in ('null', 'false', '1', '"text"', '{}', '[1]', 'not json'):
            row = self.m.get('ESS', 'SD').to_row(); row['strengths'] = token
            with self.assertRaises(md.DatasetError):
                md.load_csv(self.csv_text([row]))

    def test_reordered_csv_header_supported(self):
        back = md.load_csv(self.csv_text([c.to_row() for c in self.m.ordered()], list(reversed(md.CSV_FIELDS))))
        self.assertEqual([], md.round_trip_report(self.m, back))

    def test_csv_bom_supported(self):
        p = Path(self.csv_text([c.to_row() for c in self.m.ordered()]))
        p.write_bytes(b'\xef\xbb\xbf' + p.read_bytes())
        self.assertEqual([], md.round_trip_report(self.m, md.load_csv(str(p))))

    def test_export_validates_before_destination_write(self):
        for kind in ('json', 'csv'):
            p = self.root / ('out.' + kind); p.write_bytes(b'preserve original')
            bad = copy.deepcopy(self.m); del bad.cells[('ESS', 'security')]
            with self.assertRaises(md.DatasetError):
                getattr(md, 'save_' + kind)(bad, str(p))
            self.assertEqual(b'preserve original', p.read_bytes())

    def test_internal_key_mismatch_detected(self):
        self.m.get('ESS', 'SD').group = 'RIS'
        self.assertTrue(any('disagrees' in x for x in self.m.validate()))

    def test_invalid_text_validation_is_not_crash(self):
        for field in md.TEXT_FIELDS:
            c = copy.deepcopy(self.m.get('ESS', 'SD')); setattr(c, field, {})
            self.assertTrue(c.validate())

    def test_blank_evidence_cannot_support_assessed_cell(self):
        for links in [[], [''], ['  '], ['valid', '']]:
            c = copy.deepcopy(self.m.get('ESS', 'SD')); c.evidence_refs = links
            self.assertTrue(c.validate())

    def test_roundtrip_report_is_type_sensitive(self):
        back = copy.deepcopy(self.m); back.get('ESS', 'SD').maturity_rank = True
        self.assertTrue(any('maturity_rank' in s for s in md.round_trip_report(self.m, back)))

    def test_search_preserves_aliases_and_evidence_text(self):
        self.assertEqual(1, len(md.search(self.m, group='ess', area='software_development')))
        self.assertEqual(9, len(md.search(self.m, 'EV-SYN-1', ranked_only=True)))

    def test_direct_cli_accepts_both_encodings(self):
        for kind in ('csv', 'json'):
            path = getattr(md, 'save_' + kind)(self.m, str(self.root / ('in.' + kind)))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, md.main(['--dataset', path, '--validate', '--round-trip']))

    def test_cli_input_alias_preserved(self):
        path = md.save_json(self.m, str(self.root / 'in.json')); before = Path(path).read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, md.main(['--dataset', path, '--export-json', path]))
        self.assertEqual(before, Path(path).read_bytes())

    def test_cli_symlink_alias_preserved(self):
        path = md.save_json(self.m, str(self.root / 'in.json')); link = self.root / 'link.json'
        link.symlink_to(path); before = Path(path).read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, md.main(['--dataset', path, '--export-json', str(link)]))
        self.assertEqual(before, Path(path).read_bytes())

    def test_cli_hardlink_alias_preserved(self):
        path = md.save_json(self.m, str(self.root / 'in.json')); link = self.root / 'link.json'
        os.link(path, link); before = Path(path).read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, md.main(['--dataset', path, '--export-json', str(link)]))
        self.assertEqual(before, Path(path).read_bytes())

    def test_cli_exports_must_differ(self):
        path = md.save_json(self.m, str(self.root / 'in.json')); out = str(self.root / 'out')
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, md.main(['--dataset', path, '--export-json', out, '--export-csv', out]))
        self.assertFalse(Path(out).exists())

    def test_cli_missing_cells_cannot_export(self):
        payload = md.to_json(self.m); payload['cells'].pop(); path = self.write_json(payload)
        out = self.root / 'out.csv'
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(1, md.main(['--dataset', path, '--export-csv', str(out)]))
        self.assertFalse(out.exists())

    def test_real_cli_error_is_clean(self):
        p = self.root / 'bad.json'; p.write_text('{')
        args = [sys.executable] + (['-O'] if sys.flags.optimize else [])
        result = subprocess.run(args + [str(Path(md.__file__)), '--dataset', str(p)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(2, result.returncode)
        self.assertIn('dataset error:', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_deterministic_adversarial_panel(self):
        rng = random.Random(35019)
        alphabet = 'Ab; ,"\\\t\r\nÜ漢字🧪[]{}='
        for index in range(100):
            m = specimen()
            for field in md.LIST_FIELDS:
                strings = [''.join(rng.choice(alphabet) for _ in range(rng.randint(1, 30)))
                           for _ in range(rng.randint(1, 5))]
                if field == 'evidence_refs':
                    strings = ['EV-SYN-' + s for s in strings]
                setattr(m.get('ESS', 'SD'), field, strings)
            with self.subTest(index=index):
                self.roundtrip(m)


if __name__ == '__main__':
    unittest.main(verbosity=2)

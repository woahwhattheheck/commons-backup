"""Executable contract for the newsletter-production email handoff component."""
import copy
import csv
from email import policy
from email.parser import BytesParser
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from email_handoff import HandoffError, _load_packet, build_email_bundle, render_issue_html, write_packet


def packet():
    passages = [
        ('Start with a useful question', 'Before opening an interview, choose one question the reader actually has. Keep the answer attached to the speaker and the original passage, then write an introduction that explains why it matters.'),
        ('Keep the quote with its context', 'A quote is easier to edit when it carries a passage identifier and a timestamp. Return to that passage before changing a name or removing a qualification. Preserve the original wording alongside the edited copy.'),
        ('Make one issue do one job', 'Give each issue a distinct purpose. A source conversation can support an explanation, an example, a checklist and a reflection without pretending that every edition is a new interview.'),
        ('Hand off files that remain editable', 'Keep the interview notes, plain text, HTML and source references together. Use the client’s existing publishing platform for its actual sender, audience, preference footer and schedule. A local export is not a sent campaign.'),
    ]
    return {'publication': 'The Working Draft · original synthetic demo',
            'source_metadata': {'source_type': 'original_scripted_demo', 'customer_interview': False,
                                'audio_verified': False, 'source_revision': 'demo-1'},
            'issues': [{'id': f'week-{i}', 'subject': title, 'body': title + '\n\n' + body + '\n\nThe Working Draft',
                        'preheader': 'An original editorial example, not customer testimony.',
                        'scheduled_at': f'2026-09-{i * 7:02d}T09:00:00-05:00', 'source_refs': [f'demo:passage-{i}']}
                       for i, (title, body) in enumerate(passages, 1)]}


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.packet = packet()

    def bundle(self):
        return build_email_bundle(self.packet['issues'], publication=self.packet['publication'],
                                  source_metadata=self.packet['source_metadata'])

    def test_four_issue_bundle_has_twelve_editable_deliverables(self):
        with zipfile.ZipFile(io.BytesIO(self.bundle())) as z:
            self.assertEqual(len([name for name in z.namelist() if name.startswith('issues/')]), 12)
            manifest = json.loads(z.read('manifest.json'))
            self.assertEqual(manifest['delivery_state'], 'UNSENT_EXPORT')
            self.assertEqual(manifest['scheduling_state'], 'NOT_SCHEDULED')
            self.assertEqual(len(manifest['issues']), 4)
            self.assertEqual(len(set(i['subject'] for i in manifest['issues'])), 4)
            self.assertEqual(json.loads(z.read('source-metadata.json')), self.packet['source_metadata'])

    def test_text_bytes_exactly_preserve_unicode_and_line_endings(self):
        value = 'Café 日本語 العربية — résumé\r\nLine two\rA\n\n'
        self.packet['issues'][0]['body'] = value
        with zipfile.ZipFile(io.BytesIO(self.bundle())) as z:
            self.assertEqual(z.read('issues/01.txt'), value.encode('utf-8'))

    def test_mime_parts_roundtrip_with_no_fabricated_delivery_headers(self):
        self.packet['issues'][0]['subject'] = '日本語 & Café'
        with zipfile.ZipFile(io.BytesIO(self.bundle())) as z:
            message = BytesParser(policy=policy.default).parsebytes(z.read('issues/01.eml'))
            self.assertEqual(str(message['Subject']), '日本語 & Café')
            self.assertEqual(message['X-Unsent'], '1')
            for name in ('From', 'To', 'Cc', 'Bcc', 'Date', 'Message-ID'):
                self.assertIsNone(message[name])
            body = message.get_body(preferencelist=('plain',)).get_content()
            self.assertEqual(body.replace('\r\n', '\n'), self.packet['issues'][0]['body'] + '\n')
            self.assertIn('<!doctype html>', message.get_body(preferencelist=('html',)).get_content())
            self.assertFalse(message.defects)

    def test_html_treats_editorial_markup_as_literal_text(self):
        issue = self.packet['issues'][0]
        issue.update(subject='<script>alert(1)</script>', body='<img src=x onerror=alert(1)>\nA & B', preheader='</div><script>x</script>')
        rendered = render_issue_html(issue, publication='<b>Publication</b>')
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<img ', rendered)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', rendered)
        self.assertIn('&lt;b&gt;Publication&lt;/b&gt;', rendered)
        self.assertIn('A &amp; B', rendered)

    def test_header_newline_injection_rejected_not_silently_rewritten(self):
        for key in ('subject', 'preheader', 'id'):
            bad = copy.deepcopy(self.packet['issues'])
            bad[0][key] = 'Title\r\nBcc: nobody@example.invalid'
            with self.subTest(key=key), self.assertRaises(HandoffError):
                build_email_bundle(bad, publication='Demo')
        with self.assertRaises(HandoffError):
            build_email_bundle(self.packet['issues'], publication='Pub\nX: y')

    def test_schedule_normalizes_timezone_without_claiming_a_send(self):
        self.packet['issues'][0]['scheduled_at'] = '2026-09-08T09:15:00.123456-05:00'
        with zipfile.ZipFile(io.BytesIO(self.bundle())) as z:
            entry = json.loads(z.read('manifest.json'))['issues'][0]
            self.assertEqual(entry['scheduled_at'], '2026-09-08T14:15:00.123456Z')
            rows = list(csv.DictReader(io.StringIO(z.read('campaign-import.csv').decode('utf-8-sig'))))
            self.assertEqual(rows[0]['intended_send_at_utc'], entry['scheduled_at'])
            self.assertEqual(rows[0]['delivery_state'], 'UNSENT_EXPORT')

    def test_naive_malformed_and_overflow_schedules_rejected(self):
        for value in ['2026-09-08T09:00:00', 'not a time', '0001-01-01T00:00:00+23:00',
                      '9999-12-31T23:59:59-23:00', [], {}, True, 123]:
            self.packet['issues'][0]['scheduled_at'] = value
            with self.subTest(value=value), self.assertRaises(HandoffError):
                self.bundle()

    def test_empty_schedules_are_supported(self):
        for value in ('', None):
            self.packet['issues'][0]['scheduled_at'] = value
            with zipfile.ZipFile(io.BytesIO(self.bundle())) as z:
                self.assertEqual(json.loads(z.read('manifest.json'))['issues'][0]['scheduled_at'], '')

    def test_archive_paths_do_not_use_input_identifiers(self):
        self.packet['issues'][0]['id'] = '../../outside'
        with zipfile.ZipFile(io.BytesIO(self.bundle())) as z:
            self.assertFalse(any('..' in name or name.startswith('/') for name in z.namelist()))
            self.assertEqual(json.loads(z.read('manifest.json'))['issues'][0]['id'], '../../outside')

    def test_duplicate_ids_rejected(self):
        self.packet['issues'][1]['id'] = self.packet['issues'][0]['id']
        with self.assertRaises(HandoffError):
            self.bundle()

    def test_csv_formula_prefix_is_inert_original_manifest_unchanged(self):
        self.packet['issues'][0]['subject'] = '  =1+1'
        self.packet['issues'][0]['id'] = '+first'
        with zipfile.ZipFile(io.BytesIO(self.bundle())) as z:
            rows = list(csv.DictReader(io.StringIO(z.read('campaign-import.csv').decode('utf-8-sig'))))
            self.assertEqual(rows[0]['subject'], "'  =1+1")
            self.assertEqual(rows[0]['issue_id'], "'+first")
            self.assertEqual(json.loads(z.read('manifest.json'))['issues'][0]['subject'], '  =1+1')

    def test_manifest_hashes_cover_exact_artifacts_and_references(self):
        with zipfile.ZipFile(io.BytesIO(self.bundle())) as z:
            manifest = json.loads(z.read('manifest.json'))
            for index, issue in enumerate(manifest['issues']):
                self.assertEqual(issue['source_refs'], self.packet['issues'][index]['source_refs'])
                for name, digest in issue['sha256'].items():
                    self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(), digest)

    def test_repeated_export_is_deterministic_and_does_not_mutate_inputs(self):
        before = copy.deepcopy(self.packet)
        self.assertEqual(self.bundle(), self.bundle())
        self.assertEqual(self.packet, before)

    def test_invalid_input_shapes_and_text_contract(self):
        for value in (None, {}, [], [None], [{'id': [], 'subject': 'x', 'body': 'y'}], self.packet['issues'] * 14):
            with self.subTest(value=str(value)[:50]), self.assertRaises(HandoffError):
                build_email_bundle(value, publication='Demo')
        for key, value in [('body', ''), ('body', 'bad\ud800'), ('body', '\x00bad'), ('subject', []),
                           ('source_refs', 'passage'), ('source_refs', [{}]), ('preheader', False)]:
            issues = copy.deepcopy(self.packet['issues'])
            issues[0][key] = value
            with self.subTest(key=key, value=repr(value)), self.assertRaises(HandoffError):
                build_email_bundle(issues, publication='Demo')

    def test_metadata_rejects_non_json_and_nonfinite_numbers(self):
        for metadata in [[], {'bad': float('inf')}, {'bad': float('nan')}, {'bad': object()}, {'bad': '\udfff'}]:
            with self.subTest(metadata=repr(metadata)), self.assertRaises(HandoffError):
                build_email_bundle(self.packet['issues'], publication='Demo', source_metadata=metadata)

    def test_cli_parser_rejects_duplicate_keys_and_exponent_overflow(self):
        for raw in ['{"publication":"a","publication":"b"}', '{"x":1e400}', '{"x":NaN}', '[]', '[' * 2000]:
            with self.subTest(raw=raw[:50]), self.assertRaises(HandoffError):
                _load_packet(raw)
        self.assertEqual(_load_packet(json.dumps(self.packet)), self.packet)

    def test_real_cli_emits_zip_and_truthful_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'packet.json').write_text(json.dumps(self.packet), encoding='utf-8')
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('email_handoff.py')),
                                     str(path / 'packet.json'), '--output', str(path / 'month.zip')],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('UNSENT_EXPORT; NOT_SCHEDULED', result.stdout)
            with zipfile.ZipFile(path / 'month.zip') as z:
                self.assertIn('issues/04.eml', z.namelist())
            self.assertEqual(list(path.glob('.email-handoff-*')), [])

    def test_invalid_packet_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'month.zip'
            output.write_bytes(b'existing handoff')
            bad = copy.deepcopy(self.packet)
            bad['issues'][0]['scheduled_at'] = '2026-09-08'
            with self.assertRaises(HandoffError):
                write_packet(bad, output)
            self.assertEqual(output.read_bytes(), b'existing handoff')
            self.assertEqual(list(Path(tmp).glob('.email-handoff-*')), [])
            write_packet(self.packet, output)
            self.assertEqual(output.read_bytes(), self.bundle())


if __name__ == '__main__':
    unittest.main(verbosity=2)

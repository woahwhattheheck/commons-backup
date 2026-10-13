"""RFC 2046 boundary regressions, including explicitly forced collision branches."""
from email import policy
from email.parser import BytesParser
import io
import re
import unittest
from unittest.mock import patch
import zipfile

from email_handoff import HandoffError, _email, build_email_bundle, render_issue_html
from test_email_handoff import packet


class BoundaryTests(unittest.TestCase):
    def test_all_exported_boundaries_obey_rfc2046(self):
        data = packet()
        archive = build_email_bundle(data['issues'], publication=data['publication'])
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            for name in ('issues/01.eml', 'issues/02.eml', 'issues/03.eml', 'issues/04.eml'):
                with self.subTest(name=name):
                    message = BytesParser(policy=policy.default).parsebytes(z.read(name))
                    boundary = message.get_boundary()
                    self.assertGreater(len(boundary), 0)
                    self.assertLessEqual(len(boundary), 70)
                    self.assertIsNotNone(re.fullmatch(r"[0-9A-Za-z'()+_,./:=? -]+", boundary))
                    self.assertFalse(boundary.endswith(' '))
                    self.assertTrue(boundary.isascii())

    def test_wire_delimiters_match_the_parsed_header(self):
        issue = packet()['issues'][0]
        rendered = render_issue_html(issue, publication='Wire example')
        wire = _email(issue, rendered)
        message = BytesParser(policy=policy.default).parsebytes(wire)
        marker = b'--' + message.get_boundary().encode('ascii')
        delimiters = [line for line in wire.split(b'\r\n') if line.startswith(marker)]
        self.assertEqual(delimiters, [marker, marker, marker + b'--'])
        self.assertEqual(len(list(message.iter_parts())), 2)
        self.assertFalse(message.defects)

    def test_unicode_and_boundary_like_content_roundtrip(self):
        issue = packet()['issues'][0]
        issue['body'] = 'Café 日本語 العربية\n--newsletter-handoff-' + 'c' * 40 + '-000\nLiteral source.'
        rendered = render_issue_html(issue, publication='Original demo')
        message = BytesParser(policy=policy.default).parsebytes(_email(issue, rendered))
        self.assertEqual(message.get_body(preferencelist=('plain',)).get_content().replace('\r\n', '\n'),
                         issue['body'] + '\n')
        self.assertEqual(message.get_body(preferencelist=('html',)).get_content().replace('\r\n', '\n'),
                         rendered)
        self.assertFalse(message.defects)

    def test_repeated_serialization_remains_deterministic(self):
        issue = packet()['issues'][0]
        rendered = render_issue_html(issue, publication='Repeat example')
        first = _email(issue, rendered)
        self.assertEqual(first, _email(issue, rendered))
        changed = dict(issue, id='another-issue')
        old_boundary = BytesParser(policy=policy.default).parsebytes(first).get_boundary()
        new_boundary = BytesParser(policy=policy.default).parsebytes(_email(changed, rendered)).get_boundary()
        self.assertNotEqual(old_boundary, new_boundary)

    def test_forced_collisions_choose_a_short_distinct_candidate(self):
        # A fixed digest deliberately exercises a rare branch; this is not a real hash collision.
        issue = packet()['issues'][0]
        prefix = 'newsletter-handoff-' + 'a' * 40 + '-'
        issue['body'] = '--' + prefix + '000\nRetain this exact source.'
        rendered = '<p>' + prefix + '001</p>\n'
        with patch('email_handoff.hashlib.sha256') as digest:
            digest.return_value.hexdigest.return_value = 'a' * 64
            wire = _email(issue, rendered)
        message = BytesParser(policy=policy.default).parsebytes(wire)
        self.assertEqual(message.get_boundary(), prefix + '002')
        self.assertLessEqual(len(message.get_boundary()), 70)
        self.assertEqual(len(list(message.iter_parts())), 2)
        self.assertEqual(message.get_body(preferencelist=('plain',)).get_content().replace('\r\n', '\n'),
                         issue['body'] + '\n')

    def test_forced_candidate_exhaustion_returns_a_domain_error(self):
        # All 1000 candidates are deliberately occupied using a controlled digest.
        issue = packet()['issues'][0]
        prefix = 'newsletter-handoff-' + 'a' * 40 + '-'
        issue['body'] = '\n'.join(prefix + f'{index:03d}' for index in range(1000))
        with patch('email_handoff.hashlib.sha256') as digest:
            digest.return_value.hexdigest.return_value = 'a' * 64
            with self.assertRaises(HandoffError):
                _email(issue, '<p>Original example</p>\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)

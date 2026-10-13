"""Boundary tests for the conservative all-or-none compatibility candidate.

These supplement, but do not alter, CAESURA's ten independent acceptance cases.
They describe this candidate's withholding policy, not every valid MCE adapter.
"""
from pathlib import Path
import tempfile
import unittest

if __package__:
    from . import extract
    from .test_extraction_alternatives import alternatives, package
else:
    import extract
    from test_extraction_alternatives import alternatives, package


def run(text):
    return '<w:r><w:t>' + text + '</w:t></w:r>'


def heading(content):
    return '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>' + content + '</w:p>'


class TestAlternateBoundaries(unittest.TestCase):
    def result(self, body):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fictional.docx'
            source = package(body)
            path.write_bytes(source)
            result = extract.extract(path)
            self.assertEqual(path.read_bytes(), source)
            return result

    def test_withholding_does_not_join_words_around_gap(self):
        result = self.result('<w:p>' + run('not') + alternatives() + run('approved') + '</w:p>')
        self.assertEqual(result['status'], 'unreadable')
        self.assertEqual(result['segments'][0]['text'], '')
        self.assertEqual(result['segments'][0]['locator'], 'paragraph 1')
        self.assertTrue(result['segments'][0]['warnings'])

    def test_unresolved_heading_does_not_inherit_previous_section(self):
        result = self.result(heading(run('Prior section')) + heading(alternatives())
                             + '<w:p>' + run('Following evidence.') + '</w:p>')
        current = result['segments'][-1]
        self.assertEqual(current['text'], 'Following evidence.')
        self.assertEqual(current['heading_path'], ['(unresolved heading)'])

    def test_clean_heading_after_ambiguity_restores_known_context(self):
        result = self.result(heading(alternatives()) + heading(run('Known section'))
                             + '<w:p>' + run('Following evidence.') + '</w:p>')
        self.assertEqual(result['segments'][-1]['heading_path'], ['Known section'])

    def test_content_control_retains_full_warning_locator(self):
        result = self.result('<w:sdt><w:sdtContent><w:p>' + alternatives()
                             + '</w:p></w:sdtContent></w:sdt>')
        segment = result['segments'][0]
        self.assertEqual(segment['locator'], 'sdt 1/sdtContent/paragraph 1')
        self.assertTrue(any(segment['locator'] in w for w in segment['warnings']))

    def test_ambiguous_table_is_not_a_partial_quotation(self):
        result = self.result('<w:tbl><w:tr><w:tc><w:p>' + alternatives()
                             + '</w:p></w:tc><w:tc><w:p>' + run('Clean neighbor')
                             + '</w:p></w:tc></w:tr></w:tbl>')
        self.assertEqual(result['segments'][0]['text'], '')
        self.assertTrue(any('table 1' in w and 'ALTERNATE' in w for w in result['warnings']))

    def test_deleted_alternatives_do_not_erase_current_text(self):
        result = self.result('<w:p><w:del w:id="1">' + alternatives()
                             + '</w:del>' + run('Current evidence.') + '</w:p>')
        self.assertEqual(result['segments'][0]['text'], 'Current evidence.')
        self.assertFalse(any('ALTERNATE' in w for w in result['warnings']))

    def test_omitted_drawing_alternatives_do_not_erase_body_prose(self):
        result = self.result('<w:p><w:drawing>' + alternatives() + '</w:drawing>'
                             + run('Current evidence.') + '</w:p>')
        self.assertEqual(result['segments'][0]['text'], 'Current evidence.')
        self.assertTrue(any('DRAWING' in w for w in result['warnings']))

    def test_clean_paragraph_keeps_known_section_around_withheld_prose(self):
        result = self.result(heading(run('Known section')) + '<w:p>' + alternatives()
                             + '</w:p><w:p>' + run('Later evidence.') + '</w:p>')
        self.assertEqual(result['segments'][-1]['heading_path'], ['Known section'])
        self.assertEqual(result['segments'][-1]['locator'], 'paragraph 3')


if __name__ == '__main__':
    unittest.main()

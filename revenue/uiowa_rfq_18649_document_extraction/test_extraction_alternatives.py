"""Independent regression cases for source-fidelity review of Commons #16309.

All inputs are fictional OOXML snippets. This is not a renderer test.
"""
from pathlib import Path
import hashlib
import io
import tempfile
import unittest
import zipfile

if __package__:
    from . import extract
else:
    import extract

MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'


def package(body):
    document = (
        f'<w:document xmlns:w="{extract.W_NS}" xmlns:mc="{MC}" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml">'
        f'<w:body>{body}</w:body></w:document>'
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('word/document.xml', document)
    return output.getvalue()


def alternatives():
    return ('<mc:AlternateContent>'
            '<mc:Choice Requires="w14"><w:r><w:t>APPROVED</w:t></w:r></mc:Choice>'
            '<mc:Fallback><w:r><w:t>DECLINED</w:t></w:r></mc:Fallback>'
            '</mc:AlternateContent>')


class TestAlternateContentFidelity(unittest.TestCase):
    def result(self, body):
        raw = package(body)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fictional.docx'
            path.write_bytes(raw)
            result = extract.extract(path)
            self.assertEqual(result['document']['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(path.read_bytes(), raw)
            return result

    def test_paragraph_does_not_join_mutually_exclusive_alternatives(self):
        result = self.result('<w:p>' + alternatives() + '</w:p>')
        text = '\n'.join(item['text'] for item in result['segments'])
        self.assertNotIn('APPROVEDDECLINED', text)
        self.assertTrue(any('ALTERNATE' in warning.upper() for warning in result['warnings']), result)

    def test_heading_does_not_propagate_a_synthetic_alternative_title(self):
        result = self.result('<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
                             + alternatives() + '</w:p><w:p><w:r><w:t>Following evidence.</w:t></w:r></w:p>')
        for segment in result['segments']:
            self.assertNotIn('APPROVEDDECLINED', segment['text'])
            self.assertNotIn('APPROVEDDECLINED', segment['heading_path'])
        self.assertTrue(any(item['text'] == 'Following evidence.' for item in result['segments']))

    def test_table_cell_does_not_join_alternatives(self):
        result = self.result('<w:tbl><w:tr><w:tc><w:p>' + alternatives()
                             + '</w:p></w:tc></w:tr></w:tbl>')
        for segment in result['segments']:
            self.assertNotIn('APPROVEDDECLINED', segment['text'])

    def test_plain_supported_paragraph_is_preserved(self):
        result = self.result('<w:p><w:r><w:t>Unambiguous evidence.</w:t></w:r></w:p>')
        self.assertEqual(result['segments'][0]['text'], 'Unambiguous evidence.')
        self.assertEqual(result['segments'][0]['locator'], 'paragraph 1')


if __name__ == '__main__':
    unittest.main()

"""Independent synthetic regressions: non-breaking hyphens are text, not metadata."""
from pathlib import Path
import io
import tempfile
import unittest
import zipfile

if __package__:
    from . import extract
else:
    import extract


def _package(body):
    xml = f'<w:document xmlns:w="{extract.W_NS}"><w:body>{body}</w:body></w:document>'
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('word/document.xml', xml)
    return stream.getvalue()


class TestRunCharacters(unittest.TestCase):
    def result(self, body):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'fictional.docx'
            source.write_bytes(_package(body))
            return extract.extract(source)

    def hyphen_run(self):
        return '<w:r><w:t>re</w:t><w:noBreakHyphen/><w:t>sign</w:t></w:r>'

    def assert_hyphen_preserved(self, text):
        # Accept the displayed hyphen-minus or Unicode non-breaking equivalent.
        self.assertIn(text, ('re-sign', 're\u2011sign'))

    def test_paragraph_keeps_nonbreaking_hyphen(self):
        result = self.result('<w:p>' + self.hyphen_run() + '</w:p>')
        self.assert_hyphen_preserved(result['segments'][0]['text'])

    def test_heading_keeps_hyphen_in_following_context(self):
        result = self.result('<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
                             + self.hyphen_run() + '</w:p><w:p><w:r><w:t>Evidence.</w:t></w:r></w:p>')
        self.assert_hyphen_preserved(result['segments'][1]['heading_path'][0])

    def test_table_keeps_nonbreaking_hyphen(self):
        result = self.result('<w:tbl><w:tr><w:tc><w:p>' + self.hyphen_run()
                             + '</w:p></w:tc></w:tr></w:tbl>')
        self.assert_hyphen_preserved(result['segments'][0]['text'])

    def test_inserted_run_keeps_nonbreaking_hyphen(self):
        result = self.result('<w:p><w:ins w:id="1">' + self.hyphen_run() + '</w:ins></w:p>')
        self.assert_hyphen_preserved(result['segments'][0]['text'])

    def test_deleted_run_is_still_omitted(self):
        result = self.result('<w:p><w:del w:id="1">' + self.hyphen_run()
                             + '</w:del><w:r><w:t>Current.</w:t></w:r></w:p>')
        self.assertEqual(result['segments'][0]['text'], 'Current.')

    def test_existing_tabs_and_breaks_are_preserved(self):
        result = self.result('<w:p><w:r><w:t>A</w:t><w:tab/><w:t>B</w:t>'
                             '<w:br/><w:t>C</w:t><w:cr/><w:t>D</w:t></w:r></w:p>')
        self.assertEqual(result['segments'][0]['text'], 'A\tB\nC\nD')


if __name__ == '__main__':
    unittest.main()

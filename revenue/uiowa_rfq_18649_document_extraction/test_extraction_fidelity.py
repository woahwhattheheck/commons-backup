"""Synthetic, local-only regression cases for document source and locator fidelity."""
from __future__ import annotations

import contextlib
import hashlib
import io
import importlib.util
import sys
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import extract
import make_synthetic_corpus

NS = extract.W_NS


def paragraph(text: str, properties: str = "") -> str:
    from xml.sax.saxutils import escape
    return f'<w:p>{properties}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def docx(path: Path, body: str, styles: str | None = None, extras: dict | None = None) -> Path:
    # Preserve the original carrier's minimal package structure.
    make_synthetic_corpus._write_minimal_docx(path)
    with zipfile.ZipFile(path) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    parts['word/document.xml'] = (
        f'<w:document xmlns:w="{NS}"><w:body>{body}<w:sectPr/></w:body></w:document>'
    ).encode()
    if styles is not None:
        parts['word/styles.xml'] = f'<w:styles xmlns:w="{NS}">{styles}</w:styles>'.encode()
    parts.update(extras or {})
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in parts.items():
            z.writestr(name, content)
    return path


class FidelityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def text_file(self, text: str, name: str = 'fixture.md') -> Path:
        path = self.root / name
        path.write_text(text, encoding='utf-8')
        return path

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = extract.main([str(a) for a in args])
        return code, json.loads(output.getvalue()) if output.getvalue() else None

    def test_source_is_opened_once_and_digest_matches_text(self):
        content = '# Synthetic source\nOriginal evidence.\n'
        path = self.text_file(content)
        original_open = Path.open
        source_reads = []

        def count_reads(p, *args, **kwargs):
            mode = args[0] if args else kwargs.get('mode', 'r')
            if p == path and 'r' in mode:
                source_reads.append(mode)
            return original_open(p, *args, **kwargs)

        with patch.object(Path, 'open', count_reads):
            result = extract.extract(path)
        self.assertEqual(len(source_reads), 1)
        self.assertEqual(result['document']['bytes'], len(content.encode()))
        self.assertEqual(result['document']['sha256'], hashlib.sha256(content.encode()).hexdigest())
        self.assertIn('Original evidence.', result['segments'][-1]['text'])

    def test_cli_refuses_same_input_output_without_changing_source(self):
        path = self.text_file('# Synthetic source\nPreserve this evidence.\n')
        before = path.read_bytes()
        code, result = self.cli(path, '-o', path)
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(path.read_bytes(), before)

    def test_cli_refuses_existing_report_without_changing_it(self):
        path = self.text_file('# Synthetic source\nEvidence.\n')
        output = self.root / 'report.json'
        output.write_bytes(b'previous report\n')
        code, result = self.cli(path, '-o', output)
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(output.read_bytes(), b'previous report\n')

    def test_cli_output_alias_cannot_overwrite_source(self):
        path = self.text_file('Fictional evidence.\n')
        alias = self.root / 'report.json'
        try:
            os.link(path, alias)
        except OSError as exc:
            self.skipTest(f'hard links unsupported: {type(exc).__name__}')
        code, result = self.cli(path, '-o', alias)
        self.assertEqual(code, 2)
        self.assertEqual(path.read_text(), 'Fictional evidence.\n')

    def test_cli_io_failure_has_structured_error(self):
        path = self.text_file('Fictional evidence.\n')
        code, result = self.cli(path, '-o', self.root / 'missing' / 'report.json')
        self.assertEqual(code, 2)
        self.assertEqual(result['status'], 'error')
        self.assertIn('OUTPUT_', result['error'])

    def test_new_output_succeeds_and_is_machine_readable(self):
        path = self.text_file('Fictional evidence.\n')
        output = self.root / 'new-report.json'
        code, result = self.cli(path, '-o', output)
        self.assertEqual(code, 0)
        self.assertIsNone(result)
        self.assertEqual(json.loads(output.read_text())['segments'][0]['text'], 'Fictional evidence.')

    def test_backtick_fence_preserves_section_and_code(self):
        path = self.text_file('# Actual heading\n```python\n# not a heading\nprint(1)\n```\nAfter code.\n')
        result = extract.extract(path)
        self.assertEqual([s['text'] for s in result['segments'] if s['kind'] == 'heading'], ['Actual heading'])
        body = result['segments'][-1]
        self.assertEqual(body['heading_path'], ['Actual heading'])
        self.assertIn('# not a heading', body['text'])
        self.assertEqual(body['locator'], 'lines 2-6')

    def test_tilde_fence_and_shorter_close_do_not_create_headings(self):
        path = self.text_file('# Root\n~~~~ text\n# inside\n~~~\n## still inside\n~~~~\n## Outside\n')
        result = extract.extract(path)
        self.assertEqual([s['text'] for s in result['segments'] if s['kind'] == 'heading'], ['Root', 'Outside'])

    def test_unclosed_fence_is_explicit(self):
        result = extract.extract(self.text_file('# Root\n```\n# literal\n'))
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(any('UNCLOSED_FENCE' in w for w in result['warnings']))
        self.assertEqual(result['segments'][-1]['heading_path'], ['Root'])

    def test_markdown_closing_hashes_are_not_heading_text(self):
        result = extract.extract(self.text_file('   ## Real title ##  \ncontent\n'))
        heading = result['segments'][0]
        self.assertEqual(heading['kind'], 'heading')
        self.assertEqual(heading['text'], 'Real title')
        self.assertEqual(heading['locator'], 'line 1')

    def test_body_whitespace_and_locator_match_source_lines(self):
        result = extract.extract(self.text_file('# Root\n\n  Preserve indentation.  \n\n'))
        body = result['segments'][-1]
        self.assertEqual(body['text'], '  Preserve indentation.  ')
        self.assertEqual(body['locator'], 'lines 3-3')

    def test_content_control_preserves_text_and_source_location(self):
        body = paragraph('Before') + '<w:sdt><w:sdtContent>' + paragraph('Inside control') + '</w:sdtContent></w:sdt>' + paragraph('After')
        result = extract.extract(docx(self.root / 'control.docx', body))
        self.assertEqual([s['text'] for s in result['segments']], ['Before', 'Inside control', 'After'])
        self.assertIn('sdt 1', result['segments'][1]['locator'])
        # Existing direct-body paragraph numbering is stable, not silently shifted.
        self.assertEqual(result['segments'][2]['locator'], 'paragraph 2')

    def test_nested_custom_xml_wrapper_keeps_order(self):
        body = '<w:customXml><w:sdt><w:sdtContent>' + paragraph('Nested evidence') + '</w:sdtContent></w:sdt></w:customXml>'
        result = extract.extract(docx(self.root / 'nested.docx', body))
        self.assertEqual(result['segments'][0]['text'], 'Nested evidence')
        self.assertIn('customXml 1', result['segments'][0]['locator'])

    def test_custom_style_inherits_heading_outline(self):
        styles = '<w:style w:type="paragraph" w:styleId="BaseTitle"><w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style><w:style w:type="paragraph" w:styleId="LocalTitle"><w:basedOn w:val="BaseTitle"/></w:style>'
        body = paragraph('Service operations', '<w:pPr><w:pStyle w:val="LocalTitle"/></w:pPr>') + paragraph('Retained context')
        result = extract.extract(docx(self.root / 'styles.docx', body, styles))
        self.assertEqual(result['segments'][0]['kind'], 'heading')
        self.assertEqual(result['segments'][1]['heading_path'], ['Service operations'])

    def test_direct_outline_can_cancel_heading_style(self):
        body = paragraph('Ordinary paragraph', '<w:pPr><w:pStyle w:val="Heading1"/><w:outlineLvl w:val="9"/></w:pPr>')
        result = extract.extract(docx(self.root / 'body-style.docx', body))
        self.assertEqual(result['segments'][0]['kind'], 'paragraph')

    def test_unrelated_style_name_is_not_heading(self):
        body = paragraph('Not a title', '<w:pPr><w:pStyle w:val="NotAHeading1"/></w:pPr>')
        result = extract.extract(docx(self.root / 'style-name.docx', body))
        self.assertEqual(result['segments'][0]['kind'], 'paragraph')

    def test_empty_table_is_not_evidence_text(self):
        body = '<w:tbl><w:tr><w:tc><w:p/></w:tc><w:tc><w:p/></w:tc></w:tr></w:tbl>'
        result = extract.extract(docx(self.root / 'empty-table.docx', body))
        self.assertEqual(result['status'], 'unreadable')
        self.assertFalse(any(s['text'].strip() for s in result['segments']))

    def test_tracked_revisions_have_explicit_text_view(self):
        body = '<w:p><w:moveFrom>' + '<w:r><w:t>Moved-from duplicate.</w:t></w:r></w:moveFrom><w:moveTo><w:r><w:t>Current text.</w:t></w:r></w:moveTo></w:p>'
        result = extract.extract(docx(self.root / 'revisions.docx', body))
        self.assertEqual(result['segments'][0]['text'], 'Current text.')
        self.assertTrue(any('TRACKED_CHANGES' in w for w in result['warnings']))

    def test_non_body_parts_are_explicit_limitations(self):
        header = f'<w:hdr xmlns:w="{NS}">{paragraph("Header only evidence")}</w:hdr>'.encode()
        result = extract.extract(docx(self.root / 'header.docx', paragraph('Body text'), extras={'word/header1.xml': header}))
        self.assertTrue(any('word/header1.xml' in w for w in result['warnings']))
        self.assertNotIn('Header only evidence', ' '.join(s['text'] for s in result['segments']))

    @unittest.skipUnless(importlib.util.find_spec("pypdf") is not None, "PDF integration requires pypdf>=6,<7")
    def test_pdf_snapshot_has_actual_page_text_and_original_digest(self):
        path = self.root / 'synthetic.pdf'
        make_synthetic_corpus._write_minimal_pdf(path, ['Synthetic first page.', 'Synthetic second page.'])
        before = path.read_bytes()
        result = extract.extract(path)
        self.assertEqual(result['document']['sha256'], hashlib.sha256(before).hexdigest())
        self.assertTrue(any(s['locator'].startswith('page 2') and 'second page' in s['text'] for s in result['segments']))

    def test_small_input_limit_applies_to_actual_bytes(self):
        path = self.text_file('Synthetic evidence longer than limit.')
        with patch.object(extract, 'MAX_BYTES', 8):
            with self.assertRaises(extract.ExtractionError):
                extract.extract(path)

    def test_public_helper_apis_remain_path_based(self):
        path = self.text_file('# Root\nSynthetic evidence.\n')
        segments, warnings = extract.extract_text(path)
        self.assertEqual(segments[-1].heading_path, ['Root'])
        self.assertEqual(warnings, [])
        self.assertEqual(extract.sha256_file(path), hashlib.sha256(path.read_bytes()).hexdigest())

    def test_direct_outline_level_preserves_context(self):
        body = paragraph('Direct title', '<w:pPr><w:outlineLvl w:val="1"/></w:pPr>') + paragraph('Direct context')
        result = extract.extract(docx(self.root / 'outline.docx', body))
        self.assertEqual(result['segments'][0]['kind'], 'heading')
        self.assertEqual(result['segments'][1]['heading_path'], ['(untitled)', 'Direct title'])

    def test_cyclic_styles_do_not_invent_heading(self):
        styles = '<w:style w:styleId="A"><w:basedOn w:val="B"/></w:style><w:style w:styleId="B"><w:basedOn w:val="A"/></w:style>'
        body = paragraph('Unresolved style', '<w:pPr><w:pStyle w:val="A"/></w:pPr>')
        result = extract.extract(docx(self.root / 'cycle.docx', body, styles))
        self.assertEqual(result['segments'][0]['kind'], 'paragraph')
        self.assertTrue(any('STYLE_INHERITANCE_CYCLE' in w for w in result['warnings']))

    def test_drawing_is_not_silently_merged_into_paragraph(self):
        body = '<w:p><w:r><w:t>Body text</w:t><w:drawing><w:txbxContent>' + paragraph('Text box') + '</w:txbxContent></w:drawing></w:r></w:p>'
        result = extract.extract(docx(self.root / 'drawing.docx', body))
        self.assertEqual(result['segments'][0]['text'], 'Body text')
        self.assertTrue(any('DRAWING_OR_EMBEDDED' in w for w in result['warnings']))

    def test_deleted_body_block_not_accepted_and_insertion_retained(self):
        body = '<w:del>' + paragraph('Old body') + '</w:del><w:ins>' + paragraph('Current body') + '</w:ins>'
        result = extract.extract(docx(self.root / 'body-revision.docx', body))
        self.assertEqual([s['text'] for s in result['segments']], ['Current body'])
        self.assertTrue(any('TRACKED_CHANGES' in w for w in result['warnings']))

    @unittest.skipUnless(importlib.util.find_spec("pypdf") is not None, "PDF integration requires pypdf>=6,<7")
    def test_pdf_backend_receives_snapshot_not_source_path(self):
        import pypdf
        path = self.root / 'snapshot.pdf'
        make_synthetic_corpus._write_minimal_pdf(path, ['Synthetic byte snapshot.'])
        with patch.object(pypdf, 'PdfReader', wraps=pypdf.PdfReader) as backend:
            result = extract.extract(path)
        source = backend.call_args.args[0]
        self.assertIsInstance(source, io.BytesIO)
        self.assertEqual(hashlib.sha256(source.getvalue()).hexdigest(), result['document']['sha256'])

    def test_docx_backend_receives_snapshot_not_source_path(self):
        path = docx(self.root / 'snapshot.docx', paragraph('Synthetic snapshot'))
        with patch.object(zipfile, 'ZipFile', wraps=zipfile.ZipFile) as backend:
            result = extract.extract(path)
        source = backend.call_args.args[0]
        self.assertIsInstance(source, io.BytesIO)
        self.assertEqual(hashlib.sha256(source.getvalue()).hexdigest(), result['document']['sha256'])

    def test_directory_rejected_before_open(self):
        path = self.root / 'directory.md'
        path.mkdir()
        with patch.object(Path, 'open', side_effect=AssertionError('directory must not open')):
            with self.assertRaises(extract.ExtractionError):
                extract.extract(path)

    def test_invalid_utf8_retains_loss_warning(self):
        path = self.root / 'encoding.txt'
        path.write_bytes(b'Synthetic \xff evidence.')
        result = extract.extract(path)
        self.assertEqual(result['status'], 'partial')
        self.assertIn('TEXT_DECODE_REPLACEMENTS_USED', result['warnings'])
        self.assertEqual(result['document']['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())


    def test_structural_row_revision_withholds_table_text(self):
        body = paragraph('Preserved body') + '<w:tbl><w:tr><w:trPr><w:del/></w:trPr><w:tc>' + paragraph('Ambiguous row') + '</w:tc></w:tr></w:tbl>'
        path = docx(self.root / 'row-revision.docx', body)
        source = path.read_bytes()
        result = extract.extract(path)
        self.assertEqual(result['segments'][0]['text'], 'Preserved body')
        self.assertEqual(result['segments'][1]['text'], '')
        self.assertTrue(any('TABLE_STRUCTURAL_REVISIONS_NOT_EXTRACTED' in w for w in result['warnings']))
        self.assertEqual(path.read_bytes(), source)

    def test_structural_cell_revision_is_explicitly_unreadable(self):
        body = '<w:tbl><w:tr><w:tc><w:tcPr><w:cellDel/></w:tcPr>' + paragraph('Ambiguous cell') + '</w:tc></w:tr></w:tbl>'
        result = extract.extract(docx(self.root / 'cell-revision.docx', body))
        self.assertEqual(result['status'], 'unreadable')
        self.assertTrue(any('TRACKED_CHANGES' in w for w in result['warnings']))
        self.assertTrue(any('TABLE_STRUCTURAL_REVISIONS_NOT_EXTRACTED' in w for w in result['warnings']))

    def test_custom_xml_row_wrapper_discloses_omission(self):
        body = '<w:tbl><w:customXml><w:tr><w:tc>' + paragraph('Wrapped row') + '</w:tc></w:tr></w:customXml></w:tbl>'
        result = extract.extract(docx(self.root / 'wrapped-row.docx', body))
        self.assertEqual(result['status'], 'unreadable')
        self.assertTrue(any('WRAPPED_TABLE_ROWS_OR_CELLS_NOT_EXTRACTED' in w for w in result['warnings']))

    def test_custom_xml_cell_wrapper_discloses_omission(self):
        body = '<w:tbl><w:tr><w:customXml><w:tc>' + paragraph('Wrapped cell') + '</w:tc></w:customXml></w:tr></w:tbl>'
        result = extract.extract(docx(self.root / 'wrapped-cell.docx', body))
        self.assertEqual(result['status'], 'unreadable')
        self.assertTrue(any('WRAPPED_TABLE_ROWS_OR_CELLS_NOT_EXTRACTED' in w for w in result['warnings']))

    def test_missing_pdf_backend_is_explicit(self):
        path = self.root / "synthetic.pdf"
        make_synthetic_corpus._write_minimal_pdf(path, ["Synthetic evidence."])
        with patch.dict(sys.modules, {"pypdf": None}):
            with self.assertRaisesRegex(extract.ExtractionError, "PDF_BACKEND_UNAVAILABLE"):
                extract.extract(path)


if __name__ == '__main__':
    unittest.main()

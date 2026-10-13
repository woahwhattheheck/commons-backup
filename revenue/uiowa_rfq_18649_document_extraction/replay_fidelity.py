#!/usr/bin/env python3
"""Replay eight fictional source-fidelity cases against two exact source revisions.

This is a pinned historical comparison, not a generic loader or source review.
It never fetches source or overwrites an existing output directory. The source
buffers whose identities are checked are the same buffers compiled for execution.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import hashlib
import io
import json
import sys
import types
import zipfile

def _display(*values: object) -> None:
    """Keep console output usable when its encoding cannot represent a quote.

    The JSON artifact always preserves Unicode in UTF-8. A limited terminal gets
    explicit backslash escapes rather than changing the quote or failing a run.
    """
    text = ' '.join(str(value) for value in values) + '\n'
    encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    sys.stdout.write(text.encode(encoding, 'backslashreplace').decode(encoding))

def main(argv: list[str] | None=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True, help='Original #16120 extract.py, Git blob d275410f...')
    parser.add_argument('--candidate', type=Path, default=Path(__file__).resolve().parent / 'extract.py')
    parser.add_argument('--output', type=Path, required=True, help='A new directory for the fictional source packet and actual results')
    args = parser.parse_args(argv)
    try:
        import pypdf
        from pypdf import PdfWriter
        from pypdf.generic import NameObject
        if pypdf.__version__.split('.')[0] != '6':
            raise ValueError("REQUIRES_PYPDF_6: install this component's declared requirements")
        OUT = args.output

        def blob(b: bytes) -> str:
            return hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\x00' + b).hexdigest()

        def load(path: Path, name: str, expected: str) -> tuple[types.ModuleType, bytes]:
            raw = path.read_bytes()
            if blob(raw) != expected:
                raise RuntimeError('SOURCE_BINDING_MISMATCH')
            module = types.ModuleType(name)
            module.__file__ = str(path)
            sys.modules[name] = module
            exec(compile(raw, str(path), 'exec'), module.__dict__)
            return (module, raw)
        before, before_raw = load(args.baseline, 'celadon_before', 'd275410fe0842426ad32bf9d15da4f69beaba463')
        after, after_raw = load(args.candidate, 'celadon_after', '765d9601b3f1fef8ee6cd2517d71018eaafc593d')
        W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'

        def paragraph(text: str) -> str:
            return '<w:p><w:r><w:t>' + text + '</w:t></w:r></w:p>'

        def docx(body: str) -> bytes:
            raw = f'<w:document xmlns:w="{W}" xmlns:mc="{MC}" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"><w:body>{body}</w:body></w:document>'.encode()
            out = io.BytesIO()
            with zipfile.ZipFile(out, 'w') as z:
                info = zipfile.ZipInfo('word/document.xml', date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 33188 << 16
                z.writestr(info, raw)
            return out.getvalue()
        alt = '<mc:AlternateContent><mc:Choice Requires="w14"><w:r><w:t>APPROVED</w:t></w:r></mc:Choice><mc:Fallback><w:r><w:t>DECLINED</w:t></w:r></mc:Fallback></mc:AlternateContent>'
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        del writer._root_object[NameObject('/Pages')]
        stream = io.BytesIO()
        writer.write(stream)
        writer2 = PdfWriter()
        empty = io.BytesIO()
        writer2.write(empty)
        cases = [('fenced.md', b'# Release practice\n```python\n# This is a code comment\npass\n```\nAfter code.\n', 'Code comments must not become evidence section headings.'), ('blank_edges.md', b'# Context\n\n\n  Indented evidence with trailing spaces.  \n\n', 'Quote edges and line locators must refer to the same text.'), ('content_control.docx', docx('<w:sdt><w:sdtContent>' + paragraph('Fictional wrapped evidence.') + '</w:sdtContent></w:sdt>'), 'Supported wrappers must not silently discard evidence.'), ('alternatives.docx', docx('<w:p>' + alt + '</w:p>'), 'Mutually exclusive content must not become APPROVEDDECLINED.'), ('heading_context.docx', docx('<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Prior heading</w:t></w:r></w:p><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>' + alt + '</w:p>' + paragraph('Following fictional evidence.')), 'Unresolved headings must not carry a fabricated or prior title forward.'), ('nonbreaking_hyphen.docx', docx('<w:p><w:r><w:t>re</w:t><w:noBreakHyphen/><w:t>sign</w:t></w:r></w:p>'), 'Dropping a visible hyphen can change the meaning of a quotation.'), ('missing_pages.pdf', stream.getvalue(), 'Container opening is not proof that its page sequence is readable.'), ('no_pages.pdf', empty.getvalue(), 'A zero-page document requires an explicit diagnostic.')]
        OUT.mkdir(exist_ok=False)
        rows = []
        for name, raw, why in cases:
            path = OUT / name
            path.write_bytes(raw)
            row = {'id': name, 'synthetic': True, 'purpose': why, 'source_sha256': hashlib.sha256(raw).hexdigest(), 'source_bytes': len(raw), 'results': {}}
            for label, module in [('original', before), ('composed', after)]:
                try:
                    result = {'returned': module.extract(path)}
                except Exception as exc:
                    result = {'exception_type': type(exc).__name__, 'exception_message': str(exc)}
                if path.read_bytes() != raw:
                    raise RuntimeError('REHEARSAL_CHANGED_INPUT')
                row['results'][label] = result
            rows.append(row)

        def out(name: str) -> dict:
            return next((r for r in rows if r['id'] == name))['results']['composed']['returned']
        # Eight explicit checks; no assert statement is removed by optimized Python.
        checks = {'fenced_comment_not_heading': [s['text'] for s in out('fenced.md')['segments'] if s['kind'] == 'heading'] == ['Release practice'], 'precise_line_range': out('blank_edges.md')['segments'][-1]['locator'] == 'lines 4-4', 'wrapper_locator': out('content_control.docx')['segments'][0]['locator'] == 'sdt 1/sdtContent/paragraph 1', 'ambiguous_quote_withheld': out('alternatives.docx')['segments'][0]['text'] == '' and out('alternatives.docx')['status'] == 'unreadable', 'heading_context_explicit': out('heading_context.docx')['segments'][-1]['heading_path'] == ['(unresolved heading)'], 'nonbreaking_hyphen': out('nonbreaking_hyphen.docx')['segments'][0]['text'] == 're‑sign', 'page_tree_named_error': rows[-2]['results']['composed']['exception_type'] == 'ExtractionError' and rows[-2]['results']['composed']['exception_message'].startswith('PDF_PAGE_TREE_FAILED:'), 'zero_page_explicit': 'PDF_NO_PAGES' in out('no_pages.pdf')['warnings']}
        if not all(checks.values()):
            raise RuntimeError(checks)
        packet = {'schema': 'uiowa.extraction-fidelity-rehearsal.v1', 'synthetic': True, 'baseline_git_blob': blob(before_raw), 'candidate_git_blob': blob(after_raw), 'checks': checks, 'cases': rows}
        (OUT / 'rehearsal.json').write_text(json.dumps(packet, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        _display(json.dumps({'checks': checks, 'source': blob(after_raw)}, indent=2))
        for row in rows:
            _display('\n', row['id'])
            for label, res in row['results'].items():
                if 'returned' in res:
                    r = res['returned']
                    _display(label, r['status'], [(s['locator'], s['text'], s['heading_path']) for s in r['segments']], r['warnings'])
                else:
                    _display(label, res)
        return 0
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        print(f'REPLAY_ERROR:{type(exc).__name__}:{exc}', file=sys.stderr)
        return 2
if __name__ == '__main__':
    raise SystemExit(main())

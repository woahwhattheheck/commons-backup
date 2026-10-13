"""Replay the specific published UIOWA-136 DOCX office-render check.

This is fixture-specific evidence, not a general Word/PDF conformance validator.
Requires PyMuPDF and a PDF rendered from the exact input via LibreOffice.
"""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
import fitz

BLOB = 'c018316991cb99d5692f2659f7e07ecbc1c70147'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def normalize(text):
    return ' '.join(text.split())


def check(docx, rendered_pdf):
    data = docx.read_bytes()
    blob = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
    if blob != BLOB:
        raise ValueError('This replay binds the published fixture; different bytes need a fresh review.')
    with zipfile.ZipFile(docx) as package:
        document = ET.fromstring(package.read('word/document.xml'))
    bookmarks = {}
    for paragraph in document.iter(W + 'p'):
        text = ''.join(t.text or '' for t in paragraph.iter(W + 't'))
        for bookmark in paragraph.iter(W + 'bookmarkStart'):
            name = bookmark.get(W + 'name')
            if name in bookmarks:
                raise ValueError('Duplicate bookmark in pinned source')
            bookmarks[name] = text
    expected = [(h.get(W + 'anchor'), ''.join(t.text or '' for t in h.iter(W + 't')))
                for h in document.iter(W + 'hyperlink')]
    results = []
    with fitz.open(rendered_pdf) as pdf:
        observed = []
        # Annotation array order is not reading order. This fixture is single-column.
        for page_index, page in enumerate(pdf):
            for link in sorted(page.get_links(), key=lambda v: (v['from'].y0, v['from'].x0)):
                words = [w for w in page.get_text('words')
                         if link['from'].contains(fitz.Point((w[0]+w[2])/2, (w[1]+w[3])/2))]
                observed.append((page_index, link, ' '.join(w[4] for w in words)))
        if len(expected) != 21 or len(observed) != len(expected) or len(pdf) != 9:
            raise ValueError('The fixture page/link counts differ from the reviewed render')
        for index, ((anchor, label), (source_page, link, actual_label)) in enumerate(zip(expected, observed), 1):
            if link['kind'] != fitz.LINK_GOTO or not 0 <= link['page'] < len(pdf):
                raise ValueError(f'Link {index} is not an in-document destination')
            target_page = pdf[link['page']]
            lines = [line for block in target_page.get_text('dict')['blocks'] for line in block.get('lines', [])]
            nearest = min(lines, key=lambda v: abs(v['bbox'][1] - link['to'].y))
            actual_target = ''.join(s['text'] for s in nearest['spans'])
            delta = abs(nearest['bbox'][1] - link['to'].y)
            label_matches = normalize(label) == normalize(actual_label)
            target_matches = normalize(bookmarks[anchor]) == normalize(actual_target) and delta <= 1.0
            results.append({'index': index, 'bookmark': anchor, 'source_page': source_page+1,
                            'target_page': link['page']+1, 'label': actual_label,
                            'target_text': actual_target, 'destination_y_error_pt': round(delta, 6),
                            'label_matches': label_matches, 'target_matches': target_matches})
    report = {'source_git_blob': blob, 'source_sha256': hashlib.sha256(data).hexdigest(),
              'source_bytes': len(data), 'pages': 9, 'bookmarks': len(bookmarks),
              'links': len(results), 'passed': sum(r['label_matches'] and r['target_matches'] for r in results),
              'results': results,
              'scope': 'Specific synthetic DOCX through office-rendered PDF; no native Word GUI clicks, no submission readiness claim.'}
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('docx', type=Path)
    parser.add_argument('rendered_pdf', type=Path)
    args = parser.parse_args()
    report = check(args.docx, args.rendered_pdf)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['passed'] == report['links'] else 1)

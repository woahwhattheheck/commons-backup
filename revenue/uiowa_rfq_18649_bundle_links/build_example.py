#!/usr/bin/env python3
"""Render the pinned UIOWA-093 synthetic sources into a portable review bundle."""
from __future__ import annotations

import argparse
import csv
import hashlib
from html import escape
import io
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def page(title: str, body: str) -> str:
    return ('<!doctype html>\n<html lang="en"><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>{escape(title)}</title>\n'
            '<style>body{font:1.1rem/1.55 system-ui;margin:2rem;max-width:75rem}'
            'td,th{border:1px solid;padding:.4rem;text-align:left}'
            'table{border-collapse:collapse}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
            ':target{outline:3px solid;outline-offset:3px}a:focus-visible{outline:3px solid}'
            '</style>\n<main>\n'
            f'<h1>{escape(title)}</h1>\n'
            '<p><strong>Synthetic rehearsal only. No University finding is asserted.</strong></p>\n'
            + body + '\n</main></html>\n')


def build(destination: Path) -> dict:
    # Refuse overwriting an existing path: this creates a separate example only.
    if destination.exists():
        raise ValueError('example destination already exists; choose a new directory')
    snapshot = json.loads((HERE/'source_snapshot.json').read_text(encoding='utf-8'))
    for entry in snapshot['files']:
        data = entry['content'].encode('utf-8')
        blob = hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()
        if blob != entry['git_blob'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('pinned source snapshot bytes do not match their recorded identity')
    sources = destination/'sources'
    sources.mkdir(parents=True)
    by_name = {entry['name']: entry for entry in snapshot['files']}
    for entry in snapshot['files']:
        (sources/entry['name']).write_bytes(entry['content'].encode('utf-8'))
    rows = list(csv.DictReader(io.StringIO(by_name['evidence.csv']['content'])))
    headings = list(rows[0])
    body = '<p><a href="../review.html">Return to review guide</a></p>\n<table>\n<thead><tr>'
    body += ''.join(f'<th scope="col">{escape(h)}</th>' for h in headings) + '</tr></thead>\n<tbody>\n'
    for row in rows:
        body += f'<tr id="{escape(row["evidence_id"], quote=True)}">'
        body += ''.join(f'<td>{escape(row[h])}</td>' for h in headings) + '</tr>\n'
    body += '</tbody></table>'
    (sources/'évidence.html').write_text(page('Pinned synthetic evidence register', body), encoding='utf-8')
    report = by_name['final-report.md']['content']
    body = '<p><a href="../review.html">Return to review guide</a></p>\n<pre>\n'
    body += '\n'.join(f'<span id="L{i}">{escape(line)}</span>' for i, line in enumerate(report.splitlines(), 1))
    body += '\n</pre>'
    (sources/'report.html').write_text(page('Pinned report with stable line destinations', body), encoding='utf-8')
    guide = '''<h2 id="questions">Review the source, not only the conclusion</h2>
<p><a href="sources/report.html#L9">Where is the RIS evidence gap introduced?</a></p>
<p><a href="sources/%C3%A9vidence.html#E-006">Which source is an interview without a retained example?</a></p>
<p><a href="sources/%C3%A9vidence.html#E-007">Which IAM result covers one representative consumer?</a></p>
<p><a href="sources/report.html#L25">What is the corresponding limited recommendation?</a></p>
<p><a href="sources/final-report.md">Original report bytes</a> · <a href="sources/evidence.csv">Original CSV bytes</a></p>'''
    (destination/'review.html').write_text(page('UIOWA-119 portable citation rehearsal', guide), encoding='utf-8')
    citations = [
        {'id':'report-heading','source':'review.html','target':'sources/final-report.md#2-ris--evidence-gap-example',
         'sha256':by_name['final-report.md']['sha256']},
        {'id':'report-lines','source':'review.html','target':'sources/final-report.md',
         'locator':{'kind':'lines','start':9,'end':11}},
        {'id':'report-quote','source':'review.html','target':'sources/final-report.md',
         'locator':{'kind':'quote','text':'evidence gap rather than as proof that the activity never happened'}},
    ]
    citations += [{'id':'row-'+row['evidence_id'],'source':'review.html','target':'sources/evidence.csv',
                   'sha256':by_name['evidence.csv']['sha256'],
                   'locator':{'kind':'csv','column':'evidence_id','value':row['evidence_id']}} for row in rows]
    manifest = {'version':1,'scan_html':['review.html','sources/report.html','sources/évidence.html'],
                'citations':citations}
    (destination/'citations.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    args = parser.parse_args()
    try:
        build(args.destination)
    except (OSError, ValueError) as error:
        parser.exit(2, f'{error}\n')
    print(args.destination/'review.html')

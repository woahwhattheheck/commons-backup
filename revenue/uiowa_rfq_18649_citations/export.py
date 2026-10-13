"""Write a replayable folder for existing bundle tools; never manufacture an archive."""
from __future__ import annotations

import csv
import io
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .contract import CitationError, canonical, digest
from .integration import dependency_receipt
from .render import report_html, report_markdown, source_html
from .resolver import Resolver


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links = set(), []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            if attrs['id'] in self.ids:
                raise CitationError('Duplicate HTML anchor: ' + attrs['id'])
            self.ids.add(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])


def check_links(files: dict[str, bytes]) -> dict:
    parsed = {}
    for name, data in files.items():
        if name.endswith('.html'):
            parser = Links()
            parser.feed(data.decode('utf-8'))
            parsed[name] = parser
    count = 0
    for name, parser in parsed.items():
        for href in parser.links:
            url = urlsplit(href)
            if url.scheme or url.netloc or url.query:
                raise CitationError('Expected a portable internal link: ' + href)
            target = unquote(url.path) or name
            if target not in files:
                raise CitationError('Missing link target: ' + target)
            if url.fragment and (target not in parsed or unquote(url.fragment) not in parsed[target].ids):
                raise CitationError('Missing anchor: ' + href)
            count += 1
    return {'html_files_checked': len(parsed), 'internal_links_checked': count, 'broken_links': 0}


def trace_csv(trace: dict) -> bytes:
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(['finding_id', 'citation_id', 'source_id', 'version', 'sha256',
                     'resolved', 'bound_to_compiler_source', 'diagnostics'])
    for finding in trace['findings']:
        for c in finding['citations']:
            writer.writerow([finding['finding_id'], c['citation_id'], c['source_id'], c['version'],
                             c['sha256'], c['resolved'], c.get('bound_to_compiler_source', False),
                             '; '.join(c['diagnostics'])])
    return out.getvalue().encode('utf-8')


def build_files(resolver: Resolver) -> tuple[dict, dict[str, bytes]]:
    trace = resolver.run()
    files = {'index.html': report_html(trace).encode('utf-8'),
             'report.md': report_markdown(trace).encode('utf-8'),
             'trace.json': canonical(trace), 'trace.csv': trace_csv(trace),
             'packet.json': canonical(resolver.packet), 'compiler-report.json': canonical(resolver.report),
             'candidate.json': canonical(resolver.report['candidate']),
             'authority.json': canonical(resolver.report['evidence_authority']),
             'dependencies.json': canonical(dependency_receipt())}
    for name, (data, extraction) in sorted(resolver.retained.items()):
        files[name] = data
        sha = extraction['document']['sha256']
        files['extraction-' + sha + '.json'] = canonical(extraction)
        files['reader-' + sha + '.html'] = source_html(extraction, name).encode('utf-8')
    links = check_links(files)
    files['link-check.json'] = canonical(links)
    files['manifest.json'] = canonical({'schema': 'uiowa.citation-bundle.v1',
        'label': trace['label'], 'compiler_receipt_sha256': trace['compiler_receipt_sha256'],
        'packet_sha256': trace['packet_sha256'], 'files': [
            {'path': path, 'bytes': len(data), 'sha256': digest(data)}
            for path, data in sorted(files.items())], 'manifest_includes_itself': False})
    return trace, files


def write_new_bundle(resolver: Resolver, destination: Path) -> dict:
    trace, files = build_files(resolver)
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in sorted(files.items()):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as handle:
            handle.write(data)
    return {'label': trace['label'], 'counts': trace['counts'], 'files_written': len(files),
            'compiler_receipt_sha256': trace['compiler_receipt_sha256'],
            'index': str(destination / 'index.html')}

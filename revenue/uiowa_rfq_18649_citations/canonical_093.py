"""Consume Keystone's existing 093 records; distinguish register rows from source bytes."""
from __future__ import annotations

import csv
import io
from html import escape
from pathlib import Path

from .contract import CitationError, LABEL, canonical, digest, unique
from .render import page

FILES = ('evidence.csv', 'findings.csv', 'recommendations.csv', 'trace-map.csv')


def read_csv(path: Path) -> tuple[list, bytes]:
    data = path.read_bytes()
    reader = csv.DictReader(io.StringIO(data.decode('utf-8'), newline=''))
    if reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise CitationError('Missing or duplicate CSV headings: ' + path.name)
    rows, previous = [], reader.line_num
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise CitationError('Malformed CSV row: ' + path.name)
        rows.append({'fields': row, 'lines': [previous + 1, reader.line_num]})
        previous = reader.line_num
    return rows, data


def split(value: str) -> list[str]:
    return [item for item in value.split(';') if item]


def audit_rehearsal(root: Path) -> dict:
    loaded = {name: read_csv(root / name) for name in FILES}
    expected = {'evidence_id', 'service', 'source_type', 'source_name', 'locator', 'observation', 'evidence_state'}
    if any(set(row['fields']) != expected for row in loaded['evidence.csv'][0]):
        raise CitationError('093 evidence schema changed; update the explicit source-intake adapter')
    evidence = unique([r['fields'] for r in loaded['evidence.csv'][0]], 'evidence_id', '093 evidence')
    findings = unique([r['fields'] for r in loaded['findings.csv'][0]], 'finding_id', '093 findings')
    recs = unique([r['fields'] for r in loaded['recommendations.csv'][0]], 'recommendation_id', '093 recommendations')
    statements = unique([r['fields'] for r in loaded['trace-map.csv'][0]], 'statement_id', '093 statements')
    requests = []
    for record in loaded['evidence.csv'][0]:
        row = record['fields']
        eid = row['evidence_id']
        fids = [fid for fid, f in findings.items() if eid in split(f['evidence_ids'])]
        requests.append({'evidence_id': eid, 'original_record': row,
            'register_path': 'evidence.csv', 'register_lines': record['lines'],
            'register_sha256': digest(loaded['evidence.csv'][1]),
            'record_sha256': digest(canonical(row)), 'original_source_sha256': None,
            'original_source_version': None, 'original_source_locator': row['locator'],
            'source_byte_status': 'ORIGINAL_SOURCE_INPUT_NEEDED',
            'affected_findings': fids,
            'affected_recommendations': [rid for rid, rec in recs.items()
                                         if set(fids) & set(split(rec['linked_findings']))],
            'affected_statements': [sid for sid, st in statements.items()
                                    if eid in split(st['evidence_ids'])],
            'next_input': 'Retain the named fictional source, its revision and byte digest, and an exact '
                          'extractor segment/locator. Do not substitute the register-row digest for source bytes.'})
    return {'schema': 'uiowa.canonical-093-source-intake.v1', 'label': LABEL,
        'upstream_component': 'uiowa_rfq_18649_traceability_rehearsal',
        'upstream_credit': 'Keystone / GPT-5.6 Sol; PR #16157',
        'existing_record_counts': {'evidence': len(evidence), 'findings': len(findings),
                                  'recommendations': len(recs), 'report_statements': len(statements)},
        'original_source_citations_asserted': 0, 'requests': requests,
        'interpretation': 'This extends the existing record-link rehearsal with source-intake preparation; '
                          'it does not replace its findings or reclassify its accepted link-check result.',
        'input_files': [{'path': name, 'sha256': digest(loaded[name][1])} for name in FILES]}


def write_audit(audit: dict, destination: Path) -> dict:
    body = ['<h1>Canonical 093: next source-intake layer</h1>', '<p>' + LABEL + '</p>',
            '<p>' + escape(audit['interpretation']) + '</p>',
            '<p>Register row identity is retained; original named-document identity is not invented.</p>']
    for row in audit['requests']:
        evidence = row['original_record']
        body += [f'<article id="{escape(row["evidence_id"])}"><h2>{escape(row["evidence_id"])}</h2>',
                 '<p>' + escape(evidence['source_name']) + ' — ' + escape(row['original_source_locator']) + '</p>',
                 '<blockquote>' + escape(evidence['observation']) + '</blockquote>',
                 '<p>Register locator: evidence.csv lines ' + '-'.join(map(str, row['register_lines'])) + '</p>',
                 '<p>Affected findings: ' + escape(', '.join(row['affected_findings'])) + '; report statements: ' +
                 escape(', '.join(row['affected_statements'])) + '</p>',
                 '<p>' + escape(row['next_input']) + '</p></article>']
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'source-intake.json').write_bytes(canonical(audit))
    (destination / 'index.html').write_text(page('Canonical 093 source intake', ''.join(body)), encoding='utf-8')
    return {'existing_record_counts': audit['existing_record_counts'],
            'source_intake_requests': len(audit['requests']), 'original_source_citations_asserted': 0}

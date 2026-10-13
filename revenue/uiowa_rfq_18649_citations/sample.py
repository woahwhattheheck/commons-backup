"""Fictional retained-byte fixture, separate from Keystone's canonical 093 records."""
from __future__ import annotations

from pathlib import Path

from .contract import SCHEMA, LABEL, canonical, digest
from .integration import extract_snapshot, inspect

GENERATION = 'uiowa-nacre-synthetic-citations-20260919-v1'
EVALUATED_AT = '2026-09-19T12:00:00Z'
DOCUMENTS = {
    'documents/ess-release.md': '# Fictional ESS release record\n\nSYNTHETIC fixture; not a University record.\n\n'
        '## Covered change\nChange ENR-17 links its acceptance criterion, passing integration run, '
        'and registrar-role acceptance in one release record.\n'
        'The retained example covers only the selected enrollment-state transition.\n',
    'documents/ris-interview.md': '# Fictional RIS AI workflow interview\n\nSYNTHETIC fixture; not a University interview.\n\n'
        '## Evaluation evidence\nThe participant described checking assisted drafts manually but supplied '
        'no retained evaluation set or repair-time measurements in this packet.\n'
        'This statement does not establish whether other teams retain such material.\n',
    'documents/iam-v1.md': '# Fictional IAM propagation inventory v1\n\nSYNTHETIC fixture; not a University record.\n\n'
        '## Recorded scope\nVersion one lists a single representative downstream consumer.\n',
    'documents/iam-v2.md': '# Fictional IAM propagation inventory v2\n\nSYNTHETIC fixture; not a University record.\n\n'
        '## Recorded scope\nVersion two lists seven dependent consumers and identifies the one sampled consumer.\n'
}
QUOTES = [
    'Change ENR-17 links its acceptance criterion, passing integration run, and registrar-role acceptance in one release record.',
    'The participant described checking assisted drafts manually but supplied no retained evaluation set or repair-time measurements in this packet.',
    'Version one lists a single representative downstream consumer.'
]


def make_sample(root: Path) -> tuple[dict, dict]:
    root.mkdir(parents=True, exist_ok=True)
    for name, body in DOCUMENTS.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as f:
            f.write(body.encode('utf-8'))
    specs = [('SRC-ESS', 'v1', 'documents/ess-release.md', 'ESS', 'software', 'artifact'),
             ('SRC-RIS', 'v1', 'documents/ris-interview.md', 'RIS', 'ai_readiness', 'interview'),
             ('SRC-IAM', 'v1', 'documents/iam-v1.md', 'IAM', 'deployment', 'artifact'),
             ('SRC-IAM', 'v2', 'documents/iam-v2.md', 'IAM', 'deployment', 'artifact')]
    sources, authority_rows, refs = [], [], []
    for ordinal, (sid, version, path, group, dimension, kind) in enumerate(specs):
        data = (root / path).read_bytes()
        extraction = extract_snapshot(data, Path(path).name)
        source = {'source_id': sid, 'version': version, 'path': path, 'aliases': [],
                  'title': Path(path).name + ' — fictional', 'sha256': digest(data),
                  'superseded_by': 'v2' if sid == 'SRC-IAM' and version == 'v1' else None}
        sources.append(source)
        if ordinal < 3:
            quote = QUOTES[ordinal]
            segment = next(row for row in extraction['segments'] if quote in row['text'])
            refs.append({'source_id': sid, 'version': version, 'sha256': digest(data),
                         'segment_id': segment['segment_id'], 'locator': segment['locator'], 'quote': quote})
        if ordinal != 2:
            authority_rows.append({'source_id': sid, 'authority_generation': GENERATION,
                'solicitation_id': '18649', 'prime_candidate': "Clark's Consulting", 'group': group,
                'dimension': dimension, 'evidence_kind': kind,
                'source_ref': 'synthetic://nacre-retained/' + sid + '/' + version,
                'source_content_sha256': digest(data), 'observed_at': '2026-09-18T12:00:00Z',
                'claim': 'Synthetic schema fixture: ' + path, 'maturity': 2, 'confidence_bp': 7000})
    candidate = {'schema': 'uiowa-rfq18649-workshare-candidate/v2',
        'engagement': {'solicitation_id': '18649', 'buyer': 'University of Iowa',
                       'prime_candidate': "Clark's Consulting", 'subcontractor': 'TJLabs',
                       'base_fee_usd': 24000, 'optional_readout_usd': 4000},
        'authority_generation': GENERATION, 'source_ids': [r['source_id'] for r in authority_rows]}
    authority = {'schema': 'uiowa-rfq18649-evidence-authority/v2', 'generation': GENERATION,
                 'solicitation_id': '18649', 'prime_candidate': "Clark's Consulting", 'sources': authority_rows}
    report = inspect(candidate, authority, EVALUATED_AT)
    statements = [
        ('F-ESS', 'ESS', 'software', 'strength',
         'The fictional ESS record preserves a requirement-to-acceptance chain for the covered change.',
         'One selected transition does not establish coverage of all ESS workflows.'),
        ('F-RIS', 'RIS', 'ai_readiness', 'gap',
         'The fictional RIS interview packet lacks retained evaluation and repair-time evidence.',
         'An interview-only statement is not proof that no evaluation occurs elsewhere.'),
        ('F-IAM-OLD', 'IAM', 'deployment', 'open_question',
         'The cited IAM inventory is a historical version, not the version bound to this compiler report.',
         'Retain the old record; inspect v2 before making a current coverage statement.')]
    findings = [{'finding_id': fid, 'group': group, 'dimension': dim, 'kind': kind,
                 'statement': statement, 'limits': limits, 'evidence_refs': [refs[i]]}
                for i, (fid, group, dim, kind, statement, limits) in enumerate(statements)]
    findings.append({'finding_id': 'F-MISSING', 'group': 'ESS', 'dimension': 'ai_readiness',
        'kind': 'open_question', 'statement': 'The requested fictional ESS AI source is not in the retained packet.',
        'limits': 'Absence from this packet is not a statement about University practice.',
        'evidence_refs': [{'source_id': 'SRC-NOT-SUPPLIED', 'version': 'v1', 'sha256': '0' * 64,
                           'segment_id': 'text-0001', 'locator': 'lines 1-2',
                           'quote': 'Requested evidence; not an asserted quotation.'}]})
    recommendations = [
        {'recommendation_id': 'R-RETAIN', 'finding_ids': ['F-ESS', 'F-RIS'],
         'action': 'Preserve the covered acceptance chain and retain one bounded AI evaluation example.',
         'rationale': 'The examples show how retained artifacts can reduce reconstruction work without extrapolating coverage.',
         'phase': '0-90 days', 'owner_role': 'Assessment practitioner',
         'effort': 'Illustrative 2-4 analyst hours; not an engagement estimate.',
         'outcome_measure': 'A reviewer can retrieve the selected acceptance and evaluation records.'},
        {'recommendation_id': 'R-REFRESH', 'finding_ids': ['F-IAM-OLD', 'F-MISSING'],
         'action': 'Resolve the requested source version and supply the missing evidence before revising the draft statements.',
         'rationale': 'Exact old bytes remain available; absent source bytes cannot be replaced by a guessed citation.',
         'phase': '0-90 days', 'owner_role': 'Evidence custodian role',
         'effort': 'Illustrative 1-2 analyst hours, subject to source availability.',
         'outcome_measure': 'Each requested reference is either resolved exactly or retains a documented open question.'}]
    packet = {'schema': SCHEMA, 'label': LABEL, 'generation': GENERATION,
              'compiler_receipt_sha256': report['receipt_sha256'], 'sources': sources,
              'findings': findings, 'recommendations': recommendations,
              'executive_summary': {'finding_ids': [f['finding_id'] for f in findings],
                                    'recommendation_ids': [r['recommendation_id'] for r in recommendations]}}
    (root / 'packet.json').write_bytes(canonical(packet))
    (root / 'compiler-report.json').write_bytes(canonical(report))
    return packet, report

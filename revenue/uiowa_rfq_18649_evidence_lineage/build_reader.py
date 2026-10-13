"""Create-only offline presentation of the existing seven saved reports.

This does not call the comparator, derive lineage, or change a finding.
"""
from pathlib import Path
import argparse, hashlib, json

NAMES = ['01-original-retained', '02-intermediate-retained', '03-no-records-supplied',
         '04-terminal-arrives', '05-one-branch-omitted', '06-both-branches-arrive', '07-declared-convergence']

def require(value, message):
    if not value:
        raise ValueError(message)

def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'

def build(cases_path, output):
    require(not output.exists(), 'Output already exists; choose a new filename.')
    summary = json.loads((cases_path / 'walkthrough.json').read_text(encoding='utf-8'))
    require(summary['synthetic'] is True and summary['status'] == 'DRAFT_NON_AUTHORITATIVE', 'Synthetic saved walkthrough required.')
    require([r['case'] for r in summary['cases']] == NAMES, 'Seven retained cases required in original order.')
    cases = []
    for row in summary['cases']:
        folder = cases_path / row['case']
        raw = (folder / 'review.json').read_bytes()
        report = json.loads(raw)
        require(report['synthetic'] is True and report['status'] == summary['status'], 'Report classification mismatch.')
        require(hashlib.sha256(encoded(report).encode()).hexdigest() == row['report_sha256'], 'Report canonical digest mismatch.')
        for name, field in [('before', 'before'), ('after', 'after'), ('findings', 'input_findings')]:
            supplied = json.loads((folder / (name + '.json')).read_text(encoding='utf-8'))
            require(supplied == report[field], 'Report/input mismatch: ' + name)
            require(hashlib.sha256(encoded(supplied).encode()).hexdigest() == report['input_sha256'][name], 'Input digest mismatch.')
        require(len(report['finding_impacts']) == 1 and len(report['input_findings']['findings']) == 1, 'One retained fixture finding required.')
        impact = report['finding_impacts'][0]
        finding = report['input_findings']['findings'][0]
        require(impact['citation'] == finding['citations'][0] and impact['finding_id'] == finding['finding_id'], 'Citation identity mismatch.')
        require(impact['status'] == row['status'], 'Saved status mismatch.')
        require([r['record_id'] for r in impact['declared_successors']] == row['present_terminal_records'], 'Supplied terminal mismatch.')
        require([r['record_id'] for r in impact.get('missing_declared_successors', [])] == row['absent_terminal_records'], 'Omitted terminal mismatch.')
        for label in ('before', 'after'):
            for record in report[label]['records']:
                path = folder / label / record['location']
                require(path.resolve().is_relative_to((folder / label).resolve()), 'Source outside case folder.')
                text = path.read_bytes()
                require(hashlib.sha256(text).hexdigest() == record['sha256'], 'Source byte digest mismatch.')
                require(text.decode('utf-8') == record['metadata']['example_text'], 'Source text mismatch.')
        cases.append({'name': row['case'], 'follow_up': row['follow_up'], 'report': report,
                      'report_file_sha256': hashlib.sha256(raw).hexdigest(), 'report_file_bytes': list(raw)})
    payload = json.dumps({'schema': 'uiowa033-offline-presentation/v1', 'cases': cases}, ensure_ascii=True, separators=(',', ':'))
    # Script-data embedding must not let source text close the inert JSON element.
    payload = payload.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    template = Path(__file__).with_name('reader.html').read_text(encoding='utf-8')
    require(template.count('__READER_DATA__') == 1, 'Single data placeholder required.')
    result = template.replace('__READER_DATA__', payload).encode('utf-8')
    with output.open('xb') as stream:
        stream.write(result)
    return {'output': str(output), 'bytes': len(result), 'sha256': hashlib.sha256(result).hexdigest(),
            'case_count': len(cases), 'source_report_consistency': 'PASS', 'engine_invoked': False}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases_path', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.cases_path, args.output), indent=2))

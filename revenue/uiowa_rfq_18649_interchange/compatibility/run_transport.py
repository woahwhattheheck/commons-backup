"""Execute a reviewed transport module against independent JSON-value oracles.

The module argument is executable source, not an untrusted intake document.
The runner does not edit that module or call network/provider services.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

from contract import audit_pair, compare_json, loads_exact

HERE = Path(__file__).resolve().parent


def exercise(module_path: Path, report_path: Path, handoff_path: Path) -> dict:
    source = module_path.read_bytes()
    spec = importlib.util.spec_from_file_location('reviewed_interchange_transport', module_path)
    if spec is None or spec.loader is None:
        raise ValueError('could not load reviewed transport module')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    required = ('loads', 'canonical_json', 'to_rows', 'from_rows', 'write_csv', 'read_csv')
    missing = [name for name in required if not callable(getattr(module, name, None))]
    if missing:
        raise ValueError('missing transport interface: ' + ', '.join(missing))
    report_text, handoff_text = report_path.read_text(encoding='utf-8'), handoff_path.read_text(encoding='utf-8')
    inputs = [
        ('actual-workbench-report', report_text),
        ('actual-workbench-handoff', handoff_text),
        ('synthetic-evidence-recommendations', (HERE / 'fixtures' / 'transport_cases.json').read_text(encoding='utf-8')),
        ('integer-over-binary64-exact-range', '{"count":9007199254740993}'),
        ('decimal-precision-boundary', '{"value":0.123456789012345678901}'),
        ('decimal-underflow-boundary', '{"value":1e-400}'),
        ('negative-zero-boundary', '{"value":-0.0}')
    ]
    results = []
    returned_pair = {}
    with tempfile.TemporaryDirectory() as directory:
        for index, (name, original) in enumerate(inputs):
            for route in ('rows', 'csv'):
                row = {'case': name, 'route': route}
                try:
                    document = module.loads(original)
                    if route == 'rows':
                        returned = module.from_rows(module.to_rows(document))
                    else:
                        path = Path(directory) / f'{index}.csv'
                        module.write_csv(document, path)
                        returned = module.read_csv(path)
                    text = module.canonical_json(returned)
                    row.update(compare_json(original, text))
                    if name in ('actual-workbench-report', 'actual-workbench-handoff') and route == 'csv':
                        returned_pair[name] = loads_exact(text)
                except (ValueError, TypeError, OSError) as exc:
                    # Explicit rejection is not silent data loss, but it is also
                    # not a successful interchange of this test case.
                    row.update(result='REJECTED', error_type=type(exc).__name__, error=str(exc))
                results.append(row)
    if len(returned_pair) == 2:
        diagnostics = audit_pair(returned_pair['actual-workbench-report'], returned_pair['actual-workbench-handoff'])
        results.append({'case': 'returned-report-handoff-join', 'route': 'csv',
                        'result': 'FAIL' if diagnostics else 'PASS', 'diagnostics': diagnostics})
    counts = {name: sum(row['result'] == name for row in results) for name in ('PASS', 'FAIL', 'REJECTED')}
    return {
        'schema': 'uiowa-096-independent-transport-execution/v1',
        'transport_git_blob_sha1': hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest(),
        'transport_sha256': hashlib.sha256(source).hexdigest(),
        'source_report_sha256': hashlib.sha256(report_text.encode()).hexdigest(),
        'source_handoff_sha256': hashlib.sha256(handoff_text.encode()).hexdigest(),
        'python': sys.version.split()[0], 'counts': counts, 'cases': results,
        'result': 'PASS' if counts['FAIL'] == counts['REJECTED'] == 0 else 'REVIEW_REQUIRED',
        'authority': 'format-and-pair-consistency-only; no source-authentication or University findings'
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('module', type=Path)
    parser.add_argument('--report', type=Path, default=HERE / 'fixtures/workbench/report.json')
    parser.add_argument('--handoff', type=Path, default=HERE / 'fixtures/workbench/handoff.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    result = exercise(args.module.resolve(), args.report, args.handoff)
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(text)
    print(text, end='')
    return int(result['result'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())

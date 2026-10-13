"""Summarize retained actual receipts; never promote statuses or alter originals."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    runs = []
    for path in (ROOT / 'runs').rglob('*.json'):
        raw = path.read_bytes()
        run = json.loads(raw)
        if run.get('schema_version') != 'agents-for-humans-run/v1':
            continue
        requests = run.get('provider_requests', [])
        runs.append({'run_id': run['run_id'], 'receipt_sha256': hashlib.sha256(raw).hexdigest(),
                     'source_version': run['source_version'], 'started_at': run['started_at'],
                     'case_id': run.get('case_id'), 'recorded_status': run['status'],
                     'execution_kind': run['execution_kind'], 'request_count': len(requests),
                     'request_outcomes': [{key: request.get(key) for key in
                         ('request_id', 'status', 'finish_reasons', 'wall_seconds', 'token_usage')}
                         for request in requests],
                     'error': run.get('error')})
    runs.sort(key=lambda item: item['started_at'])
    result = {'description': 'Actual development run history. Recorded status is not semantic approval. See VALIDATION.md.',
              'actual_requests': sum(run['request_count'] for run in runs), 'runs': runs}
    (ROOT / 'RUN_HISTORY.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'runs': len(runs), 'actual_requests': result['actual_requests']}))


if __name__ == '__main__':
    main()

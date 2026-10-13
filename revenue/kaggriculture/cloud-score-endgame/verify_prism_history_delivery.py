# SPDX-License-Identifier: Apache-2.0
"""Check delivered histories against retained source and forbidden-data controls."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys
import zipfile
from prism_history_inputs import encoded, extract_payload, sha


def verify(archive_path, delivery, start=0, count=4):
    root = Path(delivery)
    index = json.loads((root/'index.json').read_bytes())
    selected = index['records'][start:start+count]
    if not selected: raise ValueError('Empty verification shard')
    totals = {'observation_comparisons': 0, 'own_action_comparisons': 0,
              'excluded_data_controls': 0, 'same_phase_prior_observations': 0}
    with zipfile.ZipFile(archive_path) as source:
        for record in selected:
            print('Checking '+record['identity'], file=sys.stderr, flush=True)
            compressed = (root/record['runtime_member']).read_bytes()
            assert sha(compressed) == record['runtime_gzip_sha256']
            plain = gzip.decompress(compressed)
            assert sha(plain) == record['runtime_sha256']
            payload = json.loads(plain)
            rows = [json.loads(line) for line in gzip.decompress(source.read(record['source_trace_member'])).splitlines()]
            seat = record['player']; stop = payload['observation']['step']
            sequence = [entry['observation'] for entry in payload['history']] + [payload['observation']]
            actions = [entry['own_action'] for entry in payload['history']] + [payload['selected_action']]
            for t, observed in enumerate(sequence):
                recorded = rows[t]['observations'][seat]
                assert set(observed) == {'farms','private','market','town','day','hour','player','step','remainingOverageTime'}
                assert all(observed[k] == recorded[k] for k in observed if k not in ('step','remainingOverageTime'))
                assert observed['step'] == t and observed['remainingOverageTime'] == 0
                assert actions[t] == rows[t+1]['actions'][seat]
                totals['observation_comparisons'] += 1
                totals['own_action_comparisons'] += 1
            assert stop == 718 and len(payload['history']) == 718
            assert 'seed' not in payload['configuration']
            # Mutate all excluded actor/future fields, not known public inputs.
            for row in rows:
                row['observations'][1-seat] = {'private': {'secret': 'changed'}}
                row['actions'][1-seat] = {'actual_rival_action': 'changed'}
                row['rewards'] = ['changed','changed']
            assert encoded(extract_payload(rows,payload['configuration'],seat)) == plain
            totals['excluded_data_controls'] += 1
            rows[-1]['observations'] = [{'future_terminal':'changed'}]*2
            assert encoded(extract_payload(rows,payload['configuration'],seat)) == plain
            totals['excluded_data_controls'] += 1
            period = payload['configuration']['turnsPerDay']
            for lag in range(1,6):
                t = stop-lag*period
                assert payload['history'][t]['observation']['step'] == t
                assert sequence[t+1]['step'] == t+1
                assert sequence[t]['hour'] == sequence[stop]['hour']
                totals['same_phase_prior_observations'] += 1
    return {'schema':'titan.prism-history-verification.v1', **totals,
        'source_records':len(selected), 'record_identities':[r['identity'] for r in selected], 'unique_runtime_payloads':index['unique_runtime_payloads'],
        'independent_development_seeds':index['independent_development_seeds'],
        'new_policy_calls':0, 'new_engine_calls':0, 'new_games':0,
        'index_sha256':sha((root/'index.json').read_bytes()),
        'source_archive_sha256':index['source_archive_sha256']}


if __name__ == '__main__':
    result=verify(sys.argv[1],sys.argv[2],int(sys.argv[3]) if len(sys.argv)>3 else 0, int(sys.argv[4]) if len(sys.argv)>4 else 4)
    print(json.dumps(result,indent=2))

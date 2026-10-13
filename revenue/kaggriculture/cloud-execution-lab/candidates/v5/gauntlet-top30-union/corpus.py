#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize archived opponent actions and add them to an existing gauntlet.

Recorded actions are deliberately labeled diagnostic opponents. They are not
reconstructions of the competitor's observation-responsive executable policy.
"""
import argparse
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

EXPECTED_UNIQUE_SUBMISSIONS = 41
EXPECTED_FIXTURES = 123
PROVENANCE = 'public_recorded_actions'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def action_tape(replay, seat):
    steps = replay['steps']
    if seat not in (0, 1) or len(steps) != 720 or replay.get('statuses') != ['DONE', 'DONE']:
        raise ValueError('Expected a complete two-seat 719-decision episode')
    actions = [deepcopy(step[seat]['action']) for step in steps[1:]]
    if not all(isinstance(a, dict) and isinstance(a.get('farmer'), list)
               and isinstance(a.get('hands', []), list)
               and isinstance(a.get('market', []), list) for a in actions):
        raise ValueError('Missing or malformed recorded action')
    return actions


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def _validate_target_manifest(manifest):
    targets = manifest.get('targets')
    if not isinstance(targets, list) or len(targets) != EXPECTED_UNIQUE_SUBMISSIONS:
        raise ValueError(f'Expected {EXPECTED_UNIQUE_SUBMISSIONS} distinct corpus targets')
    submission_ids = []
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError('Corpus target must be an object')
        submission_id = target.get('submission_id')
        if isinstance(submission_id, bool) or not isinstance(submission_id, int) or submission_id <= 0:
            raise ValueError('Corpus submission_id must be a positive integer')
        submission_ids.append(submission_id)
        if target.get('status') != 'complete' or len(target.get('replays', [])) != 3:
            raise ValueError('Incomplete target acquisition: '+str(submission_id))
    if len(set(submission_ids)) != len(submission_ids):
        raise ValueError('Corpus target submission IDs are not unique')


def validate_recorded_additions(additions, *, expected_unique_submissions=None,
                                expected_fixtures=None):
    if expected_fixtures is not None and len(additions) != expected_fixtures:
        raise ValueError(f'Expected {expected_fixtures} recorded fixtures, got {len(additions)}')
    submissions = Counter()
    fixture_ids = []
    for row in additions:
        if not isinstance(row, dict):
            raise ValueError('Recorded fixture must be an object')
        fixture_id = row.get('id')
        if not isinstance(fixture_id, str) or not fixture_id:
            raise ValueError('Recorded fixture id must be a non-empty string')
        fixture_ids.append(fixture_id)
        submission_id = row.get('submission_id')
        if isinstance(submission_id, bool) or not isinstance(submission_id, int) or submission_id <= 0:
            raise ValueError('Recorded fixture submission_id must be a positive integer')
        submissions[submission_id] += 1
        if row.get('kind') != 'recorded_trace':
            raise ValueError(f'{fixture_id}: kind must be recorded_trace')
        if row.get('provenance') != PROVENANCE:
            raise ValueError(f'{fixture_id}: missing exact recorded-action provenance')
        if row.get('adaptive') is not False:
            raise ValueError(f'{fixture_id}: recorded trace cannot be adaptive')
        if row.get('executable') is not False:
            raise ValueError(f'{fixture_id}: recorded trace cannot claim executable policy')
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError('Recorded fixture IDs are not unique')
    if expected_unique_submissions is not None:
        if len(submissions) != expected_unique_submissions:
            raise ValueError(
                f'Expected {expected_unique_submissions} distinct submission versions, '
                f'got {len(submissions)}')
        if expected_fixtures == expected_unique_submissions * 3 and set(submissions.values()) != {3}:
            raise ValueError('Every submission version must contribute exactly three fixtures')
    return submissions


def retain_and_extend(legacy, additions):
    result = deepcopy(legacy)
    if not isinstance(result, dict) or not isinstance(result.get('opponents'), list):
        raise ValueError('Legacy input must be an object with opponents array')
    if 'additive_intake' in result:
        raise ValueError('Legacy registry already uses reserved additive_intake field')
    old = result['opponents']
    legacy_count = len(old)
    ids = [r['id'] for r in old]
    if len(ids) != len(set(ids)):
        raise ValueError('Legacy opponent IDs are not unique')
    incoming = [r['id'] for r in additions]
    if len(incoming) != len(set(incoming)) or set(ids).intersection(incoming):
        raise ValueError('Duplicate/colliding opponent ID')
    validate_recorded_additions(additions)
    result['opponents'].extend(deepcopy(additions))
    result['additive_intake'] = {'legacy_entries':legacy_count,
        'added_entries':len(additions), 'kind':'public-recorded-actions',
        'submission_hold':True, 'legacy_preserved':True}
    return result


def build_union_receipt(legacy, extended, additions, *, legacy_source_sha256,
                        source_manifest_sha256,
                        expected_unique_submissions=EXPECTED_UNIQUE_SUBMISSIONS,
                        expected_fixtures=EXPECTED_FIXTURES):
    if not isinstance(legacy, dict) or not isinstance(legacy.get('opponents'), list):
        raise ValueError('Legacy input must be an object with opponents array')
    if not isinstance(extended, dict) or not isinstance(extended.get('opponents'), list):
        raise ValueError('Extended input must be an object with opponents array')
    legacy_count = len(legacy['opponents'])
    if extended['opponents'][:legacy_count] != legacy['opponents']:
        raise ValueError('Extended registry mutated or reordered legacy opponents')
    for key, value in legacy.items():
        if key == 'opponents':
            continue
        if extended.get(key) != value:
            raise ValueError(f'Extended registry mutated legacy top-level field: {key}')
    appended = extended['opponents'][legacy_count:]
    if appended != additions:
        raise ValueError('Extended registry additions differ from materialized corpus')
    submissions = validate_recorded_additions(
        appended,
        expected_unique_submissions=expected_unique_submissions,
        expected_fixtures=expected_fixtures,
    )
    intake = extended.get('additive_intake')
    if not isinstance(intake, dict):
        raise ValueError('Extended registry lacks additive_intake receipt')
    expected_intake = {
        'legacy_entries': legacy_count,
        'added_entries': len(appended),
        'kind': 'public-recorded-actions',
        'submission_hold': True,
        'legacy_preserved': True,
        'legacy_source_sha256': legacy_source_sha256,
    }
    if intake != expected_intake:
        raise ValueError('Extended registry additive_intake metadata drift')
    return {
        'schema': 'titan.gauntlet.union-receipt.v1',
        'legacy_source_sha256': legacy_source_sha256,
        'source_manifest_sha256': source_manifest_sha256,
        'legacy_entries': legacy_count,
        'added_entries': len(appended),
        'merged_entries': len(extended['opponents']),
        'unique_submission_targets': len(submissions),
        'fixtures_per_submission': 3,
        'legacy_exact_prefix': True,
        'legacy_top_level_fields_preserved': True,
        'new_fixture_kind': 'recorded_trace',
        'new_fixture_provenance': PROVENANCE,
        'all_new_adaptive': False,
        'all_new_executable': False,
        'submission_hold': True,
    }


def materialize(corpus, output):
    corpus = corpus.resolve(strict=True)
    manifest_path = corpus/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['schema'] != 'titan.gauntlet.top30-union.v1':
        raise ValueError('Unexpected corpus schema')
    _validate_target_manifest(manifest)
    output.mkdir(parents=True, exist_ok=False)
    additions = []
    for target in manifest['targets']:
        for fixture in target['replays']:
            path = (corpus/fixture['path']).resolve(strict=True)
            if not path.is_relative_to(corpus) or digest(path) != fixture['sha256']:
                raise ValueError('Replay path or digest mismatch')
            replay = json.loads(gzip.decompress(path.read_bytes()))
            if replay.get('info', {}).get('seed') != fixture['seed']:
                raise ValueError('Replay seed differs from manifest')
            tape = action_tape(replay, fixture['recorded_opponent_seat'])
            name = f"trace-sub-{target['submission_id']}-ep-{fixture['episode_id']}"
            directory = output/name; directory.mkdir()
            write_json(directory/'actions.json', tape)
            adapter = directory/'main.py'
            adapter.write_text('''from copy import deepcopy
import json
from pathlib import Path
_actions = json.loads((Path(__file__).parent/'actions.json').read_text())
def agent(observation, configuration=None):
    step = observation.get('step')
    if step is None:
        turns = int((configuration or {}).get('turnsPerDay',24))
        step = int(observation['day'])*turns+int(observation['hour'])
    if not isinstance(step,int) or not 0 <= step < len(_actions):
        raise ValueError('Recorded trace is exhausted or clock is invalid')
    return deepcopy(_actions[step])
''', encoding='utf-8')
            additions.append({'id':name,'kind':'recorded_trace',
                'provenance':PROVENANCE,'executable':False,
                'family':f"recorded-submission:{target['submission_id']}",
                'submission_id':target['submission_id'],'team_id':target['team_id'],
                'team_name':target['team_name'],'memberships':target['memberships'],
                'episode_id':fixture['episode_id'],'seed':fixture['seed'],
                'recorded_opponent_seat':fixture['recorded_opponent_seat'],
                'candidate_seat_for_recorded_orientation':1-fixture['recorded_opponent_seat'],
                'entry':str(adapter.resolve()),'entry_sha256':digest(adapter),
                'actions_sha256':digest(directory/'actions.json'),
                'replay_sha256':fixture['sha256'],'decisions':len(tape),
                'adaptive':False,'interpretation':'Counterfactual recorded-action opponent; seat swap or new seed is a synthetic stress case.'})
    validate_recorded_additions(
        additions,
        expected_unique_submissions=EXPECTED_UNIQUE_SUBMISSIONS,
        expected_fixtures=EXPECTED_FIXTURES,
    )
    result={'schema':'titan.gauntlet.recorded-opponents.v1',
        'source_manifest_sha256':digest(manifest_path),'submission_hold':True,
        'opponents':additions,'targets':len(manifest['targets'])}
    write_json(output/'recorded-opponents.json', result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--legacy-registry',type=Path)
    args=p.parse_args()
    result=materialize(args.corpus,args.out)
    if args.legacy_registry:
        legacy=json.loads(args.legacy_registry.read_text(encoding='utf-8'))
        extended=retain_and_extend(legacy,result['opponents'])
        legacy_sha=digest(args.legacy_registry)
        extended['additive_intake']['legacy_source_sha256']=legacy_sha
        write_json(args.out/'extended-gauntlet.json',extended)
        receipt=build_union_receipt(
            legacy, extended, result['opponents'],
            legacy_source_sha256=legacy_sha,
            source_manifest_sha256=result['source_manifest_sha256'],
        )
        write_json(args.out/'GAUNTLET-UNION-RECEIPT.json',receipt)
    print(json.dumps({'targets':result['targets'],'fixtures':len(result['opponents']),
        'legacy_extended':bool(args.legacy_registry),'output':str(args.out)}))


if __name__=='__main__':main()

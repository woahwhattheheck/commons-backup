# SPDX-License-Identifier: Apache-2.0
"""Extract causal own/public history from the retained PRISM development archive.

No engine or policy is called. Inputs are the immutable source archive. Runtime
payloads never contain the other actor's action/private observation or the
terminal response. Historical provenance and outcome checks stay in index.json,
which is not an actor input. Clock normalization matches the archived evaluator.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import zipfile

SOURCE_SHA256 = '2f8566ed9cd7cd04d342216c9eb5922f3d8bd361ffd952994439e10e9771907a'
EVALUATOR_SHA256 = 'bb5553a746989f3e854d4639c9d50839b1633b77faffcf49d3e9a748603711e6'
SCHEMA = 'titan.public-own-history.v1'
OBSERVATION_FIELDS = ('farms', 'private', 'market', 'town', 'day', 'hour', 'player')


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked_member(archive, manifest, name):
    row = manifest[name]
    data = archive.read(name)
    if len(data) != row['size'] or sha(data) != row['sha256']:
        raise ValueError('Source member hash/size mismatch: ' + name)
    return data


def normalize_observation(raw, *, player, step, configuration):
    """Materialize exactly the public/own delivery surface, not evaluation data."""
    if raw.get('player') != player:
        raise ValueError('Observation belongs to a different actor')
    obs = {name: deepcopy(raw[name]) for name in OBSERVATION_FIELDS}
    if obs['day'] * configuration['turnsPerDay'] + obs['hour'] != step:
        raise ValueError('Recorded day/hour disagrees with next decision step')
    # The trace captures the post-interpreter observation before the driver
    # overwrites its stored old step and overage for the next actual call.
    obs['step'] = step
    obs['remainingOverageTime'] = 0
    return obs


def extract_payload(rows, configuration, player):
    """Consume an initialization row and one POST-action row per decision.

    At decision t the observation is in row t and the action authored for t is
    in row t+1 (whose step is t). The final post-action row is used ONLY to read
    the already-selected own action. Its observations/rewards/status never enter
    this payload. Structural checks use it only to establish trace completeness.
    """
    cfg = deepcopy(configuration)
    if player not in (0, 1) or type(player) is not int:
        raise ValueError('Expected player 0 or 1')
    cfg.pop('seed', None)
    stop = cfg['episodeSteps'] - 2
    if type(stop) is not int or stop < 1 or len(rows) != stop + 2:
        raise ValueError('Expected one initialization and every complete action row')
    for i, row in enumerate(rows):
        if row['step'] != i - 1:
            raise ValueError('Missing, duplicate, or out-of-order action row')
        if len(row['observations']) != 2 or len(row['actions']) != 2:
            raise ValueError('Expected two actors in each source row')
        expected = ['DONE', 'DONE'] if i == len(rows) - 1 else ['ACTIVE', 'ACTIVE']
        if row['status'] != expected:
            raise ValueError('Premature/incomplete terminal boundary')
    observations = [normalize_observation(rows[t]['observations'][player],
                    player=player, step=t, configuration=cfg) for t in range(stop + 1)]
    actions = [deepcopy(rows[t+1]['actions'][player]) for t in range(stop + 1)]
    if any(not isinstance(action, dict) for action in actions):
        raise ValueError('Recorded own action must be an object')
    return {'schema': SCHEMA, 'configuration': cfg,
            'history': [{'observation': observations[t], 'own_action': actions[t]}
                        for t in range(stop)],
            'observation': observations[stop], 'selected_action': actions[stop]}


def source_configuration(archive, manifest):
    packed = checked_member(archive, manifest, 'inputs/pinned-engine.zip')
    with zipfile.ZipFile(io.BytesIO(packed)) as engine_archive:
        names = [name for name in engine_archive.namelist() if name.endswith('/kaggriculture.json')]
        if len(names) != 1:
            raise ValueError('Expected a unique pinned engine specification')
        spec_bytes = engine_archive.read(names[0])
    spec = json.loads(spec_bytes)
    configuration = {key: value.get('default') if isinstance(value, dict) else value
                     for key, value in spec['configuration'].items()}
    configuration.pop('seed', None)
    # This adapter is for the exact archived invocation with no episode override.
    sourcepack = checked_member(archive, manifest, 'inputs/reusable-sources.zip')
    with zipfile.ZipFile(io.BytesIO(sourcepack)) as outer:
        with tarfile.open(fileobj=io.BytesIO(outer.read('titan-reusable-sources.tar'))) as tar:
            names = [name for name in tar.getnames() if name.endswith('/cloud-eval/evaluate.py')]
            if len(names) != 1:
                raise ValueError('Expected a unique archived evaluator')
            evaluator = tar.extractfile(names[0]).read()
    if sha(evaluator) != EVALUATOR_SHA256:
        raise ValueError('Different evaluator delivery semantics')
    return configuration, {'specification_sha256': sha(spec_bytes),
                           'evaluator_sha256': sha(evaluator)}


def run(source, output):
    source_bytes = Path(source).read_bytes()
    if sha(source_bytes) != SOURCE_SHA256:
        raise ValueError('Use the exact PRISM development archive, not a substitute')
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new output directory; preserve existing evidence')
    output.mkdir(parents=True, exist_ok=True)
    (output/'runtime').mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as archive:
        manifest = json.loads(archive.read('MANIFEST.json'))['members']
        for name in manifest:
            checked_member(archive, manifest, name)
        configuration, pins = source_configuration(archive, manifest)
        results = json.loads(checked_member(archive, manifest, 'work/dev1/results.json'))
        if results['classification'] != 'development' or results['held_seeds'] or not results['complete']:
            raise ValueError('Only the completed development collection is supported')
        if results['dependencies']['evaluator'] != pins['evaluator_sha256']:
            raise ValueError('Result and actual evaluator disagree')
        records = []
        for game in results['games']:
            name = 'work/dev1/' + game['trace_file']
            data = checked_member(archive, manifest, name)
            if sha(data) != game['trace_sha256']:
                raise ValueError('Game source and trace hash disagree')
            plain = gzip.decompress(data)
            if sha(plain) != game['full_transition_sha256']:
                raise ValueError('Lossless transition stream hash disagrees')
            rows = [json.loads(line) for line in plain.splitlines()]
            if rows[-1]['rewards'] != game['scores'] or game['steps'] != configuration['episodeSteps'] - 1:
                raise ValueError('Original completion record does not match trace')
            payload = extract_payload(rows, configuration, game['candidate_seat'])
            raw = encoded(payload)
            digest = sha(raw)
            compressed = gzip.compress(raw, mtime=0)
            target = 'runtime/' + digest + '.json.gz'
            (output/target).write_bytes(compressed)
            margins = payload['observation']['farms']
            seat = game['candidate_seat']
            lead = margins[seat]['money'] - margins[1-seat]['money']
            records.append({'identity': game['identity'], 'seed': game['seed'],
                'arm': game['arm'], 'opponent': game['opponent'], 'player': seat,
                'source_trace_member': name, 'source_trace_sha256': sha(data),
                'source_transition_sha256': sha(plain), 'source_rows': len(rows),
                'runtime_member': target, 'runtime_sha256': digest,
                'runtime_gzip_sha256': sha(compressed), 'history_decisions': len(payload['history']),
                'decision_step': payload['observation']['step'],
                'final_selected_action_sha256': sha(encoded(payload['selected_action'])),
                'public_pre_action_lead': lead,
                'original_scores_evaluation_only': game['scores']})
        index = {'schema': 'titan.prism-history-index.v1',
            'actor_input': False, 'source_archive_sha256': SOURCE_SHA256,
            'verified_source_members': len(manifest), 'pins': pins,
            'original_dependencies': results['dependencies'],
            'frozen_sell_closure': results['frozen_sell_closure'],
            'records': records, 'new_engine_calls': 0, 'new_policy_calls': 0,
            'new_games': 0, 'independent_development_seeds': len({r['seed'] for r in records}),
            'unique_runtime_payloads': len({r['runtime_sha256'] for r in records}),
            'scope': 'Retained own/public history extraction, not a new game or scenario forecast.'}
        (output/'index.json').write_bytes(encoded(index) + b'\n')
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.archive, args.output)
    print(json.dumps({'records': len(result['records']),
        'unique_runtime_payloads': result['unique_runtime_payloads'],
        'history_decisions_per_record': sorted({r['history_decisions'] for r in result['records']}),
        'independent_development_seeds': result['independent_development_seeds'],
        'new_engine_calls': 0, 'new_policy_calls': 0, 'new_games': 0}, indent=2))


if __name__ == '__main__':
    main()

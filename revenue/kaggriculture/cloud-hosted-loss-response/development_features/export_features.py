# SPDX-License-Identifier: MIT
"""Export T13 development labels and available *original* checkpoint observations.

This is an offline data importer, not a policy, simulator, or selector trainer.
Seed/opponent/terminal labels remain outside the runtime feature dictionary.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_COMMIT = 'd87f5e6ef3a578128b0d34a7a1d22959b0948e21'
SCORES_BLOB = 'a296802b4e2b162f62a6114dae36b1e54b0978f3'
FEATURE_COMMIT = 'e987ed4eec0c27223de7432a8bce88ff7e062697'
FEATURE_BLOB = 'd8a7d7e3b833c2071fa1c29d80a51951524fd737'
ENGINE_REF = '28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c'
DEVELOPMENT = (9850001, 9850019, 9850037)
REPORTS = {
    'dev0-sell-import.json': ('dev_sell', 7940508, '7713b6e71051b785389a3b86c4a04cde1d24557f6b90e4a9d0d83176c61cf19b'),
    'dev12-sell.json': ('dev_sell', 15728285, 'a99345a4e42a678708151a084596cd0808d072738eec371df8c37a44b93fc453'),
    'dev-frozen-sell.json': ('dev_sell', 11800850, '3f3a6a00bf2a4cfaa4b2de03c74b75934b06d3cf3633d6136f048eab3502063b'),
    'dev-seed.json': ('dev_seed', 35459575, '6c6f18c078861d5806ceb3f5e891327f8dec78fefd3774ec58c8c988a280b502'),
}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def load_extractor(path):
    """Import the exact already-published ASTER feature implementation."""
    path = Path(path)
    data = path.read_bytes()
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if blob != FEATURE_BLOB:
        raise ValueError('Feature source differs from the pinned ASTER implementation')
    spec = importlib.util.spec_from_file_location('t13_aster_features', path)
    if spec is None or spec.loader is None:
        raise ValueError('Cannot load feature source')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.extract


def load_scores(path):
    rows = {}
    with Path(path).open(newline='', encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            key = (row['panel'], int(row['seed']), row['opponent'], int(row['seat']))
            panel, seed, opponent, seat = key
            if panel not in ('dev_sell', 'dev_seed') or seed not in DEVELOPMENT or seat not in (0, 1) or opponent not in ('arlene', 'apex', 'frozen'):
                raise ValueError(f'Not a T13 development row: {key}')
            if key in rows:
                raise ValueError(f'Duplicate development row: {key}')
            trace = row['trace_sha256']
            if len(trace) != 64 or any(c not in '0123456789abcdef' for c in trace):
                raise ValueError(f'Invalid trace hash: {key}')
            rows[key] = {'own_cash': int(row['own_cash']), 'rival_cash': int(row['rival_cash']), 'trace_sha256': trace}
    expected = {(p, s, o, i) for p in ('dev_sell', 'dev_seed') for s in DEVELOPMENT for o in ('arlene', 'apex', 'frozen') for i in (0, 1)}
    if set(rows) != expected:
        raise ValueError('The development index must contain exactly the 36 paired source rows')
    return rows


def report_for(key):
    panel, seed, opponent, _ = key
    if panel == 'dev_seed':
        return 'dev-seed.json'
    if opponent == 'frozen':
        return 'dev-frozen-sell.json'
    return 'dev0-sell-import.json' if seed == 9850001 else 'dev12-sell.json'


def observation(snapshot, seat):
    """Reconstruct only fields retained by measure.py before the unit phase.

    This is a projection, not a claim to retain every original observation key.
    Both farms are public; only this player's private dictionary is selected.
    The snapshot's market-valued `prices` field is not merely price quotes.
    """
    if seat not in (0, 1) or type(seat) is not int:
        raise ValueError('Invalid observation seat')
    if len(snapshot['farms']) != 2 or len(snapshot['private']) != 2:
        raise ValueError('Expected two public farms and two evaluator private views')
    return copy.deepcopy({'step': snapshot['step'], 'player': seat,
                          'market': snapshot['prices'], 'town': snapshot['shops'],
                          'farms': snapshot['farms'], 'private': snapshot['private'][seat]})


def import_game(game, key, expected, extract):
    """Bind one original measurement to its published result, then project it."""
    _, seed, opponent, seat = key
    if (game['seed'], game['opponent'], game['candidate_seat']) != (seed, opponent, seat):
        raise ValueError('Game identity mismatch')
    if game['status'] != 'complete' or game.get('failure') is not None:
        raise ValueError('Only complete original games are measurements')
    if game['trace_sha256'] != expected['trace_sha256']:
        raise ValueError('Original full trace does not match its published result')
    if game['scores'][seat] != expected['own_cash'] or game['scores'][1 - seat] != expected['rival_cash']:
        raise ValueError('Terminal cash does not match its published result')
    projected = {}
    for snapshot in game['timeline']:
        step = snapshot['step']
        if type(step) is not int or step < 0:
            raise ValueError('Invalid timeline step')
        if step > 360:
            continue
        if step in projected:
            raise ValueError('Duplicate timeline step')
        projected[step] = observation(snapshot, seat)
    obs = projected.get(360)
    return {'observation': obs, 'features': extract(copy.deepcopy(obs)) if obs is not None else None,
            'observation_sha256': digest(obs) if obs is not None else None,
            'sampled_prefix': {str(t): digest(o) for t, o in sorted(projected.items()) if t < 360},
            'availability': 'original_checkpoint' if obs is not None else 'checkpoint_missing'}


def read_original(path, specification):
    _, size, expected_sha = specification
    data = Path(path).read_bytes()
    if len(data) != size or hashlib.sha256(data).hexdigest() != expected_sha:
        raise ValueError(f'Original report bytes do not match the published digest: {Path(path).name}')
    report = json.loads(data, parse_constant=lambda text: (_ for _ in ()).throw(ValueError(text)))
    if report.get('engine_ref') != ENGINE_REF:
        raise ValueError('Official engine pin differs')
    return report


def build(scores, reports, extract=None):
    if reports and extract is None:
        raise ValueError('The pinned feature source is needed to attach original observations')
    attached = {}
    for path in reports:
        name = Path(path).name
        if name not in REPORTS:
            raise ValueError('Only the four published development reports belong in this import')
        spec = REPORTS[name]
        report = read_original(path, spec)
        found = set()
        for game in report['games']:
            key = (spec[0], game['seed'], game['opponent'], game['candidate_seat'])
            if key not in scores or report_for(key) != name or key in attached:
                raise ValueError(f'Unexpected or duplicate original game: {key}')
            attached[key] = import_game(game, key, scores[key], extract)
            found.add(key)
        if found != {k for k in scores if report_for(k) == name}:
            raise ValueError(f'Original report is missing expected games: {name}')
    records = []
    for key, labels in sorted(scores.items()):
        panel, seed, opponent, seat = key
        source_name = report_for(key)
        records.append({'join': {'panel': panel, 'seed': seed, 'opponent': opponent, 'seat': seat},
                        'labels': labels, 'original_report': source_name,
                        **attached.get(key, {'observation': None, 'features': None, 'observation_sha256': None,
                                             'sampled_prefix': None, 'availability': 'raw_report_not_attached'})})
    pairs = []
    for seed in DEVELOPMENT:
        for opponent in ('arlene', 'apex', 'frozen'):
            for seat in (0, 1):
                keys = [(p, seed, opponent, seat) for p in ('dev_sell', 'dev_seed')]
                a, b = [attached.get(k) for k in keys]
                obs_equal = None
                common, mismatches, sampled_equal = [], [], None
                if a is not None and b is not None:
                    pa, pb = a['sampled_prefix'], b['sampled_prefix']
                    common = sorted(set(pa) & set(pb), key=int)
                    mismatches = [int(t) for t in common if pa[t] != pb[t]]
                    if common and set(pa) == set(pb):
                        sampled_equal = not mismatches
                    if a['observation'] is not None and b['observation'] is not None:
                        obs_equal = a['observation'] == b['observation']
                old, new = [scores[k] for k in keys]
                pairs.append({'join': {'seed': seed, 'opponent': opponent, 'seat': seat},
                              'own_cash_delta': new['own_cash'] - old['own_cash'],
                              'rival_cash_delta': new['rival_cash'] - old['rival_cash'],
                              'checkpoint_observation_equal': obs_equal,
                              'sampled_prefix_equal': sampled_equal, 'sampled_prefix_common_count': len(common),
                              'sampled_prefix_mismatch_steps': mismatches,
                              'full_prefix_equal': None, 'continuation_pair_eligible': None})
    return {'schema': 't13.development-features.v1', 'checkpoint': {'step': 360, 'stage': 'pre_unit'},
            'provenance': {'source_commit': SOURCE_COMMIT, 'source_scores_blob': SCORES_BLOB,
                           'feature_commit': FEATURE_COMMIT, 'feature_blob': FEATURE_BLOB,
                           'report_sha256': {name: value[2] for name, value in REPORTS.items()}},
            'limitations': 'Development only. Labels/join metadata are not runtime features. Sparse samples never prove a full common prefix. No held rows, simulated replacements, new games or selector changes.',
            'records': records, 'pairs': pairs,
            'summary': {'development_pairs': len(pairs), 'label_rows': len(records),
                        'available_checkpoints': sum(r['observation'] is not None for r in records),
                        'new_games': 0, 'full_prefix_proven_pairs': 0}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scores', type=Path, default=HERE / 'development-scores.csv')
    parser.add_argument('--report', type=Path, action='append', default=[])
    parser.add_argument('--feature-source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(load_scores(args.scores), args.report,
                   load_extractor(args.feature_source) if args.feature_source else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(result['summary'], sort_keys=True))


if __name__ == '__main__':
    main()

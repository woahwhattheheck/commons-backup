# SPDX-License-Identifier: Apache-2.0
"""Preserve historical development labels with explicit feature availability."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from features import extract


def import_t08(paths):
    rows = []
    for path in paths:
        data = json.loads(path.read_text())
        for game in data['games']:
            if game['status'] != 'complete':
                continue
            seat = game['candidate_seat']
            own, rival = game['scores'][seat], game['scores'][1-seat]
            rows.append({'policy': data['arm'], 'seed': game['seed'], 'seat': seat, 'opponent': game['opponent'],
                'panel': 'historical_development', 'source_commit': '291957d2c9ba0b035d496243775fcf76fef6f38f',
                'source_path': 'revenue/kaggriculture/cloud-titan-composition/results/' + path.name.removeprefix('t08-'),
                'label_observed_at_step': 718, 'own_cash': own, 'rival_cash': rival,
                'features': None, 'feature_observed_at_step': None,
                'training_eligible': False, 'reason': 'outcome record has no decision-time observation',
                'source_file_sha256': hashlib.sha256(path.read_bytes().rstrip(b'\n')+b'\n').hexdigest()})
    return rows


def import_protocol(directory):
    rows = []
    metadata = json.loads((directory / 'INPUTS.json').read_text())
    for path in sorted((directory / 'traces').glob('*.jsonl.gz')):
        if path.name not in metadata['traces']:
            raise ValueError('Trace not in published development manifest')
        if hashlib.sha256(path.read_bytes()).hexdigest() != metadata['traces'][path.name][1]:
            raise ValueError('Trace bytes differ')
        points, last = {}, None
        with gzip.open(path, 'rt') as source:
            for line in source:
                last = json.loads(line)
                if last['step'] in (0, 360):
                    points[str(last['step'])] = extract(last['observation'])
        if not last or not last['done']:
            raise ValueError('Trace has no terminal observation')
        seat = last['candidate_seat']
        rows.append({'source_commit': metadata['source_commit'], 'trace_file': path.name,
            'trace_sha256': metadata['traces'][path.name][1], 'panel': 'historical_development',
            'policy': 'frozen_sell', 'features_by_observation_step': points, 'seat': seat,
            'label_observed_at_step': last['step'], 'own_cash': last['post_cash'][seat],
            'rival_cash': last['post_cash'][1-seat], 'paired_alternative_label': None,
            'training_eligible': False, 'reason': 'single-policy observation stream; no matched alternative label'})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--t08', nargs='+', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = import_t08(args.t08) + import_protocol(args.protocol)
    args.output.write_text(json.dumps({'schema_version': 1, 'rows': rows,
        'known_late_features': ['future shop unlocks', 'future market prices', 'final own/rival cash'],
        'grouping_only': ['environment seed', 'opponent identifier'],
        'historical_held_used': False}, indent=2)+'\n')


if __name__ == '__main__':
    main()

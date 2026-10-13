# SPDX-License-Identifier: Apache-2.0
"""Fit small observation-only trees to eligible paired development outcomes."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from features import predict

POLICIES = ('sell', 'carrot_sell')
ORDER = {'L': 0, 'T': 1, 'W': 2}


def rows_from_panels(panels):
    grouped = defaultdict(dict)
    excluded = []
    for path in panels:
        report = json.loads(Path(path).read_text())
        if report.get('panel') != 'development':
            raise ValueError('Only explicitly labeled development panels may enter training')
        for game in report['games']:
            if game['arm'] not in POLICIES:
                continue
            key = (game['seed'], game['opponent'], game['candidate_seat'])
            if game['arm'] in grouped[key]:
                raise ValueError('Repeated paired label: ' + str(key))
            grouped[key][game['arm']] = game
    paired = []
    for key, games in sorted(grouped.items()):
        reason = None
        if set(games) != set(POLICIES):
            reason = 'missing_coherent_counterfactual'
        elif any(g['status'] != 'complete' for g in games.values()):
            reason = 'incomplete_game'
        elif any('360' not in g.get('checkpoints', {}) for g in games.values()):
            reason = 'missing_decision_time_observation'
        elif len({g['prefix_before_360_sha256'] for g in games.values()}) != 1:
            reason = 'different_action_prefix'
        elif len({g['checkpoints']['360']['observation_sha256'] for g in games.values()}) != 1:
            reason = 'different_checkpoint_observation'
        if reason:
            excluded.append({'seed': key[0], 'opponent': key[1], 'seat': key[2], 'reason': reason})
            continue
        checkpoint = games['sell']['checkpoints']['360']
        if checkpoint['observed_at_step'] != 360 or checkpoint['available_before_action'] is not True:
            raise ValueError('Checkpoint is not an observed pre-action feature row')
        paired.append({'seed': key[0], 'opponent': key[1], 'seat': key[2],
            'feature_observed_at_step': 360, 'label_observed_at_step': 718,
            'features': checkpoint['features'],
            'checkpoint_observation_sha256': checkpoint['observation_sha256'],
            'prefix_before_360_sha256': games['sell']['prefix_before_360_sha256'],
            'labels': {p: {k: g[k] for k in ('own_cash', 'rival_cash', 'margin', 'outcome', 'trace_file_sha256', 'engine_ref', 'evaluator_sha256')}
                       for p, g in games.items()}})
    return paired, excluded


def utility(rows, policy):
    # Aggregate W/T/L first. Use paired realized margin only as a tie-break.
    # The scale is not a probability, predicted price, or runtime feature.
    return (sum(ORDER[r['labels'][policy]['outcome']] for r in rows),
            sum(r['labels'][policy]['margin'] for r in rows),
            -len(rows) if policy != 'sell' else 0)


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def leaf(rows):
    winner = max(POLICIES, key=lambda p: (utility(rows, p), -POLICIES.index(p)))
    return {'policy': winner, 'support_rows': len(rows), 'support_seeds': len({r['seed'] for r in rows})}


def fit(rows, depth=2, min_leaf=4):
    if not rows:
        return {'policy': 'sell', 'support_rows': 0, 'support_seeds': 0}
    best = leaf(rows)
    best_score = utility(rows, best['policy'])
    if depth == 0 or len(rows) < 2 * min_leaf:
        return best
    for feature in sorted(rows[0]['features']):
        values = sorted({r['features'].get(feature) for r in rows if r['features'].get(feature) is not None})
        for a, b in zip(values, values[1:]):
            threshold = (a + b) / 2
            left = [r for r in rows if r['features'].get(feature) is None or r['features'][feature] <= threshold]
            right = [r for r in rows if r['features'].get(feature) is not None and r['features'][feature] > threshold]
            if min(len(left), len(right)) < min_leaf:
                continue
            l, rr = leaf(left), leaf(right)
            score = add(utility(left, l['policy']), utility(right, rr['policy']))
            if score > best_score:
                best_score = score
                best = {'feature': feature, 'threshold': threshold, 'missing': 'left',
                        'left': fit(left, depth - 1, min_leaf), 'right': fit(right, depth - 1, min_leaf)}
    return best


def evaluate(rows, tree):
    counts = {p: {k: 0 for k in ('W', 'T', 'L')} for p in (*POLICIES, 'router')}
    money = {p: {'own_cash': 0, 'rival_cash': 0, 'margin': 0} for p in counts}
    choices = defaultdict(int)
    flips = defaultdict(int)
    for row in rows:
        selected = predict(tree, row['features'])
        choices[selected] += 1
        for name in counts:
            label = row['labels'][selected if name == 'router' else name]
            counts[name][label['outcome']] += 1
            for key in money[name]:
                money[name][key] += label[key]
        flips[row['labels']['sell']['outcome'] + '->' + row['labels'][selected]['outcome']] += 1
    return {'rows': len(rows), 'wtl': counts, 'cash_totals': money, 'choices': dict(choices), 'paired_flips_vs_sell': dict(flips)}


def cross_validate(rows, group):
    folds = []
    for held in sorted({r[group] for r in rows}):
        train = [r for r in rows if r[group] != held]
        test = [r for r in rows if r[group] == held]
        tree = fit(train)
        folds.append({'left_out': held, 'train_rows': len(train), 'tree': tree, 'evaluation': evaluate(test, tree)})
    return folds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--panels', nargs='+', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows, excluded = rows_from_panels(args.panels)
    tree = fit(rows)
    dataset = {'schema_version': 1, 'panel': 'development', 'rows': rows, 'excluded': excluded,
               'sources': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in args.panels}}
    (args.output / 'paired-development.json').write_text(json.dumps(dataset, indent=2)+'\n')
    report = {'fit': evaluate(rows, tree), 'leave_seed_out': cross_validate(rows, 'seed'),
              'leave_opponent_out': cross_validate(rows, 'opponent'),
              'missing_label_policy': 'preserve and exclude; never impute outcomes'}
    (args.output / 'training-report.json').write_text(json.dumps(report, indent=2)+'\n')
    model = {'schema_version': 1, 'status': 'frozen_candidate', 'checkpoint': 360,
             'tree': tree, 'training_sha256': hashlib.sha256((args.output / 'paired-development.json').read_bytes()).hexdigest(),
             'runtime_input': 'features extracted before action360; no seed or opponent identity'}
    (args.output / 'model.json').write_text(json.dumps(model, indent=2)+'\n')
    print(json.dumps({'tree': tree, 'fit': report['fit'], 'excluded': len(excluded)}, indent=2))


if __name__ == '__main__':
    main()

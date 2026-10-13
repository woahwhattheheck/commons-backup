# SPDX-License-Identifier: Apache-2.0
"""Summarize retained panels; this script does not fit or run any policy."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from features import predict

HERE = Path(__file__).resolve().parent


def summarize():
    freeze = json.loads((HERE / 'FREEZE.json').read_text())
    mismatches = [name for name, sha in freeze['files'].items()
                  if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != sha]
    if mismatches:
        raise ValueError(('Frozen source changed', mismatches))
    tree = freeze['model']['tree']
    panels = {}
    for name in ('development', 'families', 'active-regime', 'validation', 'conditional-validation'):
        data = json.loads((HERE / 'results' / name / 'panel.json').read_text())
        rows = data['games']
        arms = {}
        for arm in data['arms']:
            selected = [r for r in rows if r['arm'] == arm]
            count = Counter(r.get('outcome') for r in selected)
            timings = [r['actors'][r['candidate_seat']] for r in selected]
            arms[arm] = {'games': len(selected), 'wtl': {k: count[k] for k in ('W', 'T', 'L')},
                'own_cash': sum(r['own_cash'] for r in selected),
                'rival_cash': sum(r['rival_cash'] for r in selected),
                'max_whole_agent_call_seconds': max(t['max_call_seconds'] for t in timings),
                'max_actor_cpu_seconds': max(t['cpu_seconds'] for t in timings),
                'max_actor_rss_kib': max(t['peak_rss_kib'] for t in timings)}
        paired = []
        for row in rows:
            if row['arm'] not in ('router', 'carrot_sell'):
                continue
            base = next(r for r in rows if r['arm'] == 'sell' and r['seed'] == row['seed']
                        and r['candidate_seat'] == row['candidate_seat'] and r['opponent'] == row['opponent'])
            if (row['prefix_before_360_sha256'] != base['prefix_before_360_sha256'] or
                    row['checkpoints']['360']['observation_sha256'] != base['checkpoints']['360']['observation_sha256']):
                raise ValueError('Paired decision prefixes differ')
            item = {k: row[k] for k in ('arm', 'seed', 'opponent', 'candidate_seat')}
            item.update(own_cash_delta=row['own_cash']-base['own_cash'],
                        rival_cash_delta=row['rival_cash']-base['rival_cash'],
                        margin_delta=row['margin']-base['margin'],
                        flip=base['outcome']+'->'+row['outcome'],
                        prefix_and_decision_observation_equal=True,
                        action_bank_trace_changed=row['trace_sha256'] != base['trace_sha256'])
            if row['arm'] == 'router':
                choice = predict(tree, row['checkpoints']['360']['features'])
                selected = next(r for r in rows if r['arm'] == choice and r['seed'] == row['seed']
                                and r['candidate_seat'] == row['candidate_seat'] and r['opponent'] == row['opponent'])
                item['choice'] = choice
                item['matches_selected_frozen_policy_trace'] = row['trace_sha256'] == selected['trace_sha256']
                if not item['matches_selected_frozen_policy_trace']:
                    raise ValueError('Router differs from selected coherent policy')
            paired.append(item)
        panels[name] = {'split': data['panel'], 'conditional_sampling': name == 'conditional-validation',
            'seeds': data['seeds'], 'count': len(rows), 'arms': arms, 'paired_comparisons': paired,
            'failures': sum(r['status'] != 'complete' for r in rows),
            'all_games_719_actions': all(r['steps'] == 719 for r in rows)}
    return {'schema_version': 1, 'selected_entry': 'selected.py', 'selected_policy': 'sell',
        'preserved_candidate_entry': 'main.py', 'candidate_status': 'not_promoted',
        'reason': 'Conditional validation changed two SELL wins into losses; no tuning after validation.',
        'total_new_full_games': sum(p['count'] for p in panels.values()), 'panels': panels,
        'freeze_sha256': hashlib.sha256((HERE / 'FREEZE.json').read_bytes()).hexdigest(),
        'frozen_files_verified': len(freeze['files']), 'frozen_files_changed': [],
        'historical_held_games_reused_as_new_validation': 0,
        'screening': [{'file': name, 'searched_seeds': [r['seed'] for r in data['rows']],
                      'selected_seed': data['selected_seed'], 'terminal_labels_read': False}
                     for name in ('regime-screen.json', 'conditional-screen.json')
                     for data in [json.loads((HERE / 'results' / name).read_text())]],
        'validation_note': 'The original held panel and the later observation-conditioned panel remain separate; the latter is not a random-sample performance estimate.',
        'training_note': 'Forty paired development cases across four seeds. Six beneficial choices share one seed; leaving it out loses the fitted gain. Historical missing-feature or missing-label records are excluded.'}


if __name__ == '__main__':
    output = HERE / 'results/SUMMARY.json'
    output.write_text(json.dumps(summarize(), indent=2) + '\n')
    print(output)

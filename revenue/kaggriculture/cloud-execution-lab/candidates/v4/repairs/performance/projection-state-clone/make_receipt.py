# SPDX-License-Identifier: Apache-2.0
"""Summarize every completed local run; reject incomplete or unequal pairs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import statistics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    games = []
    for path in sorted(args.runs.glob('*.json')):
        raw = path.read_bytes(); data = json.loads(raw)
        if data['callbacks'] != 719 or data['statuses'] != {'completed': 719}:
            raise ValueError(f'Incomplete/fallback run, not discarded: {path}')
        if data['requested_seed'] != data['engine_seed'] or data['runtime_members_authenticated'] != 109:
            raise ValueError(f'Unbound provenance: {path}')
        fields = ('arm', 'requested_seed', 'seat', 'optimized', 'profiled', 'instrumented_counts',
                  'callbacks', 'interpreter_calls', 'statuses', 'rewards',
                  'action_trace_sha256', 'state_trace_sha256', 'joint_trace_sha256',
                  'clone_calls', 'agent_wall_seconds', 'agent_cpu_seconds')
        games.append({'file': path.name, 'full_result_sha256': hashlib.sha256(raw).hexdigest(),
                      **{key: data[key] for key in fields}})
    controls = {}
    for game in games:
        if game['arm'] in ('base', 'unitflow'):
            key = (game['arm'], game['requested_seed'], game['seat'], game['optimized'])
            if key in controls and controls[key]['joint_trace_sha256'] != game['joint_trace_sha256']:
                raise ValueError('Baseline self-control trace differs')
            controls[key] = game
    comparisons = 0
    for game in games:
        if game['arm'].endswith('clone'):
            baseline = 'unitflow' if game['arm'].startswith('unitflow') else 'base'
            control = controls[(baseline, game['requested_seed'], game['seat'], game['optimized'])]
            for field in ('action_trace_sha256', 'state_trace_sha256', 'rewards'):
                if game[field] != control[field]:
                    raise ValueError(f'{game["file"]}: unequal {field}, not discarded')
            comparisons += 1
    by_name = {game['file']: game for game in games}
    timing = []
    for rep in range(6):
        base = by_name[f'timing-{rep:02d}-base.json']; cand = by_name[f'timing-{rep:02d}-clone.json']
        if any(g['profiled'] or g['instrumented_counts'] for g in (base, cand)):
            raise ValueError('Instrumented timing pair')
        b, c = base['agent_wall_seconds'], cand['agent_wall_seconds']
        timing.append({'replicate': rep, 'order': ['base', 'clone'] if rep % 2 == 0 else ['clone', 'base'],
                       'base_agent_wall_seconds': b, 'clone_agent_wall_seconds': c,
                       'reduction_percent': 100 * (b - c) / b})
    identities = json.loads((args.runs / 'normal-clone-9922999-0.json').read_text())['materialized_members']
    result = {
        'status': 'CANDIDATE_ONLY_NATIVE_PARITY_SMALL_LOCAL_SPEED_GAIN',
        'release_authorized': False, 'python': '3.13.5',
        'source_artifact': {'id': 10175943272, 'run': 34537404363,
                            'package': 'final-pressure-runtime',
                            'archive_sha256': 'b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9',
                            'source_manifest_sha256': 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'},
        'unitflow_dependency_blob': 'e1127c4aad842278a9e617903b0718d21c00f348',
        'new_source_identities': {k: identities[k] for k in ('frozen_selected.py', 'early_capital.py', 'projection_clone.py')},
        'component_tests': {'normal': 23, 'optimized': 23, 'failures': 0, 'errors': 0, 'skips': 0,
                            'generated_graphs_per_mode': 500, 'assertion_killed_mutants_per_mode': 8,
                            'inherited_tests_per_arm_per_mode': 90,
                            'inherited_arms': ['base', 'clone', 'unitflow', 'unitflow-clone'],
                            'missing_dependency_controls_per_mode': 6,
                            'altered_dependency_controls_per_mode': 6},
        'full_games': len(games), 'native_callbacks': sum(g['callbacks'] for g in games),
        'full_interpreter_calls_including_initialization': sum(g['interpreter_calls'] for g in games),
        'candidate_vs_matched_parent_comparisons': comparisons, 'mismatched_traces': 0,
        'fallbacks': 0, 'timing_pairs': timing,
        'median_paired_agent_time_reduction_percent': statistics.median(t['reduction_percent'] for t in timing),
        'games': games,
        'limits': [
            'Only official_starter opponents and seeds17/9922999; not a field-strength or EV gate.',
            'Timing repeats are serial alternating-order seed9922999 seat0; no excluded or retried completed runs.',
            'Initial normal seed17 seat1 comparison was slower; six designated timing pairs are not a universal speed guarantee.',
            'Whole-game parity covers this authenticated native fixture plus exact UNITFLOW, not the moving complete V4 stack.',
            'Cancellation/deadline-rescue and Python3.11 are not tested.',
            'Custom classes use stdlib deepcopy; assumes standard builtin copy dispatch, not monkeypatched copy internals.',
            'Full per-callback result files remain local; this receipt retains every full-game total/hash, and run_native reproduces full records.',
            'No production/default/archive/workflow/Kaggle mutation.',
        ],
    }
    # Store common complete traces once without discarding any game totals.
    traces = []
    for game in result['games']:
        trace = {key: game.pop(key) for key in
                 ('action_trace_sha256', 'state_trace_sha256', 'joint_trace_sha256', 'rewards')}
        if trace not in traces:
            traces.append(trace)
        game['trace_index'] = traces.index(trace)
    result['trace_table'] = traces
    args.output.write_text(json.dumps(result, separators=(',', ':'), sort_keys=True) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k in ('full_games', 'native_callbacks', 'candidate_vs_matched_parent_comparisons', 'median_paired_agent_time_reduction_percent')}))


if __name__ == '__main__':
    main()

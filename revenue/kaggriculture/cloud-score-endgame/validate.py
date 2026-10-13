# SPDX-License-Identifier: Apache-2.0
"""Validate the new absolute consumer using retained receipts and a test LP.

Dependencies are existing repository files on PYTHONPATH; SciPy is test-only.
No interpreter, provider, game seed or original peer test suite is executed.
"""
from copy import deepcopy
from fractions import Fraction as F
import argparse
import hashlib
from itertools import product
import json
import lzma
from pathlib import Path
import time

import numpy as np
from scipy.optimize import linprog
from full_support import solve_full_table, verify_certificate
from terminal_utility import build_table
from score_endgame import solve_absolute
from test_score_endgame import consumer, document, Draw

ENGINE_CASE_SHA256 = '936b72e34299abad42414265ef7f8e8d61367480b8b86f0e014c3d522f0e848a'


def oracle(rows):
    n, m = len(rows), len(rows[0])
    a = np.array([[float(F(x)) for x in row] for row in rows])
    fit = linprog([0.] * n + [-1.], A_ub=np.column_stack((-a.T, np.ones(m))),
                  b_ub=np.zeros(m), A_eq=[[1.] * n + [0.]], b_eq=[1.],
                  bounds=[(0., 1.)] * n + [(None, None)], method='highs')
    if not fit.success:
        raise AssertionError(fit.message)
    return -fit.fun


def run(engine_cases):
    retained_bytes = engine_cases.read_bytes()
    assert hashlib.sha256(retained_bytes).hexdigest() == ENGINE_CASE_SHA256
    retained = json.loads(lzma.decompress(retained_bytes))
    outputs = []
    for case in retained['cases']:
        doc = case['document']
        answer = solve_absolute(doc, build_table, solve_full_table, verify_certificate)
        terminal = case['name'] != 'not_terminal'
        if terminal:
            target = oracle(build_table(doc)['win_points'])
            assert abs(float(F(answer['value'])) - target) < 1e-9
        actions = []
        for draw in ((0, 1) if case['name'] == 'recover_from_losses' else (0,)):
            obj = consumer(Draw(draw))
            baseline = next(r['own_action'] for r in doc['receipts'] if r['plan'] == doc['baseline'])
            # Complete own actions came from the existing official-engine
            # fixture. This callback checks membership, NOT fresh state physics.
            legal = [r['own_action'] for r in doc['receipts']]
            obs = {'step': doc['source']['step'], 'player': case['player_index']}
            start = time.perf_counter()
            action = obj.transform_terminal(obs, {}, baseline, document=doc,
                                            feasible=lambda a: a in legal)
            seconds = time.perf_counter() - start
            assert action in legal
            index = obj.active['plan_index'] if obj.active else 0
            chosen_id = doc['plan_ids'][index]
            margins = [r['own_cash'] - r['rival_cash'] for r in doc['receipts'] if r['plan'] == chosen_id]
            actions.append({'draw': draw, 'selected_id': chosen_id, 'action': action,
                            'realized_margin_in_each_retained_scenario': margins,
                            'draws': obj.draws, 'provider_calls': obj.provider_calls,
                            'consumer_seconds': seconds})
            if case['name'] == 'varying_baseline':
                assert chosen_id == 'wheat_first' and min(margins) > 0
            if case['name'] in ('protect_all_wins', 'omitted_rival_supply', 'not_terminal'):
                assert action == baseline and obj.draws == 0
        outputs.append({'name': case['name'], 'player_index': case['player_index'],
                        'solution': answer, 'terminal_action_consumption': actions})
    transcript, timings = [], []
    # The previous PORT oracle covered a restricted constant-baseline helper.
    # This exhausts the NEW absolute embedding, including varying baselines.
    for flat in product((0, '1/2', 1), repeat=6):
        rows = [flat[:2], flat[2:4], flat[4:]]
        start = time.perf_counter()
        result = solve_absolute(document(rows), build_table, solve_full_table, verify_certificate)
        timings.append(time.perf_counter() - start)
        expected = oracle(rows)
        error = abs(float(F(result['value'])) - expected)
        assert error < 1e-9, (rows, result, expected)
        transcript.append({'rows': rows, 'value': result['value'], 'weights': result['weights'],
                           'status': result['status'], 'oracle': expected, 'error': error})
    # Larger exact matrices exercise virtual-row offset at the full dimension.
    rng = np.random.default_rng(73009)
    for n, m in ((2, 32), (4, 7), (8, 32), (8, 1)):
        for _ in range(8):
            rows = [[str(F(int(x), 2)) for x in row] for row in rng.integers(0, 3, (n, m))]
            result = solve_absolute(document(rows), build_table, solve_full_table, verify_certificate)
            expected = oracle(rows)
            error = abs(float(F(result['value'])) - expected)
            assert error < 1e-9
            transcript.append({'rows': rows, 'value': result['value'], 'weights': result['weights'],
                               'status': result['status'], 'oracle': expected, 'error': error})
    return {'retained_engine_cases_sha256': ENGINE_CASE_SHA256,
            'retained_engine_ref': retained['engine_ref'],
            'retained_case_count': len(outputs),
            'retained_original_action_transitions': retained['official_action_transitions'],
            'new_engine_transitions': 0, 'new_full_games': 0,
            'scope': 'New consumer on immutable constructed engine receipts; no full-game strength claim.',
            'lp_comparisons': len(transcript),
            'max_lp_absolute_error': max(r['error'] for r in transcript),
            'small_table_consumer_seconds': {'max': max(timings),
                'p95': sorted(timings)[int(.95 * len(timings))]},
            'cases': outputs, 'oracle_transcript': transcript}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-cases', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.engine_cases)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('cases', 'oracle_transcript')}, indent=2))

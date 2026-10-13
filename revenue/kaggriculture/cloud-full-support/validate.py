# SPDX-License-Identifier: Apache-2.0
"""Reproducible algebraic validation; no engine, network, or gameplay execution."""
from __future__ import annotations
import argparse
from fractions import Fraction as F
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import random
import statistics
import time

from full_support import solve_full_table, verify_certificate


def identity(path):
    body = Path(path).read_bytes()
    return {'git_blob': hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest(),
            'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}


def corpus(count=256):
    rng = random.Random(775104)  # Synthetic matrix generator, not a game seed.
    for k in range(count):
        n = 2 + k % 8
        m = 1 + (k // 8) % 32
        d = [[0] * m] + [[rng.randint(-15, 20) for _ in range(m)] for _ in range(n-1)]
        if k % 7 == 0:
            d = [[str(F(x, rng.choice([1, 3, 7]))) for x in r] for r in d]
        if k % 11 == 0 and n > 2:
            d[-1] = d[1][:]
        yield d


def run(*, with_scipy=False, reference_solver=None):
    """Return replayable inputs, exact outputs and separately labeled comparisons."""
    scipy = linprog = None
    if with_scipy:
        import scipy
        from scipy.optimize import linprog
    reference = None
    if reference_solver:
        spec = importlib.util.spec_from_file_location('_poly_reference_solver', reference_solver)
        reference = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reference)
    cases = []
    durations = []
    for index, d in enumerate(corpus()):
        start = time.perf_counter()
        result = solve_full_table(d)
        elapsed_ms = (time.perf_counter() - start) * 1000
        durations.append(elapsed_ms)
        if result['status'] != 'optimal' or not verify_certificate(d, result)['optimal']:
            raise AssertionError(('uncertified', index, result))
        case = {'index': index, 'deltas': d, 'result': result, 'solver_ms': elapsed_ms}
        if linprog:
            n, m = len(d), len(d[0])
            a = [[-float(F(d[i][j])) for i in range(n)] + [1.] for j in range(m)]
            lp = linprog([0.] * n + [-1.], A_ub=a, b_ub=[0.] * m,
                         A_eq=[[1.] * n + [0.]], b_eq=[1.],
                         bounds=[(0., None)] * n + [(None, None)], method='highs')
            exact_value = float(F(result['value']))
            if not lp.success or abs(-lp.fun - exact_value) > 1e-8:
                raise AssertionError(('independent_lp_disagreement', index, lp.message))
            case['independent_lp_value'] = float(-lp.fun)
            case['independent_lp_absolute_error'] = abs(-lp.fun - exact_value)
        cases.append(case)
    restricted = []
    if reference:
        # New-core compatibility with the exact existing smaller-table interface.
        for case in cases:
            d = case['deltas'][:3]
            prior, full = reference.solve_table(d), solve_full_table(d)
            if F(prior['value']) != F(full['value']):
                raise AssertionError(('restricted_value_disagreement', case['index']))
            restricted.append({'index': case['index'], 'value': full['value'],
                               'table_sha256': full['table_sha256']})
    three = [[0, 0, 0], [5, -2, -2], [-2, 5, -2], [-2, -2, 5]]
    witnesses = {
        'three_support_algebraic': {'deltas': three, 'result': solve_full_table(three)},
        'published_strawberry_transcription': {
            'deltas': [[0,0],[1,-1],[-1,2]],
            'provenance': 'T15 README at 4d97474b0188b0373be1b52b610c0114ceb033c8; not an engine rerun',
            'result': solve_full_table([[0,0],[1,-1],[-1,2]])},
        'published_adverse_column_transcription': {
            'deltas': [[0,0,0],[1,-1,-1],[-1,2,-1]],
            'provenance': 'T15 README at 4d97474b0188b0373be1b52b610c0114ceb033c8; not an engine rerun',
            'result': solve_full_table([[0,0,0],[1,-1,-1],[-1,2,-1]])},
        'zero_pivot_budget': {'deltas': three, 'result': solve_full_table(three, max_pivots=0)},
    }
    ordered = sorted(durations)
    summary = {
        'schema': 1, 'python': platform.python_version(),
        'scope': 'algebraic solver execution and existing restricted-solver compatibility; no new engine or game runs',
        'source': {p: identity(Path(__file__).with_name(p)) for p in ['full_support.py', 'validate.py']},
        'synthetic_cases': len(cases), 'exact_certificates': len(cases),
        'independent_lp_cases': len(cases) if scipy else 0,
        'scipy_version': scipy.__version__ if scipy else None,
        'restricted_reference_cases': len(restricted),
        'reference_solver': identity(reference_solver) if reference_solver else None,
        'solver_ms': {'median': statistics.median(durations),
                      'p95': ordered[int(.95*(len(ordered)-1))], 'maximum': max(durations)},
        'maximum_pivots': max(c['result']['pivots'] for c in cases),
        'full_games': 0, 'engine_transitions': 0,
        'runtime_scope': 'in-process solver plus certificate only; excludes imports, receipt construction and whole-agent runtime',
    }
    return {'summary': summary, 'witnesses': witnesses, 'cases': cases,
            'restricted_comparisons': restricted}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-scipy', action='store_true', help='optional independent LP oracle, not runtime dependency')
    parser.add_argument('--reference-solver', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(with_scipy=args.with_scipy, reference_solver=args.reference_solver)
    # A new output avoids overwriting source or a prior retained validation run.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()

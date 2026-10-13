"""Reduce a complete analytic run to a compact, explicitly synthetic loss table."""
import argparse
import hashlib
import json
from pathlib import Path

ARMS = ('curvature_b8', 'v2_b8', 'v2_default_b16')


def summarize(report):
    if report['schema'] != 'learn2design-curvature-analytic/v1' or report['status'] != 'COMPLETE':
        raise ValueError('not a complete analytic run')
    if report['evidence_class'] != 'LOCAL_SYNTHETIC_FAKE_DFBENCH_REAL_JAX':
        raise ValueError('this reducer only accepts explicitly synthetic observations')
    if report['sources_before'] != report['sources_after']:
        raise ValueError('source drift')
    cells, traces = {}, []
    for e in report['entries']:
        key = (e['problem'], e['dimension'], e['seed'])
        row = cells.setdefault(key, {})
        if e['arm'] not in ARMS or e['arm'] in row or e['failure']:
            raise ValueError('duplicate, unknown or failed arm')
        if e['evals'] != report['config']['eval_budget']:
            raise ValueError('mismatched evaluation budget')
        row[e['arm']] = e['best_loss']
        traces.append([*key, e['arm'], e['parameter_trace_sha256'], e['loss_trace_sha256']])
    expected = {(p, d, s) for p in report['config']['problems']
                for d in report['config']['dimensions'] for s in report['config']['seeds']}
    if set(cells) != expected or any(set(row) != set(ARMS) for row in cells.values()):
        raise ValueError('incomplete matrix')
    return {
        'schema': 'learn2design-curvature-analytic-summary/v1',
        'evidence_class': report['evidence_class'], 'official_score_authority': False,
        'physics_execution_authority': False, 'source_integrity_is_not_execution_attestation': True,
        'representation': 'Paired final-loss rows and aggregate full-trace digest; not raw trajectories.',
        'config': report['config'], 'environment': report['environment'],
        'sources': report['sources_before'], 'harness': report['harness'],
        'baseline_constructor_adapter': report['baseline_constructor_adapter'],
        'columns': ['problem', 'dimension', 'seed', *ARMS],
        'rows': [[*key, *(cells[key][arm] for arm in ARMS)] for key in sorted(cells)],
        'wins': {arm: sum(row[ARMS[0]] < row[arm] for row in cells.values()) for arm in ARMS[1:]},
        'paired_cells': len(cells), 'runs': len(report['entries']),
        'trace_digest_sha256': hashlib.sha256(json.dumps(sorted(traces), separators=(',', ':')).encode()).hexdigest(),
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    result = summarize(json.loads(args.input.read_text()))
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')

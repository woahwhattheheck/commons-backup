# SPDX-License-Identifier: Apache-2.0
"""Project the retained development case without running any agent/game panel."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime import Portfolio, load
from continuation import evaluate_continuations, market_kernel, scenario_windows


def history_from_trace(path, source, now=360):
    flow = load(Path(__file__).resolve().parent / 'vendor/t12/flow.py', 't14_r2_flow_fixture')
    history = flow.FlowHistory()
    with gzip.open(path, 'rt') as f:
        rows = []
        for line in f:
            row = json.loads(line)
            rows.append(row)
            if row['step'] == now:
                break
    for previous, current in zip(rows, rows[1:]):
        obs = previous['observation']
        action = previous['actions'][obs['player']]
        _, private = source.post_units(obs, action, {})
        available = dict(private['shed']); fills = {}
        for order in action.get('market', []):
            if len(order) > 2 and order[0] == 'SELL' and order[1] in source.PRODUCTS:
                p = order[1]; q = min(order[2], available.get(p, 0))
                fills[p] = fills.get(p, 0)+q; available[p] = available.get(p, 0)-q
        for p in source.PRODUCTS:
            history.add(flow.infer_flow(obs, current['observation'], fills, p, {}, source.m, source.absorption))
    return history, rows[-1]['observation']


def inspect(path, output, budget=30):
    # Offline source extraction only; the controller is never advanced or called.
    instance = Portfolio({})
    source = instance.scheduler_module
    parent = source.parent
    routes = instance.policy.controller.R
    history, obs = history_from_trace(path, source)
    scenarios = scenario_windows(history, 360, 718, source.PRODUCTS)
    plans = {'retain': routes[parent.YARN], 'replace': routes[parent.YARN_CARROT]}
    plans['staged'] = routes[parent.YARN][:384]+routes[parent.YARN_CARROT][384:]
    report = evaluate_continuations(obs, {}, plans, scenarios, baseline='retain', mechanics=source.m,
                                   kernel=market_kernel(source.m), repair=parent._noop, budget_seconds=budget, keep_curve=True)
    report['scenarios'] = scenarios
    report['fixture'] = str(path)
    report['split'] = 'development'
    output.write_text(json.dumps(report, separators=(',', ':'))+'\n')
    print(json.dumps({k:report[k] for k in report if k not in ('evaluations', 'scenarios')}))


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--fixture', type=Path, default=ROOT/'results/active-regime/sell-arlene-9880203-seat0.jsonl.gz')
    p.add_argument('--output', type=Path, default=Path(__file__).resolve().parent/'results/development-projection.json')
    a = p.parse_args(); inspect(a.fixture, a.output)

# SPDX-License-Identifier: Apache-2.0
"""Compile adaptive continuations from retained DEVELOPMENT market regimes."""
import argparse
import gzip
import itertools
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from dependencies import receipt_source
from scan import retained_observations
from recourse import compile_policy


def run(limit=3):
    source = receipt_source()
    reached = list(retained_observations())
    regimes = []
    for row in reached:
        obs = row['observation']
        for item, q in obs['private']['shed'].items():
            if item in source.PRODUCTS and q > 1:
                regimes.append((item, q, obs['market']['inventory'][item], obs['step'],
                                obs['town']['unlocked_shops'], row, False))
    for item, q, inv, now in itertools.product(
            ('EGG', 'MILK', 'TOMATO', 'STRAWBERRY'), (2, 4, 8, 16),
            (9950, 9998, 10000, 10002, 10030, 10080), (241, 243)):
        shops = [s for s, goods in source.m.SHOPS.items() if item in goods][:2]
        regimes.append((item, q, inv, now, shops, None, True))
    found = []; tested = 0; start = time.monotonic()
    for item, q, inv, now, shops, provenance, constructed in regimes:
        end = min(now + 8, now // 24 * 24 + 23)
        branch = now + 1
        if branch >= end: continue
        streams = [('quiet', (), 'paired')]
        for r, date, align in itertools.product(sorted({1, q, min(100, 2*q)}),
                                               (now, branch, end), ('before', 'paired', 'after')):
            streams.append((f'{r}:{date}:{align}', ((date, r),), align))
        for date, align in itertools.product((branch, end), ('paired', 'after')):
            r = min(q, 50)
            streams.append((f'correlated:{r}:{date}:{align}', ((now,r),(date,r)), align))
        for prefix_q in sorted({0, q//2}):
            remainder = q - prefix_q
            prefix = [(now, prefix_q)] if prefix_q else []
            raw = [prefix + [(end, remainder)], prefix + [(branch, remainder)],
                   prefix + [(min(branch+2,end), remainder)]]
            if remainder > 1:
                raw.append(prefix + [(branch, remainder//2), (end, remainder-remainder//2)])
            model = source.MarketPath(item, inv, None, shops, {}, now, end)
            for base in range(len(raw)):
                ordered = [raw[base]] + [p for i,p in enumerate(raw) if i != base]
                plans = [{'id': f'p{i}', 'sales': p} for i, p in enumerate(ordered)]
                policy = compile_policy(model, plans, q, streams, branch, source.absorption)
                tested += 1
                if policy['active'] and policy['causal_deltas'] != policy['static_deltas']:
                    found.append({'item': item, 'quantity': q, 'inventory': inv,
                                  'now': now, 'end': end, 'shops': shops,
                                  'streams': streams, 'policy': policy,
                                  'constructed_regime': constructed, 'provenance': provenance})
                    if len(found) >= limit: break
            if len(found) >= limit: break
        if len(found) >= limit: break
    return {'tested': tested, 'seconds': time.monotonic()-start, 'findings': found}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); report = run()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_bytes(gzip.compress(json.dumps(report, indent=2).encode(), mtime=0))
    print(json.dumps({'tested': report['tested'], 'seconds': report['seconds'],
                      'findings': [{k: x[k] for k in ('item','quantity','inventory','now','constructed_regime')}
                                   | {'causal': x['policy']['causal_deltas'], 'static': x['policy']['static_deltas']}
                                   for x in report['findings']]}))

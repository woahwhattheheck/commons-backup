# SPDX-License-Identifier: Apache-2.0
"""Causal conditional-table scan using frozen market math, then engine checks.

Retained development observations seed the search. Explicit changes to lot,
inventory, dates and shops are labelled constructed legal regimes. No future
recorded opponent action or private inventory selects a runtime distribution.
"""
import argparse
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import time

from dependencies import HERE, receipt_source
from solver import solve_table


def retained_observations():
    path = HERE.parent/'cloud-model-lab/fixtures/envelope-binding-case-669.json'
    if path.exists():
        record = json.loads(path.read_text())
        yield {'source': str(path.relative_to(HERE.parents[2])),
               'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
               'seed': record['seed'], 'observation': record['observation']}
    directory = HERE.parent/'cloud-rule-arbitrage/engine_cases/results/development-recovered'
    for path in sorted(directory.glob('control-98320*.json.gz')):
        record = json.loads(gzip.decompress(path.read_bytes()))
        for event in record.get('cycle_signature_events', []):
            yield {'source': str(path.relative_to(HERE.parents[2])),
                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                   'seed': record['seed'], 'observation': event['own_observation']}


def find_tables(limit=6, full=False):
    source = receipt_source()
    retained = list(retained_observations())
    seen, contexts, pairs = set(), 0, 0
    found = []
    # Reachable observations first; additional legal demand/rounding regimes
    # expand only the named public inputs. No consumed held observations.
    regimes = []
    for row in retained:
        o = row['observation']
        for item, quantity in o['private']['shed'].items():
            if item in source.PRODUCTS and quantity >= 2:
                regimes.append((row, item, quantity, o['market']['inventory'][item],
                                o['step'], o['town']['unlocked_shops'], False))
    anchor = retained[0] if retained else None
    for item in ('STRAWBERRY', 'MILK', 'MELON', 'TOMATO', 'CARROT', 'EGG', 'WOOL'):
        relevant = [shop for shop, products in source.m.SHOPS.items() if item in products]
        for inv, quantity, now, shops in itertools.product(
                (9950, 9990, 9998, 10000, 10002, 10010, 10030, 10080),
                (2, 3, 4, 8, 16, 32), (241, 243, 259), ([], relevant[:1], relevant[:3])):
            regimes.append((anchor, item, quantity, inv, now, shops, True))
    started = time.monotonic()
    for provenance, item, quantity, inv, now, shops, constructed in regimes:
        key = (item, quantity, inv, now, tuple(shops))
        if key in seen:
            continue
        seen.add(key)
        end = min(now+8, (now//24+1)*24-1)
        if end <= now+1:
            continue
        dates = sorted({now, min(end, now+2), end})
        model = source.MarketPath(item, inv, None, shops, {}, now, end)
        plans = [((date, quantity),) for date in dates]
        plans += [((now, first), (end, quantity-first)) for first in (quantity//4, quantity//2, 3*quantity//4) if first]
        plans = sorted(set(plans))
        streams = [('quiet', (), 'paired')]
        for r, date, alignment in itertools.product((1, quantity, min(100, 2*quantity)), dates, ('paired','before','after')):
            streams.append((f'q{r}-t{date}-{alignment}', ((date, r),), alignment))
        receipts = [[model.score(plan, quantity, stream, alignment, True) for _, stream, alignment in streams] for plan in plans]
        contexts += 1
        for base in range(len(plans)):
            for a, b in itertools.combinations([i for i in range(len(plans)) if i != base], 2):
                da = [x[0]-y[0] for x,y in zip(receipts[a],receipts[base])]
                db = [x[0]-y[0] for x,y in zip(receipts[b],receipts[base])]
                if full:
                    if min(da) > 0 or min(db) > 0 or any(max(x,y)<=0 for x,y in zip(da,db)):
                        continue
                    pairs += 1
                    table = [[0]*len(streams),da,db]
                    answer = solve_table(table)
                    from fractions import Fraction
                    if Fraction(answer['value']) <= 0:
                        continue
                    frozen, info = source.optimize_lot(item=item,quantity=quantity,
                        inventory=inv,params=None,shops=shops,config={},now=now,
                        dates=dates,reference=plans[base],rival_quantity=quantity,
                        minimum_now=0,capacity_ok=lambda p:True,last=718)
                    if tuple(frozen) != plans[base]:
                        continue
                    found.append({'item':item,'quantity':quantity,'inventory':inv,
                        'now':now,'end':end,'shops':shops,'constructed_regime':constructed,
                        'provenance':provenance,'plans':[plans[i] for i in (base,a,b)],
                        'streams':streams,'table':table,'solution':answer,
                        'receipts':[[receipts[i][c] for c in range(len(streams))] for i in (base,a,b)],
                        'frozen_reference_confirmed': True})
                    if len(found)>=limit:
                        return {'full_stress':True,'contexts':contexts,'crossing_pairs':pairs,'seconds':time.monotonic()-started,'findings':found}
                    continue
                # Distinct complete streams with opposite pure-plan regrets.
                first = [j for j in range(len(streams)) if da[j]>0 and db[j]<0]
                second = [j for j in range(len(streams)) if da[j]<0 and db[j]>0]
                for j,k in itertools.product(first,second):
                    pairs += 1
                    if da[j]*db[k] <= da[k]*db[j]:
                        continue
                    table = [[0,0],[da[j],da[k]],[db[j],db[k]]]
                    answer = solve_table(table)
                    from fractions import Fraction
                    if Fraction(answer['value']) <= 0:
                        continue
                    found.append({'item':item,'quantity':quantity,'inventory':inv,
                        'now':now,'end':end,'shops':shops,'constructed_regime':constructed,
                        'provenance':provenance, 'plans':[plans[i] for i in (base,a,b)],
                        'streams':[streams[i] for i in (j,k)],'table':table,'solution':answer,
                        'receipts':[[receipts[i][c] for c in (j,k)] for i in (base,a,b)],
                        'expanded_streams':streams,'expanded_table':[[0]*len(streams),da,db]})
                    if len(found)>=limit:
                        return {'contexts':contexts,'crossing_pairs':pairs,'seconds':time.monotonic()-started,'findings':found}
                    break
                if len(found)>=limit:
                    break
    return {'full_stress':full,'contexts':contexts,'crossing_pairs':pairs,'seconds':time.monotonic()-started,'findings':found}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--limit',type=int,default=6)
    p.add_argument('--full',action='store_true')
    args=p.parse_args()
    report=find_tables(args.limit,args.full)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='findings'}))
    for row in report['findings']:
        print(json.dumps({k:row[k] for k in ('item','quantity','inventory','now','end','shops','constructed_regime','plans','streams','table','solution')}))

# SPDX-License-Identifier: Apache-2.0
"""Equal-result alternating timings on an explicitly constructed native workload."""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
from statistics import median
import time
from check_prefix_reuse import setup,blob
from test_prefix_reuse import Controller


def run(root, repetitions=5):
    c=setup(root)
    obs=deepcopy(c.obs);obs.update(step=22,day=0,hour=22)
    cfg=deepcopy(c.cfg)
    actor=Controller(switch=23)
    scenarios={f'conditional-{i}':c.oracle.Scenario(market_deltas={48:{'WOOL':i}},label=f'declared flow {i}') for i in range(8)}
    rows=[];reference=None
    for repeat in range(repetitions):
        for name in (('original','shared') if repeat%2==0 else ('shared','original')):
            module=c.original if name=='original' else c.current
            kw={} if name=='original' else {'reuse_scenario_prefixes':True}
            started=time.perf_counter()
            report=module.replay_routes(actor,('main','other'),obs,cfg,c.engine,c.oracle.simulate_bundle,
                scenarios=scenarios,end_step=70,limits=module.ReplayLimits(seconds=30,decisions=2000),**kw)
            elapsed=time.perf_counter()-started
            assert report['complete'],report
            if reference is None:reference=report['cases']
            equal=report['cases']==reference
            assert equal
            rows.append(dict(repetition=repeat,implementation=name,wall_seconds=elapsed,
                decisions_executed=report['decisions_executed'],same_all_case_fields=equal))
    assert actor.calls==0
    summary={name:median(r['wall_seconds'] for r in rows if r['implementation']==name) for name in ('original','shared')}
    return {'scope':'Constructed 22-70 clock over the retained board; 2 scripted routes x 8 explicit future flows. Native T04 mechanics; not game strength or full-agent latency.',
        'source_blob':blob(Path(__file__).with_name('physical_replay.py')),'reference_blob':blob(c.root/'TITAN-KESTREL-replay-deadline-PR10113/physical_replay.py'),
        'engine_sha256':c.engine_hashes,'median_wall_seconds':summary,
        'median_reduction_fraction':1-summary['shared']/summary['original'],'rows':rows}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rill-evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('Choose a fresh output file')
    result=run(a.rill_evidence)
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result['median_wall_seconds'],indent=2));print('median reduction',result['median_reduction_fraction'])

# SPDX-License-Identifier: Apache-2.0
"""Explicit development cash interventions; conditional projections, not games."""
from copy import deepcopy
import json
from pathlib import Path
from inspect_case import history_from_trace
from policy import EconomicPolicy
from continuation import evaluate_continuations, scenario_windows


def study():
    here = Path(__file__).resolve().parent
    policy = EconomicPolicy()
    source = policy.source
    fixture = here.parent/'results/active-regime/sell-arlene-9880203-seat0.jsonl.gz'
    history, observed = history_from_trace(fixture, source)
    scenarios = scenario_windows(history,360,718,source.PRODUCTS)
    plans = {'retain':policy.controller.R[policy.parent.YARN],
             'replace':policy.controller.R[policy.parent.YARN_CARROT],
             'staged':policy.controller.R[policy.staged]}
    rows = []
    for cash in (0,500,2000,5000,observed['farms'][observed['player']]['money']):
        obs = deepcopy(observed);obs['farms'][obs['player']]['money'] = cash
        receipt = evaluate_continuations(obs,{},plans,scenarios,baseline='retain',
            mechanics=source.m,kernel=policy.kernel,repair=policy.parent._noop,budget_seconds=30)
        rows.append({'intervened_own_cash':cash,'selected':receipt['selected'],'scores':receipt['scores'],
            'economics':{name:{sid:{k:r[k] for k in ('own_cash_change','rival_cash_change',
                'cash_trough','unfunded_orders','blocked_plant_turns','exit_state_sha256')}
                for sid,r in cases.items()} for name,cases in receipt['evaluations'].items()}})
    report = {'split':'development_parametric_intervention','source_fixture':str(fixture),
        'observation_time':360,'latest_history_time':359,'full_games':0,
        'intervention':'Change only visible own operating cash at the retained development checkpoint.',
        'interpretation':'Conditional mechanics sensitivity; no win labels, seed inference or runtime tuning.',
        'rows':rows}
    (here/'results/operating-cash-study.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps([{'cash':r['intervened_own_cash'],'selected':r['selected'],
                       'funding':{k:v['funding_supported'] for k,v in r['scores'].items()}} for r in rows]))


if __name__ == '__main__':
    study()

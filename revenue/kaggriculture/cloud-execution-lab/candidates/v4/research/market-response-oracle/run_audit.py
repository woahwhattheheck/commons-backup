# SPDX-License-Identifier: Apache-2.0
"""Run source-pinned finite-family audits offline. Never modifies a runtime."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time

from market_response import audit_plan, normalize_plan, select_robust_lot
from runtime_support import HERE, PINS, identity, load_scheduler, load_selected_core, load_engine, replay_plan


def run(root: Path, cases_path: Path, *, engine_check: bool, screen: bool, consumer: str = 'frozen') -> dict:
    scheduler, source = (load_selected_core(root) if consumer == 'frozen' else load_scheduler(root))
    source['consumer'] = consumer
    engine, Struct, engine_hashes = load_engine(root) if engine_check else (None, None, None)
    supplied = json.loads(cases_path.read_text())
    if supplied.get('schema') != 'titan-market-response-cases/v1':
        raise ValueError('Unrecognized cases schema')
    rows = []
    for case in supplied['cases']:
        options = dict(case['input'])
        options['reference'] = tuple(map(tuple, options['reference']))
        start = time.perf_counter()
        plan, info = scheduler.optimize_lot(**options)
        end = options['dates'][-1]
        model = scheduler.MarketPath(options['item'], options['inventory'], options['params'],
                                     options['shops'], options['config'], options['now'], end)
        audit = audit_plan(model, quantity=options['quantity'], reference=options['reference'],
                           candidate=plan, rival_budget=options['rival_quantity'],
                           absorb=lambda t: scheduler.absorption(options['item'], t, options['shops'], options['config']),
                           terminal=end == options.get('last', 718))
        row = {'id': case['id'], 'input': options, 'note': case.get('note'),
               'selected_plan': plan, 'named_scenarios': info,
               'oracle': audit.to_dict(), 'model_audit_seconds': time.perf_counter()-start}
        if screen:
            start = time.perf_counter()
            robust_plan, robust_info = select_robust_lot(scheduler, enabled=True, **options)
            row['screen'] = {'plan': robust_plan, 'info': robust_info,
                             'seconds': time.perf_counter()-start}
        if engine_check and audit.complete:
            pairs = []
            for seat in (0, 1):
                baseline = replay_plan(engine, Struct, options, options['reference'], audit.rival_stream, seat)
                chosen = replay_plan(engine, Struct, options, plan, audit.rival_stream, seat)
                delta = chosen['margin']-baseline['margin']
                if delta != audit.worst_delta:
                    raise ValueError(f"{case['id']}: official-engine/model mismatch in seat {seat}: {delta} vs {audit.worst_delta}")
                pairs.append({'seat': seat, 'delta_own_cash': chosen['own_cash']-baseline['own_cash'],
                              'delta_rival_cash': chosen['rival_cash']-baseline['rival_cash'],
                              'delta_margin': delta,
                              'same_final_market': chosen['market']==baseline['market'],
                              'same_final_privates': chosen['privates']==baseline['privates'],
                              'baseline': baseline, 'selected': chosen})
            row['official_engine_pairs'] = pairs
        rows.append(row)
    return {'schema': 'titan-market-response-evidence/v1',
            'generated_utc': datetime.now(timezone.utc).isoformat(),
            'publication_status': 'LOCAL_ONLY_NOT_POSTED_OR_MERGED',
            'runtime_root': str(root.resolve()), 'python': sys.version,
            'optimization_mode': sys.flags.optimize, 'source': source,
            'engine': engine_hashes, 'cases_source': identity(cases_path),
            'implementation': {p: identity(HERE/p) for p in ('market_response.py','runtime_support.py','run_audit.py')},
            'scope': 'Synthetic fixed-schedule counterfactuals, not traced policy activations or games',
            'limits': ['Finite budget of rival units, not a private-inventory inference',
                       'One aggregate rival market lot per callback; no buys or unit-phase production',
                       'No admission or capacity proof for intervening full-agent decisions',
                       'Carry is a continuation model; interpreter check explicitly realizes it next callback',
                       'No whole-game score, gauntlet-causality, default-change, or runtime-promotion claim'],
            'cases': rows}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, default=os.environ.get('TITAN_RUNTIME_ROOT'))
    parser.add_argument('--cases', type=Path, default=HERE/'CASES.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--engine-check', action='store_true')
    parser.add_argument('--screen', action='store_true')
    parser.add_argument('--consumer', choices=('frozen','standalone'), default='frozen')
    args=parser.parse_args()
    if args.runtime_root is None:
        parser.error('--runtime-root or TITAN_RUNTIME_ROOT is required')
    try:
        report=run(args.runtime_root, args.cases, engine_check=args.engine_check, screen=args.screen, consumer=args.consumer)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=args.output.parent,
                                         prefix=args.output.name+'.', delete=False) as f:
            tmp=Path(f.name)
            try:
                json.dump(report,f,indent=2,allow_nan=False)
                f.write('\n')
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
        try:
            tmp.replace(args.output)
        finally:
            tmp.unlink(missing_ok=True)
        print(f"{len(report['cases'])} source-pinned cases -> {args.output}")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'AUDIT FAILED: {exc}',file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())

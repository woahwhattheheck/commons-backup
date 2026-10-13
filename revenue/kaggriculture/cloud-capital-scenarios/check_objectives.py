# SPDX-License-Identifier: Apache-2.0
"""Read existing completed-replay evidence; select no live actor and run no game."""
from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from time import perf_counter

from dated_scenarios import DatedSelector


def identity(path):
    body = Path(path).read_bytes()
    return {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
            'git_blob': hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()}


def evaluate_saved(document, *, vary_scenario=None, probabilities=()):
    """Consume RILL's saved wrapper and explicitly named two-scenario sensitivity.

    Probabilities are user/caller assumptions. No frequencies, game scores or
    inferred buyer distribution are read. All original cases remain present.
    """
    replay = document['replay']
    row = document['validation']['input_row']
    observation, configuration = row['observation'], row['configuration']
    names = tuple(replay['scenarios'])
    incumbent = replay['original_route']
    ids = [incumbent] + list(dict.fromkeys(c['offered_route'] for c in replay['cases']
                                         if c['offered_route'] != incumbent))
    offers = [{'route_id': key} for key in ids]
    results = {}

    def select(label, objective, weights=None):
        selector = DatedSelector.from_completed_replay(
            replay, configuration, scenario_ids=names, objective=objective,
            scenario_weights=weights)
        selector(offers, observation)
        results[label] = deepcopy(selector.last_report)
        return results[label]

    original_digest = hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
    robust = select('robust', 'robust')
    if robust['reason'] == 'execution_report_invalid':
        raise ValueError('The existing physical-input reader did not accept this report')
    select('minimax_regret', 'minimax_regret')
    boundary = None
    if vary_scenario is not None:
        if len(names) != 2 or len(ids) != 2 or vary_scenario not in names:
            raise ValueError('The simple crossover requires two routes and two named scenarios')
        other = next(name for name in names if name != vary_scenario)
        case = {(c['offered_route'], c['scenario_id']): c for c in replay['cases']}
        delta = {name: Fraction(str(case[ids[1], name]['final_cash']))
                       - Fraction(str(case[ids[0], name]['final_cash'])) for name in names}
        slope = delta[vary_scenario] - delta[other]
        root = -delta[other] / slope if slope else None
        boundary = {'varied_scenario': vary_scenario, 'other_scenario': other,
                    'paired_cash_at_probability_zero': str(delta[other]),
                    'paired_cash_at_probability_one': str(delta[vary_scenario]),
                    'cash_difference_slope': str(slope),
                    'zero_gain_probability': str(root) if root is not None and 0 <= root <= 1 else None,
                    'probability_estimated': False, 'regimes_are_conditional_not_new_games': True}
        for value in probabilities:
            p = Fraction(value)
            if not 0 <= p <= 1:
                raise ValueError('Sensitivity probabilities must be in [0,1]')
            select('expected_cash_p_' + str(p), 'expected_cash', {vary_scenario:p, other:1-p})
    elif probabilities:
        raise ValueError('Name the scenario whose probability is being varied')
    assert hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest() == original_digest
    return {'schema':'titan.cash-objective-consumer.v1', 'input_unchanged': True,
            'scenario_ids': list(names), 'route_ids': ids, 'results': results,
            'sensitivity': boundary, 'retained_cases_consumed':len(replay['cases']),
            'retained_market_rows': sum(len(c['market_rows']) for c in replay['cases']),
            'new_games':0, 'simulator_calls':0, 'actor_calls':0,
            'selected_policy_changed':False, 'probabilities_calibrated':False,
            'rival_utility':None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--vary-scenario')
    parser.add_argument('--probabilities', default='')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.report.resolve():
        parser.error('Choose an output distinct from the retained input')
    try:
        data = json.loads(args.report.read_text(encoding='utf-8'))
        started = perf_counter()
        result = evaluate_saved(data, vary_scenario=args.vary_scenario,
                                probabilities=[p for p in args.probabilities.split(',') if p])
        result['read_validate_rank_seconds'] = perf_counter() - started
        result['input_report'] = identity(args.report)
        result['sources'] = {name: identity(Path(__file__).with_name(name))
                             for name in ('dated_scenarios.py','physical_outcomes.py','check_objectives.py')}
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        print(json.dumps({'selections':{key:value['selected'] for key,value in result['results'].items()},
                          'sensitivity':result['sensitivity'], 'new_games':0}, indent=2))
    except (OSError, KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()

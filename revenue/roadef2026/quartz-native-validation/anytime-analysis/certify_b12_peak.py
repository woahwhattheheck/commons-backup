#!/usr/bin/env python3
"""Exact first-departure ECMP bound for the retained B12 node-77 peak.

No routing optimizer, official checker, native binary, or external service is run.
The unchanged evidence reader supplies archive verification; all 27 allocation
rows use rational arithmetic. This proves a peak bound, not a full-vector optimum.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
from contextlib import ExitStack
from typing import Sequence

from analyze_b12_anytime import CONTEXT_SHA, EVIDENCE_SHA, require, sha, verify_archive

SOURCE_PINS = {
    'context/sources/checker/src/helpers.h':
        'ece20001ee779eaa0751db600fa5e3d305a7060e8dd2ca6fcc34fe51f6b8b17b',
    'context/sources/networktools/networktools/te/algorithms/ecmp.h':
        '77a9b11f8d05c38b39272c080266837cbbf2e2fc3a69005f6ab4e82b9c7e43e6',
    'context/sources/networktools/networktools/te/algorithms/segment_routing.h':
        '71497104553ce63680b63cc609d49ab84fc26f30e16830f191b47744881a6d48',
    'context/sources/checker/src/checker.h':
        '282d78595da31dc0c9d80994f18099008d65bd1bc527a3494ad7a4848f3b43e8',
}


def fraction_record(value: Fraction) -> dict:
    with localcontext() as context:
        context.prec = 50
        decimal = str(Decimal(value.numerator) / Decimal(value.denominator))
    return {'numerator': value.numerator, 'denominator': value.denominator,
            'decimal_approximation': decimal}


def minimum_two_link_peak(volumes: Sequence[Fraction], capacities: Sequence[Fraction]) -> dict:
    """Relax each demand's first departure to fractions 0, 1/2, or 1 on link 0.

    All permitted first-hop choices in a two-exit equal-next-hop ECMP graph are
    included. Some enumerated choices need not be attainable; including them
    can only weaken a lower bound. Later traversals add nonnegative load.
    """
    require(1 <= len(volumes) <= 8, 'Expected one to eight positive demand volumes')
    require(len(capacities) == 2 and all(c > 0 for c in capacities),
            'Expected exactly two positive capacities')
    require(all(v > 0 for v in volumes), 'Demand volumes must be positive')
    require(all(isinstance(v, Fraction) for v in (*volumes, *capacities)),
            'Use exact Fraction inputs, not binary floats')
    rows = []
    for twice in product((0, 1, 2), repeat=len(volumes)):
        flow0 = sum((v * a / 2 for v, a in zip(volumes, twice)), Fraction())
        flow1 = sum(volumes, Fraction()) - flow0
        loads = (flow0 / capacities[0], flow1 / capacities[1])
        rows.append({'twice_fraction_on_link0': list(twice),
                     'link0_first_departure_load': fraction_record(loads[0]),
                     'link1_first_departure_load': fraction_record(loads[1]),
                     'peak': fraction_record(max(loads))})
    def exact_peak(row):
        return Fraction(row['peak']['numerator'], row['peak']['denominator'])
    optimum = min(exact_peak(row) for row in rows)
    return {'case_count': len(rows), 'minimum_peak': fraction_record(optimum),
            'minimizers': [r for r in rows if exact_peak(r) == optimum], 'all_cases': rows}


def certify(evidence_path: Path, context_path: Path) -> dict:
    with ExitStack() as stack:
        evidence, evidence_integrity = verify_archive(evidence_path, EVIDENCE_SHA, 'MANIFEST.json')
        stack.enter_context(evidence)
        context, context_integrity = verify_archive(context_path, CONTEXT_SHA, 'TRANSFER-MANIFEST.json')
        stack.enter_context(context)
        for member, digest in SOURCE_PINS.items():
            require(sha(context.read(member)) == digest, f'Official source pin mismatch: {member}')
        raw = {name: evidence.read('inputs/setB-12-' + name + '.json') for name in ('net', 'tm', 'scenario')}
        network = json.loads(raw['net'], parse_float=Decimal)
        traffic = json.loads(raw['tm'], parse_float=Decimal)
        scenario = json.loads(raw['scenario'], parse_float=Decimal)
        require(network['directed'] is True and network['multigraph'] is False,
                'This certificate expects a simple directed graph')
        require(all(Decimal(e['metric']) > 0 and Decimal(e['capacity']) > 0 for e in network['links']),
                'Nonpositive metric or capacity')
        require(all(Decimal(v) >= 0 for demand in traffic['demands'] for v in demand['v']),
                'Negative input demand')
        source, slot = 77, 7
        removed = set()
        for item in scenario['interventions']:
            if item['t'] == slot:
                removed.update(item['links'])
        all_exits = [e for e in network['links'] if e['from'] == source]
        require(len(all_exits) == 2 and not any(e['id'] in removed for e in all_exits),
                'Boundary is not exactly two unaffected exit arcs')
        exits = sorted((e for e in all_exits),
                       key=lambda e: e['id'])
        require([(e['id'], e['to'], e['capacity']) for e in exits] == [(2945, 83, 101), (2946, 84, 114)],
                'The active two-exit boundary has changed')
        demands = [{'index': i, 'from': d['s'], 'to': d['t'], 'volume': str(d['v'][slot])}
                   for i, d in enumerate(traffic['demands'])
                   if d['s'] == source and d['t'] != source and d['v'][slot] > 0]
        require([d['index'] for d in demands] == [976, 4410, 14435], 'Demand boundary changed')
        values = [Fraction(Decimal(d['volume'])) for d in demands]
        capacities = [Fraction(e['capacity']) for e in exits]
        enumeration = minimum_two_link_peak(values, capacities)
        minimum = Fraction(enumeration['minimum_peak']['numerator'], enumeration['minimum_peak']['denominator'])
        require(minimum == Fraction(127207967, 202000000), 'Unexpected exact first-departure bound')
        checker_members = {places: f'full-budget/portfolio-independent-checker-{places}.json' for places in (6, 12)}
        checked = {places: json.loads(evidence.read(member), parse_float=Decimal)
                   for places, member in checker_members.items()}
        require(all(doc['valid'] is True for doc in checked.values()), 'Retained selected solution is not valid')
        keys = [{(r['t'], r['from'], r['to']) for r in checked[p]['saturations']} for p in (6, 12)]
        require(keys[0] == keys[1] and len(keys[0]) == 53448 and
                all(len(checked[p]['saturations']) == 53448 for p in (6, 12)), 'Checker coordinate set mismatch')
        peaks = {p: max(Decimal(r['sat']) for r in checked[p]['saturations']) for p in (6, 12)}
        require(peaks[6] == Decimal('0.629742'), 'Six-place witness peak changed')
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            exact_decimal = Decimal(minimum.numerator) / Decimal(minimum.denominator)
            discrepancy = abs(peaks[12] - exact_decimal)
        require(discrepancy <= Decimal('0.0000000000005'), 'Twelve-place witness does not meet the rational bound')
        micro_floor = (minimum.numerator * 1000000) // minimum.denominator
        require(Decimal(micro_floor) / 1000000 == peaks[6], 'Conservative six-place lower bound differs')
        boundary_loads = [next(r for r in checked[12]['saturations']
                              if r['t'] == slot and r['from'] == source and r['to'] == e['to'])
                          for e in exits]
        return {
            'schema': 'roadef.quill.b12-peak-certificate.v1',
            'instance': 'setB-12', 'source_node': source, 'time_slot': slot,
            'new_solver_runs': 0, 'new_official_checker_runs': 0,
            'integrity': {'evidence': evidence_integrity, 'context': context_integrity,
                          'official_source_sha256': SOURCE_PINS,
                          'input_sha256': {k: sha(v) for k, v in raw.items()}},
            'active_exit_links': exits, 'all_positive_source_demands': demands,
            'continuous_cut_relaxation': fraction_record(sum(values, Fraction()) / sum(capacities, Fraction())),
            'discrete_first_departure_bound': enumeration,
            'retained_feasible_witness': {
                'solution_sha256': sha(evidence.read('full-budget/portfolio-B12.json')),
                'checker_sha256': {str(p): sha(evidence.read(m)) for p, m in checker_members.items()},
                'reported_peak_6': str(peaks[6]), 'reported_peak_12': str(peaks[12]),
                'twelve_place_absolute_discrepancy_from_exact_bound': str(discrepancy),
                'exit_link_saturations_12': [{k: str(v) if isinstance(v, Decimal) else v for k, v in r.items()}
                                           for r in boundary_loads],
                'validation_source': 'Existing QUARTZ official-checker outputs, not a new validation run'},
            'proof': [
                'At time 7, node 77 has exactly two active outgoing arcs, capacities 101 and 114.',
                'The three positive demands originating at 77 must each leave the node to reach their distinct destinations.',
                'One SR path is associated with each demand. At the first nontrivial departure, equal-next-hop ECMP chooses one exit or both equally. Direct arc segments also lie in that set.',
                'Consequently each demand puts a fraction from {0, 1/2, 1} on the first exit; all 27 combinations are enumerated exactly.',
                'Positive metrics rule out a first-segment forwarding cycle. Any later revisits and any other traffic add nonnegative load and cannot weaken the first-departure bound.',
                'The minimum maximum exit utilization across this relaxed set is 127207967/202000000. Imposing reachability, eight-segment or transition-budget constraints cannot lower this bound.',
                'The retained feasible full solution reports the same peak to twelve decimal places and matches its conservative six-place bound: 0.629742.'
            ],
            'conclusion': 'The mathematical first-hop ECMP bound is attained by the retained result to checker reporting precision; B12 peak-only objective is optimal at the six-place comparison precision.',
            'limits': ['Not a full lexicographic-vector optimum; later ranks demonstrably improve.',
                       'Not an invariance certificate for every one of the top 32 coordinates or for another instance.',
                       'No new route, global solver replay, floating-point implementation audit, benchmark sample, or leaderboard result.',
                       'The bound relies on the supplied fixed topology, nonnegative traffic, and one-path-per-demand equal-next-hop ECMP semantics; it does not apply to arbitrary fractional traffic engineering.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = certify(args.evidence, args.context)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f'Certificate failed: {error}\n')
    print(json.dumps({'case_count': result['discrete_first_departure_bound']['case_count'],
                      'minimum_peak': result['discrete_first_departure_bound']['minimum_peak'],
                      'reported_peak_6': result['retained_feasible_witness']['reported_peak_6'],
                      'conclusion': result['conclusion']}, indent=2))


if __name__ == '__main__':
    main()

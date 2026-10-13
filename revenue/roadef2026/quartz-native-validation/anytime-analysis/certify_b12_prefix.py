#!/usr/bin/env python3
"""Compose disjoint first-departure ECMP bounds into a B12 leading-prefix proof.

Reads only the original archives. Reuses PR10315's exact allocation enumeration
and PR10273's archive verification; no solver or official checker is executed.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path
from typing import Sequence

from analyze_b12_anytime import CONTEXT_SHA, EVIDENCE_SHA, require, sha, verify_archive
from certify_b12_peak import SOURCE_PINS, minimum_two_link_peak

QUANTIZER_PINS = {
    'context/sources/networktools/networktools/core/json.h':
        'e85129d3b82c47f53d1ce9072130da0ecdf7df04b1a923a9f58c19a1d96a5763',
    'context/sources/networktools/networktools/@deps/rapidjson/writer.h':
        '40db14761c8f72d44261553400c24111b64bcc367bd23eeed4c45043ec80b39b',
    'context/sources/networktools/networktools/@deps/rapidjson/internal/dtoa.h':
        '73bdbedab68a0647156c918a7c879b7b0f13b88e2de2145c05fd7c65c8970cc5',
}


def truncate_micro(value: Fraction) -> int:
    require(isinstance(value, Fraction) and value >= 0, 'Expected nonnegative exact Fraction')
    return (value.numerator * 1000000) // value.denominator


def quantized_pair(values: Sequence[Fraction]) -> tuple[int, int]:
    require(len(values) == 2, 'Expected two loads')
    return tuple(sorted((truncate_micro(v) for v in values), reverse=True))


def minimum_quantized_pair(allocations: Sequence[Sequence[Fraction]]) -> tuple[int, int]:
    """Minimize after quantization; quantizing an exact lex minimum can be wrong."""
    require(len(allocations) > 0, 'Expected at least one allocation')
    return min(quantized_pair(values) for values in allocations)


def sorted_union(*vectors: Sequence[int]) -> tuple[int, ...]:
    return tuple(sorted((v for vector in vectors for v in vector), reverse=True))


def merge_disjoint_bounds(blocks: Sequence[dict], total_coordinates: int) -> tuple[int, ...]:
    seen = set()
    vectors = []
    for block in blocks:
        coords = [tuple(c) for c in block['coordinates']]
        values = tuple(block['minimum_quantized_pair'])
        require(len(coords) == len(values) == 2, 'Expected two distinct coordinates per block')
        require(len(set(coords)) == 2 and not any(c in seen for c in coords), 'Overlapping bound coordinates')
        require(all(type(v) is int and v >= 0 for v in values), 'Expected nonnegative integer micro-loads')
        require(values == tuple(sorted(values, reverse=True)), 'Bound pair must be descending')
        seen.update(coords)
        vectors.append(values)
    require(type(total_coordinates) is int and total_coordinates >= len(seen), 'Coordinate count is too small')
    return sorted_union(*vectors, (0,) * (total_coordinates - len(seen)))


def common_prefix(left: Sequence[int], right: Sequence[int]) -> int:
    require(len(left) == len(right), 'Vector dimensions differ')
    return next((i for i, (a, b) in enumerate(zip(left, right)) if a != b), len(left))


def certify(evidence_path: Path, context_path: Path) -> dict:
    with ExitStack() as stack:
        evidence, evidence_integrity = verify_archive(evidence_path, EVIDENCE_SHA, 'MANIFEST.json')
        stack.enter_context(evidence)
        context, context_integrity = verify_archive(context_path, CONTEXT_SHA, 'TRANSFER-MANIFEST.json')
        stack.enter_context(context)
        source_pins = {**SOURCE_PINS, **QUANTIZER_PINS}
        for member, digest in source_pins.items():
            require(sha(context.read(member)) == digest, f'Official source pin mismatch: {member}')
        raw = {name: evidence.read(f'inputs/setB-12-{name}.json') for name in ('net', 'tm', 'scenario')}
        network, traffic, scenario = (json.loads(raw[n], parse_float=Decimal) for n in ('net', 'tm', 'scenario'))
        require(network['directed'] is True and network['multigraph'] is False, 'Expected simple directed network')
        require(all(e['metric'] > 0 and e['capacity'] > 0 for e in network['links']), 'Nonpositive metric/capacity')
        require(all(len(d['v']) == 12 and all(v >= 0 for v in d['v']) for d in traffic['demands']), 'Unexpected traffic domain')
        checker_member = 'full-budget/portfolio-independent-checker-6.json'
        checked = json.loads(evidence.read(checker_member), parse_float=Decimal)
        require(checked['valid'] is True, 'Retained witness is not checker-valid')
        coordinates = {(r['t'], r['from'], r['to']) for r in checked['saturations']}
        require(len(coordinates) == len(checked['saturations']) == 53448, 'Missing or duplicate checker coordinates')
        actual_map = {}
        for row in checked['saturations']:
            value = Fraction(row['sat'])
            require(value >= 0 and (value * 1000000).denominator == 1, 'Unexpected checker precision')
            actual_map[(row['t'], row['from'], row['to'])] = int(value * 1000000)
        blocks = []
        for node in (77, 969):
            exits = sorted((e for e in network['links'] if e['from'] == node), key=lambda e: e['id'])
            require(len(exits) == 2, 'Certificate expects exactly two source exits')
            origin = [(i, d) for i, d in enumerate(traffic['demands']) if d['s'] == node and d['t'] != node]
            for t in range(12):
                demands = [{'index': i, 'target': d['t'], 'volume': str(d['v'][t])} for i, d in origin if d['v'][t] > 0]
                require(1 <= len(demands) <= 8, 'Unexpected positive-demand count')
                cases = minimum_two_link_peak([Fraction(d['volume']) for d in demands], [Fraction(e['capacity']) for e in exits])
                loads = [tuple(Fraction(r[k]['numerator'], r[k]['denominator']) for k in
                               ('link0_first_departure_load', 'link1_first_departure_load')) for r in cases['all_cases']]
                best = minimum_quantized_pair(loads)
                choices = []
                for row, values in zip(cases['all_cases'], loads):
                    pair = quantized_pair(values)
                    choices.append({'twice_fraction_on_link0': row['twice_fraction_on_link0'],
                                    'exact_loads': [{'numerator': v.numerator, 'denominator': v.denominator} for v in values],
                                    'quantized_sorted_pair': list(pair), 'minimizer': pair == best})
                coords = [(t, node, e['to']) for e in exits]
                require(all(c in coordinates for c in coords), 'Bound coordinates missing from checker')
                observed = sorted_union([actual_map[c] for c in coords])
                require(observed >= best, 'Retained block violates the mathematical lower bound')
                interventions = {arc for item in scenario['interventions'] if item['t'] == t for arc in item['links']}
                blocks.append({'source_node': node, 'time_slot': t, 'coordinates': [list(c) for c in coords],
                               'exit_links': exits, 'positive_origin_demands': demands,
                               'intervened_exit_ids': [e['id'] for e in exits if e['id'] in interventions],
                               'minimum_quantized_pair': list(best), 'observed_quantized_pair': list(observed),
                               'allocation_count': len(choices), 'all_allocations': choices})
        bound = merge_disjoint_bounds(blocks, len(coordinates))
        actual = sorted_union(tuple(actual_map.values()))
        require(actual >= bound, 'Retained full vector violates the composed lower bound')
        prefix = common_prefix(bound, actual)
        require(len(blocks) == 24 and sum(b['allocation_count'] for b in blocks) == 630, 'Unexpected allocation census')
        require(prefix == 23 and bound[prefix] == 351129 and actual[prefix] == 373232, 'Unexpected prefix result')
        return {
            'schema': 'roadef.quill.b12-prefix-certificate.v1', 'instance': 'setB-12',
            'precision': {'places': 6, 'operation': 'floor nonnegative exact load to integer micro-units before lex minimization'},
            'new_solver_runs': 0, 'new_official_checker_runs': 0,
            'integrity': {'evidence': evidence_integrity, 'context': context_integrity, 'official_source_sha256': source_pins,
                          'input_sha256': {k: sha(v) for k, v in raw.items()}, 'checker_sha256': sha(evidence.read(checker_member)),
                          'solution_sha256': sha(evidence.read('full-budget/portfolio-B12.json'))},
            'block_count': len(blocks), 'allocation_count': sum(b['allocation_count'] for b in blocks),
            'coordinate_count': len(coordinates), 'supported_coordinate_count': 48,
            'lower_bound_sorted_micro_loads_nonpadding': list(bound[:48]), 'zero_padding_count': len(bound) - 48,
            'certified_prefix_length': prefix, 'certified_prefix_micro_loads': list(bound[:prefix]),
            'first_unresolved_rank': prefix + 1, 'first_unresolved_bound_micro_load': bound[prefix],
            'first_unresolved_observed_micro_load': actual[prefix],
            'observed_prefix_with_first_gap': list(actual[:prefix + 1]), 'blocks': blocks,
            'proof': [
                'Each positive source demand has first-departure exit shares from {0,1/2,1}; the original ECMP proof applies to each of the 24 two-exit source/time groups.',
                'Each group enumerates every such allocation and minimizes its descending pair after six-place truncation, not before.',
                'Actual loads include these first departures plus nonnegative additional traffic. Their sorted truncated pair is lexicographically no smaller than its local minimum.',
                'If sorted A is lexicographically no smaller than sorted B, merging the same multiset C preserves that order: the highest value with differing multiplicity is unchanged.',
                'The 24 coordinate sets are disjoint. Applying the merge-order lemma one block at a time and filling all unaccounted coordinates with zero gives a full-vector lexicographic lower bound.',
                'The retained feasible vector matches that lower bound for 23 coordinates. A strictly better vector must preserve those 23 sorted values; the certificate leaves rank 24 and later unresolved.'
            ],
            'limits': ['This is a prefix bound in the mathematical ECMP model at six-place reporting precision, not a full-vector optimum or complete native floating-point audit.',
                       'Sorted values are certified, not unconditional invariance of named arcs; worse solutions can change the prefix.',
                       'The first gap is not evidence that the bound at rank 24 is jointly attainable.',
                       'Do not freeze or skip all top 32 coordinates, omit feasibility checks, or treat a rank-band policy as tested by this proof.',
                       'This fixed-instance analysis reuses existing official-checker records and does not add a benchmark sample or contest submission.']}


def main() -> None:
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
    print(json.dumps({k: result[k] for k in ('block_count', 'allocation_count', 'coordinate_count',
        'certified_prefix_length', 'certified_prefix_micro_loads', 'first_unresolved_rank',
        'first_unresolved_bound_micro_load', 'first_unresolved_observed_micro_load')}, indent=2))


if __name__ == '__main__':
    main()

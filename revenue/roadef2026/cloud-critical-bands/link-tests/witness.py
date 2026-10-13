#!/usr/bin/env python3
"""Construct a connected bidirected rank barrier; no external inputs or network."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def write_fixture(out: Path, high: int = 33, *, slots: int = 1,
                  max_segments: int = 2, budget: int = 4,
                  noncontiguous: bool = False, maintenance: bool = False) -> tuple[Path, Path, Path]:
    if high < 1 or slots < 1:
        raise ValueError('high and slots must be positive')
    out.mkdir(parents=True, exist_ok=True)
    dest, middle = high + 1, high + 2
    node_id = lambda i: i * 7 + 100 if noncontiguous else i
    nodes = [{'id': node_id(i), 'name': f'n{i}'} for i in range(high + 3)]
    edges = []
    def pair(a, b, metric, capacity):
        for x, y in [(a, b), (b, a)]:
            edges.append({'id': len(edges), 'from': node_id(x), 'to': node_id(y),
                          'metric': metric, 'capacity': capacity})
    for leaf in range(1, high + 1):
        pair(leaf, 0, 1, 1)
    pair(0, dest, 1, 10)
    pair(0, middle, 2, 100)
    pair(middle, dest, 2, 100)
    demands = [{'s': node_id(i), 't': node_id(0), 'v': [10] * slots}
               for i in range(1, high + 1)]
    demands.append({'s': node_id(0), 't': node_id(dest), 'v': [50] * slots})
    interventions = []
    if maintenance:
        if slots < 2:
            raise ValueError('Maintenance fixture requires at least two slots')
        # Slot zero has no intervention. At slot one the bypass is offline.
        # Its return arc is deliberately narrow: a constant detour would
        # overload it after the maintenance change, requiring a budgeted switch.
        edges[-3]['capacity'] = 1
        interventions = [{'t': 1, 'links': [len(edges)-2, len(edges)-1]}]
    documents = {
        'network.json': {'directed': True, 'multigraph': False, 'nodes': nodes, 'links': edges},
        'traffic.json': {'num_time_slots': slots, 'demands': demands},
        'scenario.json': {'max_segments': max_segments, 'interventions': interventions,
                          'budget': [{'t': t, 'value': budget} for t in range(1, slots)]},
    }
    for name, data in documents.items():
        (out / name).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    return tuple(out / name for name in documents)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--high', type=int, default=33)
    args = parser.parse_args()
    write_fixture(args.output, args.high)

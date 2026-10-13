# SPDX-License-Identifier: Apache-2.0
"""Recheck captured natural CF1 inputs; not a second game driver or policy.

Consumes the immutable support corpus in the existing CF1 package. No engine,
parent runtime, network, action reconstruction, or gameplay writes are used.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import importlib.util
import json
import lzma
from pathlib import Path

HERE = Path(__file__).resolve().parent


def require(value, message):
    if not value:
        raise ValueError(message)


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def read_corpus(path, expected_compressed, expected_raw):
    # Four binary fragments keep the evidence publishable through bounded
    # connector payloads. Their concatenation is the original, hash-pinned XZ.
    compressed = (path.read_bytes() if path.is_file() else b''.join(
        path.with_name(path.name + '.part%02d' % i).read_bytes()
        for i in range(1, 5)))
    require(hashlib.sha256(compressed).hexdigest() == expected_compressed, 'compressed corpus mismatch')
    raw = lzma.decompress(compressed)
    require(hashlib.sha256(raw).hexdigest() == expected_raw, 'raw corpus mismatch')
    return [json.loads(line) for line in raw.splitlines()]


def authenticate_helper(path, expected):
    require(git_blob(path.read_bytes()) == expected, 'helper source mismatch')
    spec = importlib.util.spec_from_file_location('_cf1_support_subject', path)
    require(spec is not None and spec.loader is not None, 'cannot import helper')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def review(rows, helper, cells, configuration):
    """Preserve every raw action row, including surplus/missing actor commands."""
    expected = {tuple(cell) for cell in cells}
    require(len(expected) == len(cells) and bool(expected), 'invalid panel cells')
    coverage = defaultdict(set)
    totals = Counter()
    for source in rows:
        row = copy.deepcopy(source)
        key = (row['opponent'], row['seed'], row['seat'])
        step = row['step']
        require(key in expected, 'unexpected panel cell')
        require(type(step) is int and step in range(23, 696, 24), 'invalid boundary step')
        require(step not in coverage[key], 'duplicate boundary')
        coverage[key].add(step)
        obs, action = row['observation'], row['action']
        require(obs['step'] == step and obs['player'] == row['seat'], 'observation identity mismatch')
        farm = obs['farms'][row['seat']]
        positions = [farm['farmer'], *farm['hands']]
        commands = [action.get('farmer'), *action.get('hands', [])]
        inventories = obs['private']['inventories']
        totals['boundaries'] += 1
        totals['complete_actor_vectors'] += int(len(positions) == len(commands) == len(inventories))
        for actor, (x, y) in enumerate(positions):
            tile = farm['tiles'][y][x]
            command = commands[actor] if actor < len(commands) else None
            if isinstance(tile, dict) and tile.get('animal') == 'COW':
                totals['actor_on_cow_visits'] += 1
                totals['cow_harvest_commands'] += int(command == ['HARVEST'])
                totals['empty_cow_harvest_commands'] += int(
                    command == ['HARVEST'] and type(tile.get('yield_units')) is int and tile['yield_units'] == 0)
                totals['ready_empty_cow_already_collecting'] += int(
                    command == ['COLLECT_FERTILIZER'] and helper._ready_cow(tile, step // 24))
        for completed in (False, True):
            for enabled in (False, True):
                before = encoded([action, obs, configuration])
                proposal = helper.apply_cow_fert_salvage(
                    action, obs, configuration, enabled=enabled, completed_service=completed)
                require(encoded([action, obs, configuration]) == before, 'helper mutated a captured input')
                totals['input_nonmutation_checks'] += 1
                if not enabled:
                    require(proposal is action, 'OFF identity failure')
                    totals['off_identity_checks'] += 1
                else:
                    totals['on_shadow_checks'] += 1
                    totals['proposals_completed_service' if completed else 'proposals_harvest_only'] += int(proposal is not action)
    for key in expected:
        require(coverage[key] == set(range(23, 696, 24)), 'incomplete boundary coverage: ' + str(key))
    totals['cells'] = len(expected)
    return dict(sorted(totals.items()))


def recheck(receipt_path, corpus_path, helper_path):
    receipt = json.loads(receipt_path.read_text())
    rows = read_corpus(corpus_path, receipt['corpus']['sha256'], receipt['corpus']['raw_sha256'])
    helper = authenticate_helper(helper_path, receipt['recheck']['helper_blob'])
    cells = [(r['opponent'], r['seed'], r['seat']) for r in receipt['cells']]
    totals = review(rows, helper, cells, receipt['recheck']['configuration_fields'])
    require(totals == receipt['recheck']['expected_totals'], 'census differs from recorded receipt')
    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, default=HERE / 'NATURAL-HARVEST-SUPPORT.json')
    parser.add_argument('--corpus', type=Path, default=HERE / 'natural-harvest-support.jsonl.xz')
    parser.add_argument('--helper', type=Path, default=HERE / 'r04_cow_fert_salvage.py')
    args = parser.parse_args()
    try:
        print(json.dumps(recheck(args.receipt, args.corpus, args.helper), indent=2, sort_keys=True))
    except (ValueError, OSError, lzma.LZMAError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    main()

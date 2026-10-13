#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Audit AUTHORED native tape mechanics with the sole existing miner.

No agent or engine is executed. Raw unit rows (including surplus hands),
empty rows and all market slots are preserved as intent. This is not a
leaderboard cohort, hosted replay, current full-V4 run, or filled-action log.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import math
import tarfile
import zlib
from collections import Counter, defaultdict
from pathlib import Path

import mine_top_mechanics as miner
from sequence_contract import collect_witnesses, sequence_windows, witness_record

ARCHIVE_SHA256 = 'b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9'
SOURCE_SHA256 = 'e87d70dd3bcf5aea1e929f1a5dbdc86f3cc33d8a0b3492986f2970fc8e774be2'
VENDOR_PATH = 'reference/next-panel/vendor/arlene.py'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def authenticated_routes(archive: Path) -> tuple[dict, dict]:
    if sha(archive.read_bytes()) != ARCHIVE_SHA256:
        raise ValueError('archive hash mismatch; obtain a separately reviewed pin for newer bytes')
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        if len({m.name for m in members}) != len(members) or not all(m.isfile() for m in members):
            raise ValueError('duplicate or non-regular archive member')
        data = {m.name: tar.extractfile(m).read() for m in members}
    if sha(data['SOURCE.json']) != SOURCE_SHA256:
        raise ValueError('SOURCE.json identity mismatch')
    manifest = json.loads(data['SOURCE.json'])
    expected = manifest['runtime']
    if set(data) != set(expected) | {'SOURCE.json'}:
        raise ValueError('archive member set mismatch')
    for name, receipt in expected.items():
        if len(data[name]) != receipt['bytes'] or sha(data[name]) != receipt['sha256']:
            raise ValueError('runtime member mismatch: ' + name)
    tree = ast.parse(data[VENDOR_PATH].decode('utf-8'))
    blobs = [n.value for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == '_BLOB' for t in n.targets)]
    if len(blobs) != 1:
        raise ValueError('expected exactly one literal authored route blob')
    raw = zlib.decompress(base64.b64decode(ast.literal_eval(blobs[0]), validate=True))
    payload = json.loads(raw)
    routes = {payload['main']: payload['full']}
    for tail in payload['tails']:
        if tail['h'] in routes or tail['parent'] not in routes:
            raise ValueError('invalid route ancestry')
        routes[tail['h']] = routes[tail['parent']][:tail['at']] + tail['suffix']
    if len(routes) != 4 or any(len(tape) != 720 for tape in routes.values()):
        raise ValueError('unexpected pinned route cardinality')
    return routes, {'archive_sha256': ARCHIVE_SHA256, 'source_sha256': SOURCE_SHA256,
                    'verified_runtime_members': len(expected), 'vendor_path': VENDOR_PATH,
                    'vendor_sha256': sha(data[VENDOR_PATH]), 'route_payload_sha256': sha(raw)}


def events_from_tape(route: str, tape: list[dict]) -> list[miner.Event]:
    events = []
    for step, action in enumerate(tape):
        if not isinstance(action, dict):
            raise ValueError(f'{route}:{step}: action is not a dictionary')
        units = [action.get('farmer', []), *action.get('hands', [])]
        for source, rows in [('unit', units), ('market', action.get('market', []))]:
            for index, raw in enumerate(rows):
                if not isinstance(raw, list) or (raw and not isinstance(raw[0], str)):
                    raise ValueError(f'{route}:{step}:{source}:{index}: malformed raw row')
                target = str(raw[1]).upper() if len(raw) > 1 else ''
                qty = raw[2] if len(raw) > 2 else None
                qty = float(qty) if type(qty) in (int, float) and math.isfinite(qty) else None
                events.append(miner.Event(route, 'TITAN_AUTHORED', 'template', step, source,
                    raw[0].upper() if raw else 'EMPTY', target, qty, len(events),
                    actor=str(index) if source == 'unit' else None,
                    slot=index if source == 'market' else None))
    return events


def legacy_windows(events):
    """The exact donor ordering algorithm, isolated only for comparison."""
    streams = defaultdict(list)
    for e in sorted(events, key=lambda e: (e.step, e.source, e.player, e.ordinal)):
        streams[(e.source, e.player)].append(e)
    for rows in streams.values():
        for n in (2, 3):
            for i in range(len(rows) - n + 1):
                witness = tuple(rows[i:i+n])
                yield 'seq' + str(n) + '|' + '>'.join(map(miner.token, witness)), witness


def audit(archive: Path) -> dict:
    routes, pins = authenticated_routes(archive)
    results = []
    for route, tape in sorted(routes.items()):
        events = events_from_tape(route, tape)
        features = miner.features_by_team(events)[0]['TITAN_AUTHORED']
        legacy = list(legacy_windows(events))
        current = list(sequence_windows(events, miner.token))
        legacy_keys = {f for f, _ in legacy}
        current_keys = {f for f, _ in current}
        ungrounded = [(f, rows) for f, rows in legacy if rows[0].source == 'unit'
                      and any(a.step == b.step for a, b in zip(rows, rows[1:]))]
        distinct = []
        used = set()
        for f, rows in ungrounded:
            if f not in used and all(r.verb not in ('PASS', 'EMPTY') for r in rows):
                distinct.append({'feature': f, 'witness': [witness_record(e) for e in rows],
                                 'absent_from_repaired_player_sequences': f not in current_keys})
                used.add(f)
            if len(distinct) == 3:
                break
        # No leaderboard ranking: one policy, four conditional authored routes.
        counts = Counter((e.source, e.verb, e.target) for e in events)
        results.append({'route': route, 'callbacks_authored': len(tape),
            'raw_action_sha256': sha(json.dumps(tape, sort_keys=True, separators=(',', ':')).encode()),
            'raw_event_count': len(events), 'unit_rows': sum(e.source == 'unit' for e in events),
            'market_rows': sum(e.source == 'market' for e in events),
            'feature_count': len(features), 'legacy_sequence_occurrences': len(legacy),
            'legacy_simultaneous_unit_occurrences': len(ungrounded),
            'legacy_unique_sequence_features': len(legacy_keys),
            'repaired_player_sequence_features': sum(f.startswith('seq') for f in current_keys),
            'explicit_actor_sequence_features': sum(f.startswith('actor_seq') for f in current_keys),
            'old_features_absent_from_repaired_player_sequences': len(legacy_keys-current_keys),
            'first_three_simultaneous_unit_witnesses': distinct,
            'authored_plant_requests': {target: n for (source, verb, target), n in sorted(counts.items())
                                        if source == 'unit' and verb == 'PLANT'},
            'authored_buy_animal_requests': {target: n for (source, verb, target), n in sorted(counts.items())
                                            if source == 'market' and verb == 'BUY_ANIMAL'},
            'actor_motif_examples': {f: rows for f, rows in collect_witnesses(events, miner.token,
                                                        limit_per_feature=1).items()
                                     if f.startswith('actor_seq2|unit:PICKUP:')
                                     and ('>unit:FERTILIZE' in f or '>unit:FEED' in f)},
            'all_features_sha256': sha(json.dumps(sorted(features)).encode())})
    return {'schema': 'titan-v4-native-mechanics-order-audit/v1', 'pins': pins,
            'scope': 'AUTHORED_INTENT_ONLY; no native agent/engine invocation, field cohort, fills, or strength claim',
            'top_team_corpus': 'NOT_AVAILABLE; no top-5 leaderboard inference or enrichment ranking',
            'routes': results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.archive)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

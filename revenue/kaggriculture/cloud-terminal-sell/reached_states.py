# SPDX-License-Identifier: MIT
"""Read retained T05 x SELL games into isolated, observation-only case inputs.

No policy import, simulator, network, seed execution, or inferred missing frame.
The private source archive remains separate from the public code repository.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import lzma
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable

ARCHIVE_SHA256 = 'a85fdedc100b54d9e853c0db43c6609fece99e93497a49d01df91fdcc12948f4'
MAX_DECODED_BYTES = 64 * 1024 * 1024
OBSERVATION_FIELDS = ('farms', 'market', 'town', 'day', 'hour', 'player',
                      'private', 'step', 'remainingOverageTime')
CONFIGURATION_FIELDS = ('episodeSteps', 'actTimeout', 'boardSize', 'startingMoney',
    'maxMarketOrdersPerTurn', 'turnsPerDay', 'shedCapacity', 'weedSpawnChance',
    'townShopUnlockInterval', 'townShopSellInterval', 'townCenterSellInterval',
    'farmHandCostMult', 'marketParams')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       allow_nan=False) + '\n').encode('utf-8')


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate JSON key: {key}')
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f'Nonfinite JSON constant: {value}')


def decode(data: str | bytes):
    return json.loads(data, object_pairs_hook=_object, parse_constant=_constant)


def _phase(name: str) -> str:
    path = PurePosixPath(name)
    if (len(path.parts) != 2 or path.parts[0] not in ('dev', 'held')
            or name != str(path) or '\\' in name
            or not re.fullmatch(r'[a-zA-Z0-9_-]+\.json', path.name)):
        raise ValueError(f'Unexpected evidence member name: {name}')
    return path.parts[0]


def read_archive(path: Path, *, expected_sha256: str = ARCHIVE_SHA256,
                 max_decoded_bytes: int = MAX_DECODED_BYTES) -> dict[str, str]:
    """Read the lossless filename-to-original-text archive; no extraction writes."""
    if max_decoded_bytes < 1:
        raise ValueError('Decoded size limit must be positive')
    if digest(path.read_bytes()) != expected_sha256:
        raise ValueError('Archive SHA256 does not match the supplied source pin')
    with lzma.open(path, 'rb') as stream:
        raw = stream.read(max_decoded_bytes + 1)
    if len(raw) > max_decoded_bytes:
        raise ValueError('Decoded archive exceeds the size limit')
    records = decode(raw)
    if not isinstance(records, dict) or not records:
        raise ValueError('Archive must be a nonempty filename-to-text mapping')
    for name, text in records.items():
        _phase(name)
        if not isinstance(text, str):
            raise ValueError(f'Archive member must retain original JSON text: {name}')
    return records


def actor_input(frame: dict, seat: int) -> dict:
    """Return only public observation + this seat's private observation/config.

    Recorded co-actions, final outcomes, evaluator seeds and file paths never
    enter this result. A raw stored seat without shared step must be normalized
    by its own framework consumer, not guessed here from a final score or seed.
    """
    observation, configuration = frame['observation'], frame['configuration']
    if observation.get('player') != seat or seat not in (0, 1):
        raise ValueError('Frame observation is not bound to the recorded candidate seat')
    step = frame['step']
    if type(step) is not int or observation.get('step') != step:
        raise ValueError('Frame lacks a matching delivered observation step')
    turns = configuration.get('turnsPerDay', 24)
    if type(turns) is not int or turns <= 0:
        raise ValueError('turnsPerDay must be a positive integer')
    if observation.get('day') != step // turns or observation.get('hour') != step % turns:
        raise ValueError('Observation clock differs from the recorded step')
    for key in ('farms', 'market', 'town', 'private'):
        if key not in observation:
            raise ValueError(f'Missing delivered observation field: {key}')
    if len(observation['farms']) != 2:
        raise ValueError('Expected two visible farms')
    return copy.deepcopy({
        'observation': {k: observation[k] for k in OBSERVATION_FIELDS if k in observation},
        'configuration': {k: configuration[k] for k in CONFIGURATION_FIELDS if k in configuration},
    })


def pressure(inputs: dict) -> dict:
    """Separate ready-to-deposit pressure from goods still traveling on workers."""
    obs, cfg = inputs['observation'], inputs['configuration']
    farm, private = obs['farms'][obs['player']], obs['private']
    positions = [farm['farmer'], *farm['hands']]
    inventories = private['inventories']
    if len(positions) != len(inventories):
        raise ValueError('Worker and private inventory counts differ')
    size = len(farm['tiles'])
    half = size // 2
    access = {(half-1, half-1), (half, half-1), (half-1, half), (half, half)}
    capacity = int(cfg.get('shedCapacity', 100))
    shed = sum(private['shed'].values())
    carried = [sum(inv.values()) for inv in inventories]
    ready = [i for i, pos in enumerate(positions) if tuple(pos) in access and carried[i] > 0]
    ready_units = sum(carried[i] for i in ready)
    room = max(0, capacity - shed)
    return {'shed_capacity': capacity, 'shed_units': shed, 'shed_room': room,
            'carried_units': sum(carried), 'ready_workers': ready,
            'ready_units': ready_units, 'ready_excess': max(0, ready_units-room),
            'total_inventory_excess': max(0, shed+sum(carried)-capacity)}


def collect(records: dict[str, str], *, phase: str = 'dev',
            arms: Iterable[str] | None = None, step: int | None = None,
            only_pressure: bool = False) -> tuple[list[dict], list[dict]]:
    """Collect input-deduplicated cases and separate evaluator-side references.

    Development is the default. Held is an explicitly requested consumed bank,
    never promoted to fresh validation. Missing requested frames raise an error.
    Deduplication uses exact policy input, not final outcomes or seed identity;
    repeated cases remain represented by references in the separate catalog.
    """
    if phase not in ('dev', 'held'):
        raise ValueError('Choose dev or explicitly consumed held; no implicit mixed split')
    chosen = None if arms is None else set(arms)
    if chosen is not None and not chosen:
        raise ValueError('An empty arm selection has no cases')
    cases: dict[str, dict] = {}
    reports = []
    eligible = 0
    for name, text in sorted(records.items()):
        if _phase(name) != phase:
            continue
        record = decode(text)
        if chosen is not None and record['arm'] not in chosen:
            continue
        eligible += 1
        if record.get('status') != 'complete' or record.get('failure') is not None:
            raise ValueError(f'Incomplete game is not a completed source case: {name}')
        seat = record['candidate_seat']
        snapshots = record.get('final_day', [])
        if not isinstance(snapshots, list) or not snapshots:
            raise ValueError(f'Complete record has no retained frames: {name}')
        previous = -1
        matched = step is None
        for frame in snapshots:
            inputs = actor_input(frame, seat)
            current = frame['step']
            if current <= previous:
                raise ValueError(f'Frame order is not strictly increasing: {name}')
            previous = current
            if step is not None and current != step:
                continue
            matched = True
            metrics = pressure(inputs)
            if only_pressure and metrics['ready_excess'] == 0:
                continue
            key = digest(encoded(inputs))
            case_id = f'{phase}-{key}'
            case = cases.setdefault(case_id, {'case_id': case_id,
                'input_sha256': key, 'inputs': inputs, 'pressure': metrics, 'references': []})
            # Metadata is kept OUT of each inputs/*.json actor payload.
            case['references'].append({'record': name, 'record_sha256': digest(text.encode()),
                'arm': record['arm'], 'seed': record['seed'], 'seat': seat, 'step': current,
                'opponent': record['opponent']})
        if not matched:
            raise ValueError(f'Requested step {step} absent from {name}; no reconstructed frame')
        reports.append({'record': name, 'record_sha256': digest(text.encode()),
            'phase': phase, 'arm': record['arm'], 'seed': record['seed'], 'seat': seat,
            'opponent': record['opponent'], 'scores': record['scores'],
            'trace_sha256': record.get('trace_sha256'),
            'pre698_sha256': record.get('pre698_sha256')})
    if not eligible:
        raise ValueError('No records match the requested phase and arms')
    if chosen is not None and chosen != {r['arm'] for r in reports}:
        raise ValueError('At least one selected arm is absent from the source records')
    ordered = sorted(cases.values(), key=lambda c: (-c['pressure']['ready_excess'],
        c['pressure']['shed_room'], c['input_sha256']))
    return ordered, reports


def export(records: dict[str, str], destination: Path, **selection) -> dict:
    """Write isolated inputs plus a metadata-only index and evaluator sidecar."""
    cases, reports = collect(records, **selection)
    destination.mkdir(parents=True, exist_ok=False)
    inputs_dir = destination / 'inputs'
    inputs_dir.mkdir()
    index = []
    for case in cases:
        relative = 'inputs/' + case['case_id'] + '.json'
        (destination / relative).write_bytes(encoded(case['inputs']))
        index.append({k: v for k, v in case.items() if k != 'inputs'} | {'input_file': relative})
    catalog = {'schema_version': 1, 'phase': selection.get('phase', 'dev'),
        'split_status': 'previously consumed development' if selection.get('phase', 'dev') == 'dev'
                        else 'previously consumed held; not fresh validation',
        'source_records': len(reports), 'frame_references': sum(len(c['references']) for c in cases),
        'distinct_inputs': len(cases), 'cases': index,
        'case_count_is_not_independent_seed_count': True}
    (destination / 'index.json').write_bytes(encoded(catalog))
    (destination / 'evaluation-only.json').write_bytes(encoded(reports))
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--phase', choices=('dev', 'held'), default='dev')
    parser.add_argument('--arm', action='append', dest='arms')
    parser.add_argument('--step', type=int)
    parser.add_argument('--only-pressure', action='store_true')
    parser.add_argument('--archive-sha256', default=ARCHIVE_SHA256)
    args = parser.parse_args()
    try:
        records = read_archive(args.archive, expected_sha256=args.archive_sha256)
        catalog = export(records, args.destination, phase=args.phase, arms=args.arms,
                         step=args.step, only_pressure=args.only_pressure)
    except (ValueError, KeyError, TypeError, OSError, lzma.LZMAError) as exc:
        parser.exit(2, f'Case intake: {exc}\n')
    print(json.dumps({k: catalog[k] for k in ('phase', 'source_records', 'frame_references', 'distinct_inputs')}))


if __name__ == '__main__':
    main()

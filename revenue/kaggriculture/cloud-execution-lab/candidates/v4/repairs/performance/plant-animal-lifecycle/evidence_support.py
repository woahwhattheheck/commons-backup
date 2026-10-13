# SPDX-License-Identifier: Apache-2.0
"""Offline authenticated fixtures shared by the lifecycle component gates."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
import random
import types
from pathlib import Path

from repair_lifecycle import repair_source

MECHANICS_SHA = '579965e589237d1e5bbcc8b8448188f91b173d4480430d34b3a7f0e07e0c48d3'
PINS = {
    'checks/reference/evaluator/loader.py': 'cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e',
    'checks/reference/engine/kaggriculture.py': 'bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e',
    'checks/reference/engine/kaggriculture.json': 'a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867',
    'checks/reference/engine/utils.py': '537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b',
}
NAMES = ('_decay_plants', '_daily_refresh_plants', '_daily_refresh_animals')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    if digest(data) != expected:
        raise ValueError(f'input hash mismatch: {path}')
    return data


def module(source: str, name: str):
    result = types.ModuleType(name)
    exec(compile(source, name, 'exec'), result.__dict__)
    return result


def load_inputs(runtime: Path):
    source = checked(runtime/'mechanics.py', MECHANICS_SHA).decode('utf-8')
    for name, expected in PINS.items():
        checked(runtime/name, expected)
    path = runtime/'checks/reference/evaluator/loader.py'
    spec = importlib.util.spec_from_file_location('phenology_engine_loader', path)
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    engine, _ = loader.get_engine(runtime/'checks/reference/engine')
    return source, module(source, 'native_control'), module(repair_source(source), 'native_candidate'), loader, engine


def initial(loader, engine, seed=9600913):
    cfg = loader.Struct({k: v.get('default') if isinstance(v, dict) else v
                         for k, v in engine.specification['configuration'].items()})
    cfg.seed = seed
    env = loader.Struct(configuration=cfg, done=False, info={})
    state = [loader.Struct(observation=loader.Struct(), action={}, status='ACTIVE', reward=0) for _ in range(2)]
    engine.interpreter(state, env)
    return state, env


def world(m, seed: int, size=10, density=0.75):
    """Construct physiological boundary coverage, not a field prevalence sample."""
    rng = random.Random(seed)
    tiles = []
    for y in range(size):
        row = []
        for x in range(size):
            if rng.random() > density:
                row.append(rng.choice([None, 'LOCKED', {'kind': 'WEED'}, {'kind': 'PASTURE'}]))
            elif rng.randrange(2):
                crop = rng.choice(list(m.CROPS))
                tile = m._new_plant(crop, rng.randrange(-3, 20), 24)
                tile.update(watered_today=bool(rng.randrange(2)), consecutive_unwatered=rng.randrange(3),
                            yield_units=rng.randrange(9), max_lifespan_step=rng.choice([-1, 0, 23, 24, 48, 96, 200, 718]),
                            fertilized_until_day=rng.randrange(-1, 33))
                row.append(tile)
            else:
                tile = m._new_animal(rng.choice(list(m.ANIMALS)), rng.randrange(-3, 20))
                tile.update(fed_today=bool(rng.randrange(2)), cared_today=bool(rng.randrange(2)),
                            consecutive_unfed=rng.randrange(3), yield_units=rng.randrange(8),
                            pending_care_bonus=rng.randrange(4))
                row.append(tile)
        tiles.append(row)
    return {'tiles': tiles, 'untouched': {'sentinel': [seed, 'keep']}}


def signature(value):
    """Ordered data plus identity graph: distinguish copies, row/tile aliases."""
    seen = {}
    def visit(item):
        if isinstance(item, (dict, list, tuple)):
            ident = id(item)
            if ident in seen:
                return ('REF', seen[ident])
            seen[ident] = len(seen)
            if isinstance(item, dict):
                return ('DICT', tuple((key, visit(val)) for key, val in item.items()))
            return (type(item).__name__, tuple(visit(val) for val in item))
        return item
    return visit(value)


def invoke(function, farm, args):
    try:
        result = function(farm, *args)
        outcome = ('return', result)
    except (IndexError, KeyError, TypeError) as error:
        outcome = (type(error).__name__, str(error))
    return outcome, signature(farm)

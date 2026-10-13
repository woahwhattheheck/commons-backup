# SPDX-License-Identifier: Apache-2.0
"""Offline, source-bound one-game D4 native entrypoint/official-engine receipt."""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify(root):
    pins = json.loads((HERE/'NATIVE-INPUTS.json').read_text())
    source = json.loads((root/'SOURCE.json').read_text())
    if digest((root/'SOURCE.json').read_bytes()) != pins['source_manifest_sha256']:
        raise ValueError('Wrong native source manifest')
    identities = {}
    for name, info in source['runtime'].items():
        b = (root/name).read_bytes()
        h = digest(b)
        permitted = {info['sha256'], pins['candidate_files'].get(name)}
        if name == 'TITAN-CONFIG.json':
            cfg = json.loads(b)
            original = json.loads(pins['original_config'])
            for k in ('r04_d4_strawberry_timing', 'r04_d4_strawberry_min_price'):
                cfg.pop(k, None)
            if cfg != original:
                raise ValueError('Unrelated native config drift')
        elif h not in permitted:
            raise ValueError(f'Native source mismatch: {name}')
        identities[name] = h
    candidate = digest((root/'frozen_selected.py').read_bytes()) == pins['candidate_files']['frozen_selected.py']
    runtime_changed = digest((root/'titan_runtime.py').read_bytes()) == pins['candidate_files']['titan_runtime.py']
    if candidate != runtime_changed:
        raise ValueError('Mixed candidate runtime/consumer')
    if candidate:
        h = digest((root/'native_d4.py').read_bytes())
        if h != pins['candidate_files']['native_d4.py']:
            raise ValueError('Wrong D4 helper')
        identities['native_d4.py'] = h
    cfg = json.loads((root/'TITAN-CONFIG.json').read_text())
    if cfg.get('r04_d4_strawberry_timing',False) and not candidate:
        raise ValueError('D4 enabled without native wiring')
    return identities, cfg


def play(root, seed, seat, opponent, snapshots=None):
    root = Path(root).resolve()
    identities, feature_cfg = verify(root)
    sys.path.insert(0, str(root))
    ev = load('_bloom_evaluate', root/'checks/reference/evaluator/evaluate.py')
    engine, hashes = ev.get_engine(root/'checks/reference/engine', root/'checks/reference/evaluator/loader.py')
    main = load('_bloom_main', root/'main.py')
    frozen = __import__('frozen_selected')
    probe = load('_bloom_probe', HERE/'native_d4.py')
    recorded = {}
    original = frozen.FrozenSelected.transform
    def capture(self, obs, cfg, base):
        # Capture references only; all diagnostic computation is outside the
        # native entrypoint's deadline. Transform does not mutate this base.
        recorded.update(consumer=self, obs=obs, cfg=cfg, base=base)
        return original(self, obs, cfg, base)
    frozen.FrozenSelected.transform = capture
    cfg = ev.Struct({k:v.get('default') if isinstance(v,dict) else v
                     for k,v in engine.specification['configuration'].items()})
    cfg.seed = seed
    env = ev.Struct(configuration=cfg, done=False, info={})
    states = [ev.Struct(observation=ev.Struct(), action={}, status='ACTIVE', reward=0)
              for _ in range(2)]
    engine.interpreter(states, env)
    if opponent == 'starter':
        rival = lambda obs: engine.starter_agent(obs)
    elif opponent == 'route':
        rival_agent = frozen.parent.Agent()
        rival = rival_agent.act
    else:
        raise ValueError('Unknown opponent')
    action_hash, state_hash = hashlib.sha256(), hashlib.sha256()
    counts, census = Counter(), Counter()
    frames, changes, times = [], [], []
    natural = []
    for step in range(cfg.episodeSteps):
        for i, s in enumerate(states):
            s.observation.step = step
            observation = copy.deepcopy(s.observation)
            before = time.perf_counter()
            if i == seat:
                action = main.agent(observation, cfg)
                elapsed = time.perf_counter()-before
                times.append(elapsed)
                if not isinstance(action,dict) or not isinstance(action.get('market',[]),list):
                    raise ValueError('Malformed native output')
                instance = main._INSTANCE
                status = (instance.diagnostics.get('status') if instance else 'no_instance')
                counts[status] += 1
                selected = recorded.get('consumer')
                if recorded.get('obs',{}).get('step') == step:
                    horizon = selected.diagnostics.get('horizon')
                    if horizon:
                        farm, private = frozen.post_units(recorded['obs'], recorded['base'], cfg)
                        item_end = max(horizon['baseline_end'], horizon['service_dates'].get('STRAWBERRY',horizon['baseline_end']),horizon['unit_event'] or horizon['baseline_end'])
                        common = dict(enabled=True,now=step,last=cfg.episodeSteps-2,
                            route=selected.controller.R[selected.controller.cur],
                            action=recorded['base'],stock=private['shed'].get('STRAWBERRY',0),
                            price=observation['market']['prices'].get('STRAWBERRY'),
                            item_end=item_end,hard_end=horizon['hard_end'],
                            max_orders=cfg.maxMarketOrdersPerTurn,turns_per_day=cfg.turnsPerDay)
                        for threshold in (2,180):
                            result = probe.sale_horizon(**common,min_price=threshold)
                            if 12*24<=step<19*24:
                                census[f'{threshold}:{result["reason"]}'] += 1
                            if result['due'] is not None:
                                natural.append(dict(step=step, threshold=threshold,
                                    stock=common['stock'], price=common['price'], result=result,
                                    chosen=selected.diagnostics.get('chosen')))
                        d4=selected.diagnostics.get('d4')
                        if d4 and d4['due'] is not None:
                            counts['d4_extension'] += 1
                        if snapshots is not None and 12*24<=step<19*24 and common['stock']>0:
                            frames.append(dict(step=step,observation=recorded['obs'],base=recorded['base'],
                                route_id=selected.controller.cur,horizon=horizon,
                                planned=copy.deepcopy(selected.planned),diagnostics=copy.deepcopy(selected.diagnostics),
                                returned=action))
                action_hash.update(json.dumps(action,sort_keys=True,separators=(',',':')).encode()+b'\n')
            else:
                action = rival(observation)
            s.action=action
        engine.interpreter(states,env)
        state_hash.update(json.dumps(states,sort_keys=True,separators=(',',':')).encode()+b'\n')
        if any(s.status=='DONE' for s in states):
            env.done=True
            break
    if snapshots is not None:
        Path(snapshots).write_text(json.dumps(frames,sort_keys=True,separators=(',',':'))+'\n')
    bank=[s.reward for s in states]
    return dict(seed=seed,seat=seat,opponent=opponent,steps=step+1,bank=bank,
        margin=bank[seat]-bank[1-seat],status=[s.status for s in states],
        entrypoint_counts=dict(counts),census=dict(census),natural_opportunities=natural,
        action_sha256=action_hash.hexdigest(),state_sha256=state_hash.hexdigest(),
        max_call_seconds=max(times),elapsed_call_seconds=sum(times),engine_sha256=hashes,
        feature_config=feature_cfg,source_files=identities)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True,type=Path);p.add_argument('--seed',type=int,default=17)
    p.add_argument('--seat',type=int,choices=(0,1),default=0)
    p.add_argument('--opponent',choices=('starter','route'),default='starter')
    p.add_argument('--output',required=True,type=Path);p.add_argument('--snapshots',type=Path)
    a=p.parse_args();result=play(a.root,a.seed,a.seat,a.opponent,a.snapshots)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_files','engine_sha256','natural_opportunities','feature_config')},sort_keys=True))

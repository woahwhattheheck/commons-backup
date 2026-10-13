# SPDX-License-Identifier: Apache-2.0
"""Source-pinned PRICE-PATH native pilot, not production activation.

Arms: off (unmodified native), funded (forced strawberry->tomato proposal,
for engagement/schedule stress), projected (same funded proposal only on a large
conditional known-shop price premium); supply-aware additionally models the
parent's authored future SELL supply and tests four tomato units minus seed cost
against eight strawberry units. These yields are scenario assumptions, NOT a
certificate for arbitrary service routes. No historical projector is reconstructed.
Each process runs exactly one full official-engine game. The adapter transforms
unit intent BEFORE checkpoint/projection, adds only market purchases at the
native final market boundary, and observes the actual returned action READ-ONLY.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time
from types import MethodType

from harness import authenticate, engine, initial, advance, load, blob
from seed_budget import SeedBudget


def conditional_prices(m, obs, cfg, end_step, route=None):
    """Conditional prices, NOT a guarantee that future authored SELLs fill.

    Hold currently unlocked shops fixed. Optional route supply is this agent's
    executable raw SELL prefix, with exact per-unit $1-floor inventory behavior.
    No future new shops, private rival state, or evaluation seed enters this model.
    """
    start = obs['step']
    inventory = {crop: obs['market']['inventory'][crop]
                 for crop in ('STRAWBERRY', 'TOMATO')}
    params = obs['market'].get('params')
    shop_interval = max(1, int(cfg.get('townShopSellInterval', 4)))
    center_interval = max(1, int(cfg.get('townCenterSellInterval', 24)))
    cap = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))
    shop_drain = Counter()
    for shop in obs['town']['unlocked_shops']:
        products = m.SHOPS[shop]
        for product in products:
            if product in inventory:
                shop_drain[product] += 2 if len(products) == 1 else 1
    for step in range(start, end_step):
        if route is not None and step < len(route):
            for order in route[step].get('market', [])[:cap]:
                if len(order) != 3 or order[0] != 'SELL' or order[1] not in inventory:
                    continue
                crop = order[1]
                for _ in range(max(0, int(order[2]))):
                    if m.market_price(crop, inventory[crop], params) <= 1:
                        break  # further $1 sales produce cash, not supply
                    inventory[crop] += 1
        if step % shop_interval == 0:
            for crop, quantity in shop_drain.items():
                inventory[crop] -= quantity
        if step % center_interval == 0:
            for crop in inventory:
                inventory[crop] -= 1
    return {crop: m.market_price(crop, inventory[crop], params) for crop in inventory}


def install(instance, arm, events, counters, m):
    admission = SeedBudget()
    instance.price_seed_admission = admission
    original_init = instance._initialize
    original_final = instance._early_capital_selected

    def initialize(self):
        original_init()
        admission.reset()  # reconstruction never inherits a tentative intent
        original_production = self.production

        class Producer:
            def act(_, obs):
                parent = original_production.act(obs)
                result, report = admission.apply(parent, obs, configuration[0],
                    episode='native-pilot-episode', route=str(self.controller.cur))
                counters['apply:' + report['status']] += 1
                if report['status'] != 'no-ticket':
                    events.append({'step': obs['step'], 'stage': 'apply', **report})
                return result
        self.production = Producer()

    def final(self, obs, cfg, selected):
        returned = original_final(obs, cfg, selected)
        if self.diagnostics.get('status') != 'completed':
            admission.reset()
            counters['fallback'] += 1
            return returned
        step = obs['step']
        route = self.controller.R[self.controller.cur]
        if step + 1 >= len(route):
            return returned
        future = route[step + 1]
        count = sum(row == ['PLANT', 'STRAWBERRY'] for row in
                    [future.get('farmer', []), *future.get('hands', [])])
        if not count:
            return returned
        counters['raw-next-strawberry-opportunities'] += 1
        # Existing strawberry service is merely a testable continuation, not a
        # tomato yield certificate. Leave at least twelve days for this pilot.
        tpd = int(cfg.get('turnsPerDay', 24))
        if (step // tpd + 12) * tpd > int(cfg.get('episodeSteps', 720)) - 2:
            counters['insufficient-horizon'] += 1
            return returned
        forecast = conditional_prices(m, obs, cfg, (step // tpd + 10) * tpd,
                                      route if arm == 'supply-aware' else None)
        if arm == 'projected' and forecast['TOMATO'] < 3 * forecast['STRAWBERRY']:
            counters['conditional-premium-not-met'] += 1
            return returned
        if arm == 'supply-aware' and 4 * forecast['TOMATO'] - 50 <= 8 * forecast['STRAWBERRY']:
            counters['supply-aware-value-not-met'] += 1
            return returned
        result, report = admission.prepare(returned, obs, cfg, future,
            episode='native-pilot-episode', route=str(self.controller.cur),
            source='STRAWBERRY', target='TOMATO', budget=500, reserve=250,
            max_plants=2, enabled=True)
        counters['prepare:' + report['status']] += 1
        events.append({'step': step, 'stage': 'prepare', 'forecast': forecast, **report})
        return result

    instance._initialize = MethodType(initialize, instance)
    instance._early_capital_selected = MethodType(final, instance)


configuration = [None]


def run(root, arm, seed, seat, audit=True):
    root = authenticate(root)
    sys.path.insert(0, str(root))
    official, Struct = engine(root)
    main = load(root / 'main.py', 'priceseed_native_main')
    m = load(root / 'mechanics.py', 'priceseed_native_mechanics')
    counters, status = Counter(), Counter()
    events, transitions = [], []
    source_factory = main._new_instance
    if arm != 'off':
        def factory(r, features):
            obj = source_factory(r, features)
            install(obj, arm, events, counters, m)
            return obj
        main._new_instance = factory
    state, env = initial(official, Struct, seed)
    configuration[0] = dict(env.configuration)
    economic = Counter()
    if audit:
        commit_unit = official._commit_unit
        apply_unit = official._apply_unit_action
        def commit(op, item, price, farm, private, market, shed_capacity=100):
            answer = commit_unit(op, item, price, farm, private, market, shed_capacity)
            if answer and farm is state[0].observation.farms[seat] and item in ('TOMATO', 'STRAWBERRY'):
                economic[op + ':' + item + ':units'] += 1
                economic[op + ':' + item + ':cash'] += price
            return answer
        def unit(farm, private, idx, action, board_size, day, turns_per_day, shed_capacity=100):
            watch = farm is state[0].observation.farms[seat] and action and action[0] == 'HARVEST'
            before = {crop: sum(inv.get(crop, 0) for inv in private['inventories'])
                      for crop in ('TOMATO', 'STRAWBERRY')} if watch else {}
            answer = apply_unit(farm, private, idx, action, board_size, day, turns_per_day, shed_capacity)
            for crop in before:
                economic['HARVEST:' + crop + ':units'] += (
                    sum(inv.get(crop, 0) for inv in private['inventories']) - before[crop])
            return answer
        official._commit_unit = commit
        official._apply_unit_action = unit
    action_hash = hashlib.sha256()
    state_hash = hashlib.sha256()
    durations = []
    start = time.perf_counter()
    for step in range(env.configuration.episodeSteps):
        observations = []
        for i in range(2):
            state[i].observation.step = step
            observations.append(deepcopy(state[i].observation))
        tick = time.perf_counter()
        selected = main.agent(observations[seat], env.configuration)
        durations.append(time.perf_counter() - tick)
        instance = main._INSTANCE
        status[getattr(instance, 'diagnostics', {}).get('status', 'no-instance')] += 1
        if arm != 'off' and instance is not None:
            # Receipt binding only. No action modification after native return.
            bound = instance.price_seed_admission.record_returned(selected, observations[seat],
                env.configuration, episode='native-pilot-episode', route=str(instance.controller.cur))
            if bound:
                counters['returned-purchases'] += 1
        rival = official.starter_agent(observations[1 - seat])
        actions = [selected, rival] if seat == 0 else [rival, selected]
        action_hash.update(json.dumps(actions, sort_keys=True).encode() + b'\n')
        before = deepcopy(observations[seat]['farms'][seat])
        advance(official, state, env, actions, step)
        own = state[seat].observation
        for y, row in enumerate(own['farms'][seat]['tiles']):
            for x, tile in enumerate(row):
                old = before['tiles'][y][x]
                if (isinstance(tile, dict) and tile.get('kind') == 'PLANT'
                        and (not isinstance(old, dict) or old.get('kind') != 'PLANT'
                             or tile.get('planted_day') != old.get('planted_day'))):
                    counters['filled-plant:' + tile['crop']] += 1
                    if tile['crop'] == 'TOMATO':
                        transitions.append({'step': step, 'position': [x, y], 'tile': deepcopy(tile)})
        state_hash.update(json.dumps([dict(s) for s in state], sort_keys=True).encode() + b'\n')
        if any(s.status == 'DONE' for s in state):
            break
    return {'arm': arm, 'seed': seed, 'seat': seat, 'steps': step + 1,
            'source_blobs': {name: blob((Path(__file__).parent / name).read_bytes())
                             for name in ('seed_budget.py', 'harness.py', 'native_pilot.py')},
            'scores': [s.reward for s in state], 'status': dict(status),
            'counters': dict(counters), 'economics': dict(economic), 'events': events, 'observed_tomato_plants': transitions,
            'actions_sha256': action_hash.hexdigest(), 'full_state_sha256': state_hash.hexdigest(),
            'final_seeds': dict(state[seat].observation.private['seeds']), 'audit': audit,
            'seconds': time.perf_counter() - start, 'max_call_seconds': max(durations),
            'call_seconds': durations, 'input_scope': '110-member checked b567 archive (109 runtime entries plus SOURCE.json), not moving main',
            'limits': ['Official starter only; not ladder strength.',
                       'Known-shop premium is conditional; not guaranteed future cash.',
                       'Forced funded arm measures schedule/engagement, not a promotion policy.',
                       'No production/default/archive/config/Kaggle mutation.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--arm', choices=('off', 'funded', 'projected', 'supply-aware'), required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--seat', type=int, choices=(0, 1), required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--no-audit', action='store_true')
    args = parser.parse_args()
    report = run(args.root, args.arm, args.seed, args.seat, not args.no_audit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in
                     ('events', 'observed_tomato_plants', 'call_seconds')}), flush=True)

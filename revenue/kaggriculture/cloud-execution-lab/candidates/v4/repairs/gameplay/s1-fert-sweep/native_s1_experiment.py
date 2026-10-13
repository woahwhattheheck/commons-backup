# SPDX-License-Identifier: Apache-2.0
"""S1 fertilizer-sweep admission and actor custody for offline native experiments.

Semantic port of PR12630 / canonical donor f14e18e67b5c0b95943f3c9b9db649d3327d5eb4.
Not the legacy router and not a production entrypoint. Quoted value is a heuristic,
not a profit certificate. The experiment adapter deliberately lives outside the
native instance so its ownership survives the native instance's reconstruction.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Callable

KEY = 'r04_s1_fert_sweep'
STANDARD = dict(episodeSteps=720, turnsPerDay=24, boardSize=10,
                shedCapacity=100, maxMarketOrdersPerTurn=10, farmHandCostMult=1)
STARTS = ((4, 4), (5, 4), (4, 5), (5, 5))


def plain_int(x, minimum=0):
    return type(x) is int and x >= minimum


def standard(configuration):
    if not isinstance(configuration, dict):
        return False
    return (all(type(configuration.get(k)) is int and configuration[k] == v
                for k, v in STANDARD.items())
            and configuration.get('marketParams') in (None, {}))


def farm_of(obs):
    """Validate own public/private shape without accessing rival private state."""
    if not isinstance(obs, dict) or not plain_int(obs.get('step')):
        return None
    player = obs.get('player')
    if type(player) is not int or player not in (0, 1):
        return None
    farms, private, market = obs.get('farms'), obs.get('private'), obs.get('market')
    if not isinstance(farms, list) or len(farms) != 2:
        return None
    farm = farms[player]
    if not all(isinstance(v, dict) for v in (farm, private, market)):
        return None
    hands, tiles = farm.get('hands'), farm.get('tiles')
    inventories, shed = private.get('inventories'), private.get('shed')
    if (not isinstance(hands, list) or not isinstance(tiles, list) or len(tiles) != 10
            or any(not isinstance(row, list) or len(row) != 10 for row in tiles)
            or not isinstance(inventories, list) or len(inventories) != len(hands) + 1
            or not isinstance(shed, dict) or not isinstance(market.get('prices'), dict)):
        return None
    for pos in [farm.get('farmer'), *hands]:
        if (not isinstance(pos, list) or len(pos) != 2
                or any(not plain_int(x) or x >= 10 for x in pos)):
            return None
    for inv in [shed, *inventories]:
        if not isinstance(inv, dict) or any(not plain_int(q) for q in inv.values()):
            return None
    return farm, private


def commands(action):
    if not isinstance(action, dict) or not isinstance(action.get('hands', []), list):
        return None
    units = [action.get('farmer'), *action.get('hands', [])]
    if any(u is not None and not isinstance(u, list) for u in units):
        return None
    return units


def market_safe(action, *, spare_slot=False):
    if not isinstance(action, dict):
        return False
    rows = action.get('market', [])
    if not isinstance(rows, list) or (spare_slot and len(rows) >= 10):
        return False
    # Conservative all-row guard; never compact or reinterpret a dead suffix.
    return all(isinstance(row, list) and (not row or row[0] == 'SELL') for row in rows)


def future_reason(tape, step):
    end = (step // 24 + 1) * 24
    if not isinstance(tape, list) or len(tape) < end:
        return 'incomplete-day'
    for action in tape[step + 1:end]:
        units = commands(action)
        if units is None or not market_safe(action):
            return 'future-market-or-schema'
        for unit in units:
            if unit and unit[0] == 'COLLECT_FERTILIZER':
                return 'future-collection'
            if unit and len(unit) >= 2 and unit[:2] == ['PICKUP', 'WHEAT']:
                return 'future-wheat-pickup'
    return None


def targets(farm):
    result = []
    for y, row in enumerate(farm['tiles']):
        for x, tile in enumerate(row):
            if x >= 5 and y >= 5:
                continue
            if not isinstance(tile, dict) or tile.get('fertilizer_available') is not True:
                continue
            a, k = tile.get('animal'), tile.get('kind')
            if (a == 'GOOSE' and k == 'COOP') or (a in ('COW', 'SHEEP') and k == 'PASTURE'):
                result.append((x, y))
    return result


def reachable_count(start, points, callbacks):
    pos, left, spent, count = tuple(start), list(points), 0, 0
    while left and count < 6:
        target = min(left, key=lambda p: (abs(pos[0]-p[0])+abs(pos[1]-p[1]), p[1], p[0]))
        cost = abs(pos[0]-target[0]) + abs(pos[1]-target[1]) + 1
        if spent + cost > callbacks:
            break
        spent += cost
        count += 1
        pos = target
        left.remove(target)
    return count


def fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a+b
    return a


@dataclass(frozen=True)
class Admission:
    reason: str
    units: int = 0
    hire_cost: int = 0
    quote: float = 0.0

    @property
    def allowed(self):
        return self.reason == 'admit'


def assess(obs, action, configuration, tapes, *, reserve=100.0):
    """Read-only donor-family gate; certify every supplied possible native tape.

    Complete same-day coverage is required (unlike canonical donor f14e).
    The caller must supply all possible native tapes, not a guessed future route.
    Neither current price nor present headroom guarantees future realized profit.
    """
    if not standard(configuration) or type(reserve) not in (int, float):
        return Admission('configuration')
    try:
        if not math.isfinite(reserve) or reserve < 100:
            return Admission('configuration')
    except (OverflowError, TypeError):
        return Admission('configuration')
    parsed = farm_of(obs)
    if parsed is None:
        return Admission('observation')
    farm, private = parsed
    day, hour = divmod(obs['step'], 24)
    if not 4 <= day <= 23 or not 14 <= hour < 23:
        return Admission('phase')
    units = commands(action)
    if units is None or not market_safe(action, spare_slot=True):
        return Admission('current-market-or-schema')
    if any(u and u[0] == 'COLLECT_FERTILIZER' for u in units):
        return Admission('current-collection')
    if not isinstance(tapes, (list, tuple)) or not tapes:
        return Admission('missing-tapes')
    for tape in tapes:
        reason = future_reason(tape, obs['step'])
        if reason:
            return Admission(reason)
    points = targets(farm)
    if not points:
        return Admission('no-targets')
    n = min(reachable_count(p, points, 23-hour) for p in STARTS)
    if n == 0:
        return Admission('reachability')
    hired = farm.get('hires_today')
    price = obs['market']['prices'].get('FERTILIZER')
    money = farm.get('money')
    if (not plain_int(hired) or hired > 240 or not plain_int(price, 1)
            or type(money) not in (int, float)):
        return Admission('numeric')
    try:
        cash, quote = float(money), n * price * 0.8
    except (OverflowError, ValueError):
        return Admission('numeric')
    if not math.isfinite(cash) or cash < 0 or not math.isfinite(quote):
        return Admission('numeric')
    cost = fib(hired)
    if quote-cost < 100 or quote < 1.2*cost or cash < cost+reserve:
        return Admission('value-or-cash', n, cost, quote)
    total = sum(private['shed'].values()) + sum(sum(inv.values()) for inv in private['inventories'])
    if total+n > 88:
        return Admission('headroom', n, cost, quote)
    return Admission('admit', n, cost, quote)


def parent_view(obs, index):
    """Detach the observation. No parent write can corrupt real actor custody."""
    result = deepcopy(obs)
    del result['farms'][result['player']]['hands'][index]
    del result['private']['inventories'][index+1]
    return result


def remap(action, index, command):
    """Preserve omitted/invalid/ghost parent rows under the official raw-row ABI.

    A short vector must be padded before insertion. All original rows, including
    ghost PLANT demands, retain their order and contents; non-list hands are the
    interpreter's empty vector. New commands never contain a PLANT request.
    """
    if not isinstance(action, dict):
        return action
    if not plain_int(index):
        raise ValueError('invalid hidden index')
    if not isinstance(command, list) or not command or command[0] not in (
            'PASS', 'NORTH', 'SOUTH', 'EAST', 'WEST', 'COLLECT_FERTILIZER'):
        raise ValueError('invalid sweep command')
    result = deepcopy(action)
    rows = result.get('hands', [])
    if not isinstance(rows, list):
        rows = []
    rows.extend([['PASS'] for _ in range(max(0, index-len(rows)))])
    rows.insert(index, deepcopy(command))
    result['hands'] = rows
    return result


def hand_command(obs, index):
    farm = obs['farms'][obs['player']]
    x, y = farm['hands'][index]
    choices = []
    for tx, ty in targets(farm):
        d = abs(x-tx)+abs(y-ty)
        if d+1 <= 24-obs['step']%24:
            choices.append((d, ty, tx))
    if not choices:
        return ['PASS']
    _, ty, tx = min(choices)
    if x != tx:
        return ['EAST' if x < tx else 'WEST']
    if y != ty:
        return ['SOUTH' if y < ty else 'NORTH']
    return ['COLLECT_FERTILIZER']


@dataclass(frozen=True)
class Pending:
    step: int
    index: int
    hires_today: int


class SweepExperiment:
    """One-game OFF/ON native experiment, not a deadline-integrated release.

    Only the synchronous experiment driver supplies actions to the interpreter.
    There is no downstream action rewriting after this wrapper; a different
    caller needs its own final-return commit hook. Instances must not be shared
    between seats or episodes. Cancellation/time-budget eligibility is NOT proved.
    """
    def __init__(self, parent: Callable, tapes_of: Callable, *, reserve=100.0):
        self.parent, self.tapes_of, self.reserve = parent, tapes_of, reserve
        self.day = None
        self.player = None
        self.last_step = -1
        self.pending = None
        self.index = None
        self.tried = False
        self.report = {'admissions': 0, 'confirmed_hires': 0, 'failed_hires': 0,
                       'collection_requests': 0, 'owned_callbacks': 0, 'reasons': {}}

    def __call__(self, obs, cfg):
        parsed = farm_of(obs)
        if parsed is None or not standard(cfg):
            if self.index is not None or self.pending is not None:
                raise ValueError('unsupported observation while owning a hand')
            return self.parent(obs, cfg)
        farm, private = parsed
        step, player = obs['step'], obs['player']
        if self.player is not None and player != self.player:
            raise ValueError('one experiment instance per player')
        if step <= self.last_step:
            raise ValueError('one monotonic experiment invocation per step')
        if (self.pending is not None or self.index is not None) and step != self.last_step+1:
            raise ValueError('nonconsecutive callback during actor custody')
        self.player, self.last_step = player, step
        day = step//24
        if day != self.day:
            self.day, self.pending, self.index, self.tried = day, None, None, False
        if self.pending is not None:
            p = self.pending
            if (step == p.step+1 and len(farm['hands']) == p.index+1
                    and farm['hires_today'] == p.hires_today+1
                    and len(private['inventories']) == p.index+2):
                self.index = p.index
                self.report['confirmed_hires'] += 1
            else:
                self.report['failed_hires'] += 1
            self.pending = None
        if self.index is not None:
            if self.index >= len(farm['hands']):
                raise ValueError('owned actor disappeared before EOD')
            action = self.parent(parent_view(obs, self.index), cfg)
            command = hand_command(obs, self.index)
            parent_rows = [action.get('farmer')] if isinstance(action, dict) else []
            if isinstance(action, dict) and isinstance(action.get('hands'), list):
                parent_rows += action['hands']
            if any(isinstance(row, list) and row and row[0] == 'COLLECT_FERTILIZER'
                   for row in parent_rows):
                command = ['PASS']  # Dynamic native collectors keep first claim.
            result = remap(action, self.index, command)
            self.report['owned_callbacks'] += 1
            if isinstance(result, dict) and command == ['COLLECT_FERTILIZER']:
                self.report['collection_requests'] += 1
            return result
        action = self.parent(obs, cfg)
        if self.tried:
            return action
        # Read routes AFTER the real native parent chooses/initializes them.
        tapes = self.tapes_of()
        gate = assess(obs, action, cfg, tapes, reserve=self.reserve)
        reasons = self.report['reasons']
        reasons[gate.reason] = reasons.get(gate.reason, 0)+1
        if not gate.allowed:
            return action
        result = deepcopy(action)
        result['market'] = deepcopy(action.get('market', []))+[['HIRE']]
        pending = Pending(step, len(farm['hands']), farm['hires_today'])
        # This exact action is the last mutation in the synchronous experiment.
        self.tried, self.pending = True, pending
        self.report['admissions'] += 1
        return result


def install(parent, tapes_of, *, enabled=False, reserve=100.0):
    """Literal-OFF is identical; malformed flags are rejected, never activated."""
    if type(enabled) is not bool:
        raise ValueError('enabled must be a literal bool')
    return SweepExperiment(parent, tapes_of, reserve=reserve) if enabled else parent

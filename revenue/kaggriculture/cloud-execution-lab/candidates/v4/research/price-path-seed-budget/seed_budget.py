# SPDX-License-Identifier: Apache-2.0
"""PRICE-PATH seed funding, independent of the unrecovered historical projector.

This module does NOT predict prices or promise crop profitability. It makes an
explicit next-turn crop proposal executable without crediting hoped-for SELL
receipts. Purchases retain raw slots and incumbent fixed-cost acquisitions.
Planting requires the actual final purchase return and a new observed seed
balance. Use before the selected-action consumer, not after its receipts.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Mapping

SEED_COST = {'WHEAT': 10, 'CARROT': 20, 'TOMATO': 50,
             'STRAWBERRY': 100, 'MELON': 80}
ANIMAL_COST = {'GOOSE': 300, 'COW': 400, 'SHEEP': 500}
LAND_COST = (1000, 2000, 4000)


def _integer(value: Any, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _money(value: Any) -> bool:
    return (type(value) in (int, float) and math.isfinite(value) and value >= 0)


def _units(action: Mapping[str, Any]) -> list:
    if not isinstance(action, Mapping):
        raise ValueError('invalid action')
    hands = action.get('hands', [])
    farmer = action.get('farmer', [])
    if type(hands) is not list or type(farmer) is not list:
        raise ValueError('invalid unit vector')
    units = [farmer, *hands]
    if any(type(row) is not list for row in units):
        raise ValueError('invalid unit row')
    return units


def _plants(action: Mapping[str, Any]) -> Counter:
    # Deliberately includes ghost and infeasible actors: the engine's atomic
    # availability check counts the entire authored vector before execution.
    return Counter(row[1] for row in _units(action)
                   if len(row) >= 2 and row[0] == 'PLANT' and row[1] in SEED_COST)


def _signature(action: Mapping[str, Any], cap: int) -> str:
    payload = {'units': _units(action), 'market': action.get('market', [])[:cap]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def _context(obs: Mapping, cfg: Mapping) -> tuple[int, int, int, int]:
    if not isinstance(obs, Mapping) or not isinstance(cfg, Mapping):
        raise ValueError('invalid context')
    step, seat = obs.get('step'), obs.get('player')
    cap, board = cfg.get('maxMarketOrdersPerTurn', 10), cfg.get('boardSize', 10)
    if not _integer(step) or type(seat) is not int or seat not in (0, 1):
        raise ValueError('invalid identity')
    if not _integer(cap) or not _integer(board, 2) or board % 2:
        raise ValueError('invalid dimensions')
    return step, seat, max(1, cap), board


def _fixed_cost(market: list, farm: Mapping, cfg: Mapping) -> int:
    """Reserve all incumbent acquisition costs, never count sale revenue.

    Dynamic product buys are vetoed: their future lockstep quote depends on the
    opponent. Failed expensive incumbent rows are NOT treated as free budget.
    """
    hires = farm.get('hires_today')
    mult = cfg.get('farmHandCostMult', 1)
    quads = farm.get('unlocked_quadrants')
    if (not _integer(hires) or hires > 100 or not _integer(mult)
            or type(quads) is not list or not 1 <= len(quads) <= 4):
        raise ValueError('invalid acquisition state')
    a, b = 1, 1
    for _ in range(hires):
        a, b = b, a + b
    land = len(quads) - 1
    total = 0
    for row in market:
        if type(row) is not list:
            raise ValueError('non-list market row')
        if not row:
            continue
        op = row[0]
        if op == 'HIRE' and len(row) == 1:
            total += a * mult
            a, b = b, a + b
        elif op == 'BUY_LAND' and len(row) == 1:
            if land < len(LAND_COST):
                total += LAND_COST[land]
                land += 1
        elif op in ('BUY_SEED', 'BUY_ANIMAL') and len(row) == 3:
            table = SEED_COST if op == 'BUY_SEED' else ANIMAL_COST
            if row[1] not in table or not _integer(row[2], 1):
                raise ValueError('invalid fixed acquisition')
            total += table[row[1]] * row[2]
        elif op == 'SELL' and len(row) == 3 and _integer(row[2], 1):
            # SELL proceeds are not required for the purchase certificate.
            if row[1] not in (*SEED_COST, 'EGG', 'MILK', 'WOOL', 'FERTILIZER'):
                raise ValueError('invalid sale')
        else:
            raise ValueError('unsupported or dynamic acquisition')
    return total


@dataclass(frozen=True)
class Ticket:
    episode: str
    seat: int
    step: int
    route: str
    cap: int
    board: int
    slots: tuple[int, ...]
    source: str
    target: str
    quantity: int
    cost: int
    purchase_signature: str


class SeedBudget:
    """One pending proposal, explicitly committed to a real returned action.

    Separate instances per agent/episode. Every apply consumes pending state,
    including rejected observations. A returned purchase is intent, not fill:
    apply checks the entire proposed raw PLANT demand against observed seeds.
    """
    def __init__(self) -> None:
        self.pending: Ticket | None = None
        self.committed: Ticket | None = None

    def reset(self) -> None:
        self.pending = self.committed = None

    def prepare(self, action: Mapping, obs: Mapping, cfg: Mapping, next_action: Mapping,
                *, episode: str, route: str, source: str, target: str,
                budget: int = 500, reserve: int = 250, max_plants: int = 2,
                enabled: bool = False) -> tuple[Mapping, dict]:
        """Append/fill one raw slot with a fully cash-backed seed purchase.

        Existing seed purchases are left untouched, including source seeds.
        This conservative pilot therefore charges unused seed cost in economics.
        No route mutation, market compaction, product speculation, or credit.
        """
        self.pending = None
        report = {'status': 'disabled'}
        if not enabled:
            return action, report
        try:
            step, seat, cap, board = _context(obs, cfg)
            if (not isinstance(episode, str) or not episode or not isinstance(route, str)
                    or source not in SEED_COST or target not in SEED_COST or source == target
                    or not _integer(budget) or not _integer(reserve)
                    or not _integer(max_plants, 1)):
                raise ValueError('invalid proposal')
            end = cfg.get('episodeSteps', 720)
            if not _integer(end, 3) or step + 1 > end - 2:
                raise ValueError('no next callback')
            _units(action)
            market = action.get('market', [])
            if type(market) is not list:
                raise ValueError('invalid market')
            farm, seeds = obs['farms'][seat], obs['private']['seeds']
            money = farm['money']
            if not _money(money):
                raise ValueError('invalid cash')
            if any(not _integer(seeds.get(crop, 0)) for crop in SEED_COST):
                raise ValueError('invalid seeds')
            future = _units(next_action)
            slots = tuple(i for i, row in enumerate(future)
                          if row == ['PLANT', source])[:max_plants]
            if not slots:
                return action, {'status': 'no-proposed-plant'}
            changed = deepcopy(dict(next_action))
            for slot in slots:
                if slot == 0:
                    changed['farmer'] = ['PLANT', target]
                else:
                    changed['hands'][slot - 1] = ['PLANT', target]
            needed = _plants(changed)[target]
            # Reserve even infeasible current PLANT requests. Over-reservation
            # is conservative; ignoring ghost requests would not be.
            available = max(0, seeds.get(target, 0) - _plants(action)[target])
            quantity = max(0, needed - available)
            cost = quantity * SEED_COST[target]
            if cost > budget:
                return action, {'status': 'proposal-over-budget', 'cost': cost}
            incumbent = _fixed_cost(market[:cap], farm, cfg)
            if money < incumbent + cost + reserve:
                return action, {'status': 'cash-reserved', 'cost': cost,
                                'incumbent_cost': incumbent, 'money': money}
            result = action
            if quantity:
                # Existing raw order indexes remain unchanged, including tails.
                slot = next((i for i, row in enumerate(market[:cap]) if row == []), None)
                if slot is None:
                    if len(market) >= cap:
                        return action, {'status': 'no-live-slot', 'cost': cost}
                    slot = len(market)
                result = deepcopy(dict(action))
                result.setdefault('market', [])
                row = ['BUY_SEED', target, quantity]
                if slot == len(market):
                    result['market'].append(row)
                else:
                    result['market'][slot] = row
            ticket = Ticket(episode, seat, step, route, cap, board, slots,
                            source, target, quantity, cost, _signature(result, cap))
            self.pending = ticket
            report = {'status': 'purchase-proposed', 'quantity': quantity,
                      'cost': cost, 'incumbent_cost': incumbent, 'slots': list(slots),
                      'source': source, 'target': target}
            return result, report
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            return action, {'status': 'invalid-or-unsupported'}

    def record_returned(self, action: Mapping, obs: Mapping, cfg: Mapping,
                        *, episode: str, route: str) -> bool:
        """Read-only return observer. Never rewrite an already returned action."""
        ticket, self.pending = self.pending, None
        self.committed = None
        if ticket is None:
            return False
        try:
            step, seat, cap, board = _context(obs, cfg)
            valid = ((episode, seat, step, route, cap, board)
                     == (ticket.episode, ticket.seat, ticket.step, ticket.route,
                         ticket.cap, ticket.board)
                     and _signature(action, cap) == ticket.purchase_signature)
            if valid:
                self.committed = ticket
            return bool(valid)
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            return False

    def apply(self, action: Mapping, obs: Mapping, cfg: Mapping,
              *, episode: str, route: str) -> tuple[Mapping, dict]:
        """Consume a committed ticket before selected-action projections run."""
        ticket, self.committed = self.committed, None
        if ticket is None:
            return action, {'status': 'no-ticket'}
        try:
            step, seat, cap, board = _context(obs, cfg)
            if ((episode, seat, step - 1, route, cap, board)
                    != (ticket.episode, ticket.seat, ticket.step, ticket.route,
                        ticket.cap, ticket.board)):
                return action, {'status': 'stale-identity'}
            units = _units(action)
            if any(slot >= len(units) or units[slot] != ['PLANT', ticket.source]
                   for slot in ticket.slots):
                return action, {'status': 'parent-plant-changed'}
            seeds, farm = obs['private']['seeds'], obs['farms'][seat]
            if any(not _integer(seeds.get(crop, 0)) for crop in SEED_COST):
                raise ValueError('invalid observed seeds')
            # Do not incidentally unblock an atomic source-crop group that the
            # incumbent cannot execute. Both vectors need real stock backing.
            if any(seeds.get(crop, 0) < n for crop, n in _plants(action).items()):
                return action, {'status': 'parent-unfunded'}
            positions = [farm['farmer'], *farm['hands']]
            occupied = Counter(tuple(p) for p in positions)
            for slot in ticket.slots:
                if slot >= len(positions):
                    return action, {'status': 'missing-actor'}
                x, y = positions[slot]
                if (not _integer(x) or not _integer(y) or x >= board or y >= board
                        or occupied[(x, y)] != 1 or farm['tiles'][y][x] is not None):
                    return action, {'status': 'plant-site-unavailable'}
                quadrant = ('N' if y < board // 2 else 'S') + ('W' if x < board // 2 else 'E')
                if quadrant not in farm['unlocked_quadrants']:
                    return action, {'status': 'plant-site-unavailable'}
            result = deepcopy(dict(action))
            for slot in ticket.slots:
                if slot == 0:
                    result['farmer'] = ['PLANT', ticket.target]
                else:
                    result['hands'][slot - 1] = ['PLANT', ticket.target]
            demand = _plants(result)
            if any(seeds.get(crop, 0) < n for crop, n in demand.items()):
                return action, {'status': 'observed-fill-shortfall'}
            return result, {'status': 'plant-proposed', 'target': ticket.target,
                            'slots': list(ticket.slots), 'cost': ticket.cost,
                            'positions': [positions[i] for i in ticket.slots]}
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            return action, {'status': 'invalid-observed-state'}

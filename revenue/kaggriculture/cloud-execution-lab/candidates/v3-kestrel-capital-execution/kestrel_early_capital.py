# SPDX-License-Identifier: Apache-2.0
"""Execution-preserving same-queue capital ordering.

The official engine truncates the market queue before executing it and resolves
cash, shed capacity, hire escalation, and product inventory in queue-index order.
A rank-only sort can therefore activate an inert tail row or make an originally
executable order fail.  This revision treats ranking as a proposal, then admits
it only after replaying the exact own-side deterministic market semantics from
the post-unit state.

The transform never invents, deletes, resizes, or substitutes an order.  It
preserves active-prefix membership and accepts a reorder only when:

* every originally executed non-capital order executes the same quantity;
* no preserved sale earns less and no preserved purchase costs more;
* every already-successful admitted capital order remains successful; and
* at least one admitted capital order executes more than before.

The replay intentionally does not predict the rival's hidden queue.  It proves
the candidate does not depend on self-inflicted cash/capacity/order changes under
the public pre-market state; paired official games remain the strength gate.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math

PAYBACK_DAYS = {'GOOSE': 4, 'COW': 8, 'SHEEP': 6, 'LAND': 4}
EARLY_DAY_LIMIT = 20
KNOWN = frozenset(('SELL', 'HIRE', 'BUY_LAND', 'BUY_SEED',
                   'BUY_ANIMAL', 'BUY_PRODUCT', 'PASS'))
FUNDING = 0
OPERATING = 1
CAPITAL = 2
REST = 3
_MONEY_TOLERANCE = 1e-9


def _last_step(config):
    return int(config.get('episodeSteps', 720)) - 2


def _turns_per_day(config):
    return int(config.get('turnsPerDay', 24))


def _remaining_days(now, config):
    last = _last_step(config)
    tpd = _turns_per_day(config)
    if tpd <= 0 or now > last:
        return 0
    return max(0, (last - now) // tpd)


def _horizon_end(now, config, decisions):
    last = _last_step(config)
    tpd = _turns_per_day(config)
    end = min(last, now + tpd)
    for checkpoint, *_ in decisions or ():
        if now < int(checkpoint) <= end:
            end = int(checkpoint)
            break
    return end


def _qty(order):
    if not isinstance(order, list) or len(order) < 3:
        return 0
    try:
        return max(0, int(order[2]))
    except (TypeError, ValueError):
        return 0


def _valid_order(order):
    if order is None or order == []:
        return True
    if not isinstance(order, list) or not order or order[0] not in KNOWN:
        return False
    op = order[0]
    if op in ('PASS', 'HIRE', 'BUY_LAND'):
        return len(order) == 1
    if len(order) < 3 or _qty(order) <= 0:
        return False
    return isinstance(order[1], str) and bool(order[1])


def _plant_demand(selected, route, now, end):
    demand = {}

    def add(row):
        if not isinstance(row, dict):
            return
        acts = [row.get('farmer', ['PASS']), *(row.get('hands') or [])]
        for action in acts:
            if action and action[0] == 'PLANT' and len(action) > 1:
                crop = action[1]
                demand[crop] = demand.get(crop, 0) + 1

    add(selected)
    if route:
        for t in range(now + 1, min(end + 1, len(route))):
            add(route[t])
    return demand


def _capital_admitted(order, now, remaining, day):
    if not order or day > EARLY_DAY_LIMIT:
        return False
    op = order[0]
    if op == 'BUY_LAND':
        return remaining >= PAYBACK_DAYS['LAND']
    if op == 'BUY_ANIMAL' and len(order) > 2 and _qty(order) > 0:
        return remaining >= PAYBACK_DAYS.get(order[1], 8)
    return False


def _rank(order, now, remaining, day, plant_demand, seeds_held):
    if not order:
        return REST
    op = order[0]
    if op == 'SELL':
        return FUNDING
    if op == 'HIRE':
        return OPERATING
    if op == 'BUY_SEED':
        crop = order[1]
        need = max(0, int(plant_demand.get(crop, 0))
                   - int(seeds_held.get(crop, 0)))
        return OPERATING if need > 0 else REST
    if _capital_admitted(order, now, remaining, day):
        return CAPITAL
    return REST


def _post_unit_state(mechanics, observation, configuration, selected, post_unit):
    """Return copied ``(farm, private, market, source)`` for own-side replay."""
    player = int(observation['player'])
    source = 'computed_unit_replay'
    if post_unit is not None:
        source = 'bound_post_unit_snapshot'
        if (not isinstance(post_unit, dict)
                or not isinstance(post_unit.get('farms'), list)
                or player >= len(post_unit['farms'])
                or not isinstance(post_unit.get('private'), dict)):
            raise ValueError('malformed post-unit snapshot')
        farm = deepcopy(post_unit['farms'][player])
        private = deepcopy(post_unit['private'])
    else:
        farms = observation.get('farms')
        private_source = observation.get('private')
        if (not isinstance(farms, list) or player >= len(farms)
                or not isinstance(private_source, dict)):
            raise ValueError('missing own state')
        farm = deepcopy(farms[player])
        private = deepcopy(private_source)
        tiles = farm.get('tiles')
        if not isinstance(tiles, list) or not tiles:
            raise ValueError('missing farm tiles')
        board_size = int(configuration.get('boardSize', len(tiles)))
        tpd = _turns_per_day(configuration)
        day = int(observation.get(
            'day',
            int(observation.get('step', 0)) // max(1, tpd),
        ))
        capacity = int(configuration.get('shedCapacity', 100))
        apply_unit = getattr(mechanics, '_apply_unit_action', None)
        if apply_unit is None:
            raise ValueError('mechanics lacks unit replay')
        actions = [selected.get('farmer', ['PASS']),
                   *(selected.get('hands') or [])]
        for idx, action in enumerate(actions):
            apply_unit(farm, private, idx, action, board_size, day, tpd,
                       capacity)

    market = deepcopy(observation.get('market'))
    if (not isinstance(farm, dict) or not isinstance(private, dict)
            or not isinstance(market, dict)):
        raise ValueError('malformed replay state')
    money = farm.get('money')
    if not isinstance(money, (int, float)) or not math.isfinite(float(money)):
        raise ValueError('invalid money')
    if not isinstance(private.get('shed'), dict):
        raise ValueError('missing shed')
    if not isinstance(private.get('seeds'), dict):
        raise ValueError('missing seeds')
    if not isinstance(private.get('inventories'), list):
        raise ValueError('missing inventories')
    inventory = market.get('inventory')
    if not isinstance(inventory, dict):
        raise ValueError('missing market inventory')
    for item in getattr(mechanics, 'PRODUCTS', ()):
        value = inventory.get(item)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError('invalid market inventory')
    return farm, private, market, source


def _parsed_order(mechanics, order):
    """Validate one order against the exact official operation domains."""
    if not _valid_order(order):
        raise ValueError('malformed market order')
    if not order:
        return 'EMPTY', None, 0
    op = order[0]
    if op in ('PASS', 'HIRE', 'BUY_LAND'):
        return op, None, 1
    item = order[1]
    qty = _qty(order)
    if op == 'SELL' and item not in mechanics.PRODUCTS:
        raise ValueError('invalid SELL item')
    if op == 'BUY_PRODUCT' and item not in ('WHEAT', 'FERTILIZER'):
        raise ValueError('invalid BUY_PRODUCT item')
    if op == 'BUY_SEED' and item not in mechanics.CROPS:
        raise ValueError('invalid BUY_SEED item')
    if op == 'BUY_ANIMAL' and item not in mechanics.ANIMALS:
        raise ValueError('invalid BUY_ANIMAL item')
    return op, item, qty


def _simulate_market(mechanics, base_state, entries, configuration):
    """Replay one player's queue, retaining original-index receipts.

    This mirrors the official own-side deterministic commit rules.  Rival
    lockstep actions are unknowable at decision time and are deliberately not
    guessed.
    """
    farm, private, market = deepcopy(base_state)
    board_size = int(configuration.get(
        'boardSize', len(farm.get('tiles') or []),
    ))
    if board_size <= 0:
        raise ValueError('invalid board size')
    capacity = int(configuration.get('shedCapacity', 100))
    hire_mult = int(configuration.get(
        'farmHandCostMult', getattr(mechanics, 'FARM_HAND_COST_MULT', 1),
    ))
    receipts = {}

    for original_index, order in entries:
        op, item, requested = _parsed_order(mechanics, order)
        receipt = {
            'index': int(original_index),
            'op': op,
            'item': item,
            'requested': int(
                requested if op not in ('PASS', 'EMPTY') else 0
            ),
            'executed': 0,
            'gross': 0.0,
            'cost': 0.0,
        }
        receipts[original_index] = receipt

        if op in ('PASS', 'EMPTY'):
            continue
        before_money = float(farm['money'])
        if op == 'HIRE':
            before_hires = int(farm.get('hires_today', 0))
            mechanics._do_hire(farm, private, board_size, hire_mult)
            receipt['executed'] = int(
                int(farm.get('hires_today', 0)) > before_hires
            )
            receipt['cost'] = max(0.0, before_money - float(farm['money']))
            continue
        if op == 'BUY_LAND':
            before_unlocked = len(farm.get('unlocked_quadrants') or [])
            mechanics._do_buy_land(farm, board_size)
            receipt['executed'] = int(
                len(farm.get('unlocked_quadrants') or []) > before_unlocked
            )
            receipt['cost'] = max(0.0, before_money - float(farm['money']))
            continue

        for _ in range(requested):
            inventory = market['inventory']
            if op == 'SELL':
                price = mechanics.market_price(
                    item, inventory[item], market.get('params'),
                )
            elif op == 'BUY_PRODUCT':
                price = mechanics.market_price(
                    item, inventory[item] - 1, market.get('params'),
                )
            elif op == 'BUY_SEED':
                price = mechanics.CROPS[item]['seed']
            else:
                price = mechanics.ANIMALS[item]['cost']
            unit_before = float(farm['money'])
            if not mechanics._commit_unit(
                    op, item, price, farm, private, market, capacity):
                break
            receipt['executed'] += 1
            delta = float(farm['money']) - unit_before
            if delta >= 0:
                receipt['gross'] += delta
            else:
                receipt['cost'] -= delta

    canonical_receipts = [
        receipts[index] for index in sorted(receipts)
    ]
    payload = {
        'receipts': canonical_receipts,
        'money': float(farm['money']),
        'shed_total': int(sum(private['shed'].values())),
        'hires_today': int(farm.get('hires_today', 0)),
        'unlocked_quadrants': len(farm.get('unlocked_quadrants') or []),
        'market_inventory': {
            item: market['inventory'][item]
            for item in sorted(market['inventory'])
        },
    }
    payload['sha256'] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(',', ':'),
                   allow_nan=False).encode('utf-8')
    ).hexdigest()
    return payload, receipts


def _execution_gate(original, candidate, entries, admitted):
    """Return ``(accepted, capital_gain, failures)``."""
    failures = []
    capital_gain = 0
    original_payload, original_receipts = original
    candidate_payload, candidate_receipts = candidate

    for original_index, order in entries:
        before = original_receipts[original_index]
        after = candidate_receipts[original_index]
        if original_index in admitted:
            if after['executed'] < before['executed']:
                failures.append({
                    'index': original_index,
                    'reason': 'capital_execution_regressed',
                    'before': before['executed'],
                    'after': after['executed'],
                })
            capital_gain += max(0, after['executed'] - before['executed'])
            continue

        if after['executed'] != before['executed']:
            failures.append({
                'index': original_index,
                'reason': 'noncapital_execution_changed',
                'before': before['executed'],
                'after': after['executed'],
            })
            continue
        op = order[0] if order else 'EMPTY'
        if (op == 'SELL'
                and after['gross'] + _MONEY_TOLERANCE < before['gross']):
            failures.append({
                'index': original_index,
                'reason': 'sale_proceeds_regressed',
                'before': before['gross'],
                'after': after['gross'],
            })
        if (op in ('HIRE', 'BUY_SEED', 'BUY_PRODUCT', 'BUY_ANIMAL')
                and after['cost'] > before['cost'] + _MONEY_TOLERANCE):
            failures.append({
                'index': original_index,
                'reason': 'purchase_cost_regressed',
                'before': before['cost'],
                'after': after['cost'],
            })

    # Admitted capital does not mutate public product inventory.  With every
    # non-capital execution held fixed, inventory drift signals a replay bug or
    # an unclassified operation and must fail closed.
    if candidate_payload['market_inventory'] != original_payload['market_inventory']:
        failures.append({'reason': 'market_inventory_drift'})
    if capital_gain <= 0:
        failures.append({'reason': 'no_capital_execution_gain'})
    return not failures, capital_gain, failures


def order_early_capital(mechanics, observation, configuration, selected,
                        route, decisions=(), *, post_unit=None):
    """Propose and prove a safer active-prefix market ordering.

    ``post_unit`` may bind the replay to the caller's exact completed post-unit
    observation.  Standalone callers may omit it; the official extracted unit
    primitive is then used to reconstruct the same state.
    """
    report = {
        'changed': False,
        'reason': 'init',
        'moved': 0,
        'reserved': 0,
        'reduced': [],
        'revision': 'v3-execution-preserving',
    }
    if not isinstance(selected, dict):
        report['reason'] = 'no_action'
        return selected, report
    market_source = selected.get('market')
    if not isinstance(market_source, list):
        report['reason'] = 'malformed_market'
        return selected, report
    market = deepcopy(market_source)
    if not market:
        report['reason'] = 'empty_market'
        return selected, report

    try:
        tpd = _turns_per_day(configuration)
        if tpd <= 0:
            raise ValueError('turnsPerDay must be positive')
        now = int(observation.get('step') if observation.get('step') is not None
                  else int(observation['day']) * tpd
                  + int(observation['hour']))
        last = _last_step(configuration)
        max_orders = max(
            1, int(configuration.get('maxMarketOrdersPerTurn', 10)),
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        report['reason'] = 'malformed_context'
        return selected, report
    if now >= last:
        report['reason'] = 'terminal_window'
        return selected, report

    active = market[:max_orders]
    tail = market[max_orders:]
    if any(not _valid_order(order) for order in active):
        report['reason'] = 'malformed_active_order'
        return selected, report

    day = now // tpd
    remaining = _remaining_days(now, configuration)
    horizon = _horizon_end(now, configuration, decisions)
    plants = _plant_demand(selected, route, now, horizon)
    private = observation.get('private') or {}
    seeds_held = private.get('seeds') if isinstance(private, dict) else {}
    if not isinstance(seeds_held, dict):
        seeds_held = {}
    ranks = [
        _rank(order, now, remaining, day, plants, seeds_held)
        for order in active
    ]
    admitted = {
        index for index, order in enumerate(active)
        if _capital_admitted(order, now, remaining, day)
    }
    if not admitted:
        report.update(reason='no_admitted_capital', active_prefix=len(active),
                      inactive_tail=len(tail), horizon_end=horizon,
                      remaining_days=remaining)
        return selected, report

    indexed = list(enumerate(active))
    proposed_entries = sorted(
        indexed, key=lambda item: (ranks[item[0]], item[0]),
    )
    proposed_active = [deepcopy(order) for _, order in proposed_entries]
    moved = sum(
        1 for old, new in zip(active, proposed_active) if old != new
    )
    if proposed_active == active:
        report.update(reason='already_ordered', active_prefix=len(active),
                      inactive_tail=len(tail), horizon_end=horizon,
                      remaining_days=remaining)
        return selected, report

    try:
        farm, replay_private, public_market, source = _post_unit_state(
            mechanics, observation, configuration, selected, post_unit,
        )
        base_state = (farm, replay_private, public_market)
        original = _simulate_market(
            mechanics, base_state, indexed, configuration,
        )
        candidate = _simulate_market(
            mechanics, base_state, proposed_entries, configuration,
        )
        accepted, capital_gain, failures = _execution_gate(
            original, candidate, indexed, admitted,
        )
    except (KeyError, TypeError, ValueError, OverflowError,
            AttributeError) as error:
        report.update(
            reason='simulation_unavailable',
            proposed_moved=moved,
            active_prefix=len(active),
            inactive_tail=len(tail),
            simulation_error=type(error).__name__,
        )
        return selected, report

    report.update(
        proposed_moved=moved,
        active_prefix=len(active),
        inactive_tail=len(tail),
        horizon_end=horizon,
        remaining_days=remaining,
        simulation_source=source,
        original_receipt_sha256=original[0]['sha256'],
        candidate_receipt_sha256=candidate[0]['sha256'],
        original_receipts=original[0]['receipts'],
        candidate_receipts=candidate[0]['receipts'],
        capital_execution_gain=capital_gain,
        guard_failures=failures,
    )
    if not accepted:
        report['reason'] = 'execution_guard_rejected'
        return selected, report

    result = deepcopy(selected)
    result['market'] = proposed_active + deepcopy(tail)
    report.update(changed=True, reason='execution_gain_proved', moved=moved)
    return result, report

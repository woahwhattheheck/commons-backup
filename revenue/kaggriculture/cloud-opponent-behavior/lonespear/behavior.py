"""Public-state HIRE-prefix model for pinned lonespear v18; no policy imports.

This models a named source, not identification of an unknown opponent. Feed
requests remain intervals because rival shed and seed inventory are private.
"""
from __future__ import annotations
import copy
import math
from collections.abc import Mapping
from typing import Any

SOURCE_REF = '774b26093ccf4246525517d48420349b841b6e50'
SOURCE_SHA256 = 'eb5b5f59a8ec2d40b77cc99d4ffe3b932136fdcf9f6b6e168726b7f07ab47cb0'
SCHEMA = 'titan.lonespear-public-prefix.v1'


def _integer(value: Any, name: str, low: int = 0) -> int:
    if type(value) is not int or value < low:
        raise ValueError(f'{name} must be an integer >= {low}')
    return value


def _cash(value: Any) -> float | int:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('money must be finite and nonnegative')
    return value



def _absolute_step(observation: Mapping[str, Any],
                   configuration: Mapping[str, Any] | None = None) -> int:
    """Retain an explicit step; otherwise derive it from the public day/hour."""
    step = observation.get('step')
    if step is not None:
        return _integer(step, 'step')
    cfg = configuration if configuration is not None else {}
    period = _integer(cfg.get('turnsPerDay', 24), 'turnsPerDay', 1)
    day = _integer(observation.get('day'), 'day')
    hour = _integer(observation.get('hour'), 'hour')
    if hour >= period:
        raise ValueError('hour must be below turnsPerDay when deriving step')
    return day * period + hour


def _counts(tiles: Any) -> dict[str, int]:
    if not isinstance(tiles, (list, tuple)) or not tiles:
        raise ValueError('public tile grid missing')
    count = dict(animals=0, plants=0, empty=0)
    for row in tiles:
        if not isinstance(row, (list, tuple)):
            raise ValueError('public tile row missing')
        for tile in row:
            if tile is None:
                count['empty'] += 1
            elif isinstance(tile, Mapping):
                if tile.get('kind') in ('PASTURE', 'COOP') and tile.get('animal'):
                    count['animals'] += 1
                elif tile.get('kind') == 'PLANT':
                    count['plants'] += 1
            elif tile != 'LOCKED':
                raise ValueError('unrecognized public tile')
    return count


def _hire_cost(index: int, multiplier: int) -> int:
    a, b = 1, 1
    for _ in range(index):
        a, b = b, a + b
    return a * multiplier


def predict(observation: Mapping[str, Any], configuration: Mapping[str, Any] | None = None,
            *, actor: int | None = None) -> dict[str, Any]:
    """Predict the source's leading HIRE requests and fills using PUBLIC data.

    Defaults to the opponent of observation.player. Does not read private,
    observation.action, seed, filenames, previous outcomes, or supplied labels.
    Fills are exact conditional on this source's leading queue and the official
    engine: hires have no stock requirement and precede every other purchase.
    """
    result: dict[str, Any] = {'schema': SCHEMA, 'source_ref': SOURCE_REF,
        'source_sha256': SOURCE_SHA256, 'status': 'unknown',
        'applicability': 'conditional on exact named source; not opponent identification'}
    try:
        cfg = configuration or {}
        if actor is None:
            player = _integer(observation.get('player'), 'player')
            if player not in (0, 1):
                raise ValueError('player must be 0 or 1')
            actor = 1-player
        if type(actor) is not int or actor not in (0, 1):
            raise ValueError('actor must be 0 or 1')
        farms = observation.get('farms')
        if not isinstance(farms, (list, tuple)) or len(farms) != 2:
            raise ValueError('two public farms required')
        farm = farms[actor]
        day = _integer(observation.get('day'), 'day')
        hour = _integer(observation.get('hour'), 'hour')
        step = _absolute_step(observation, cfg)
        money = _cash(farm.get('money'))
        hands = farm.get('hands')
        if not isinstance(hands, (list, tuple)):
            raise ValueError('public hands missing')
        hires = _integer(farm.get('hires_today'), 'hires_today')
        # Actual source is bounded to <=11 hires; avoid arbitrary huge indices.
        if hires > 100:
            raise ValueError('hires_today outside supported engine-state range')
        counts = _counts(farm.get('tiles'))
        multiplier = _integer(cfg.get('farmHandCostMult', 1), 'farmHandCostMult')
        max_orders = _integer(cfg.get('maxMarketOrdersPerTurn', 10), 'maxMarketOrdersPerTurn', 1)
        workload = 3*counts['animals'] + counts['plants'] + counts['empty']//3
        target = min(11, max(4, workload//4))
        eligible = hour <= 2 and hires < target and money > 40
        requests = max(0, min(target-len(hands), 6)) if eligible else 0
        executable = min(requests, max_orders)
        remaining, fills, costs = money, 0, []
        for _ in range(executable):
            price = _hire_cost(hires+fills, multiplier)
            if remaining < price:
                break  # Every later leading request retries the same cost.
            remaining -= price
            fills += 1
            costs.append(price)
        need_feed = int(counts['animals']*1.5)+5
        possible_feed = money > 60 and requests < min(10, max_orders)
        reason = ('late_hour' if hour > 2 else 'cash_threshold' if money <= 40
                  else 'daily_hire_target' if hires >= target else 'already_staffed'
                  if len(hands) >= target else 'requests_emitted')
        result.update(status='known', actor=actor, day=day, hour=hour, step=step,
            public=dict(**counts, money=money, hands=len(hands), hires_today=hires),
            workload=workload, target_hands=target, reason=reason,
            hire_requests=requests, executable_hire_requests=executable,
            hire_prefix_fills=fills, hire_costs=costs,
            cash_after_hire_prefix=remaining,
            feed_request_units={'lower': 0, 'upper': min(need_feed, 15) if possible_feed else 0},
            possible_feed_slot=requests if possible_feed else None,
            feed_fill_units={'lower': 0, 'upper': min(need_feed, 15) if possible_feed else 0},
            feed_quantity_known=False,
            feed_budget_uses_pre_hire_cash=True)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as error:
        result['reason'] = str(error)
    return result


def observed_fill(before: Mapping[str, Any], after: Mapping[str, Any], *, actor: int,
                  configuration: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Measure consecutive within-day fills with explicit or public day/hour clocks.

    Optional configuration supplies turnsPerDay for a sparse clock. The same
    per-match configuration applies to both frames; daily resets stay unknown.
    """
    out: dict[str, Any] = {'status': 'unknown', 'fills': None}
    try:
        if type(actor) is not int or actor not in (0, 1):
            raise ValueError('actor must be 0 or 1')
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            raise ValueError('two public observation mappings required')
        step0 = _absolute_step(before, configuration)
        step1 = _absolute_step(after, configuration)
        if step1 != step0+1 or before.get('day') != after.get('day'):
            raise ValueError('nonconsecutive frames or day reset')
        for label, observation in (('before', before), ('after', after)):
            farms = observation.get('farms')
            if not isinstance(farms, (list, tuple)) or len(farms) != 2:
                raise ValueError(label + ': two public farms required')
            if not isinstance(farms[actor], Mapping):
                raise ValueError(label + ': public actor farm must be a mapping')
        old, new = before['farms'][actor], after['farms'][actor]
        delta = _integer(new.get('hires_today'), 'after.hires_today')-_integer(old.get('hires_today'), 'before.hires_today')
        if not isinstance(old.get('hands'), (list, tuple)) or not isinstance(new.get('hands'), (list, tuple)):
            raise ValueError('public hands missing')
        hands_delta = len(new['hands'])-len(old['hands'])
        if delta < 0 or delta != hands_delta:
            raise ValueError('hire and hand deltas disagree')
        out.update(status='known', fills=delta,
            public_cash_delta=_cash(new.get('money'))-_cash(old.get('money')),
            interpretation='cash delta includes all other market orders; not hire-only spending')
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as error:
        out['reason'] = str(error)
    return out


def propose_delayed_wheat_sale(action: Mapping[str, Any], prediction: Mapping[str, Any], *,
                               shed_wheat: int, retained_wheat: int,
                               max_orders: int = 10) -> dict[str, Any]:
    """Experimental one-turn response proposal, never automatic policy selection.

    With one non-reserved WHEAT sale in a sale-only queue, move it after the
    possible rival feed slot, preserving every other market index. PASS slots
    are engine-native ignored orders. Full-queue rival receipts
    must still be evaluated: request possibility is not proof of a rival buy.
    """
    fallback = copy.deepcopy(dict(action))
    out = {'action': fallback, 'changed': False, 'reason': 'unsupported_queue',
           'scope': 'one-turn proposal; no win, whole-continuation or robust-value claim'}
    orders = action.get('market')
    requests = prediction.get('hire_requests')
    if prediction.get('status') != 'known' or type(requests) is not int or requests <= 0:
        return out
    slot = prediction.get('possible_feed_slot')
    if type(slot) is not int or type(max_orders) is not int or slot < 0 or slot+1 >= max_orders:
        return out
    if type(max_orders) is not int or max_orders < 1 or not isinstance(orders, list) or len(orders) > max_orders:
        return out
    if any(not isinstance(o, (list, tuple)) or len(o) != 3 or o[0] != 'SELL'
           or type(o[2]) is not int or o[2] <= 0 for o in orders):
        return out
    matches = [i for i, o in enumerate(orders) if o[1] == 'WHEAT']
    if len(matches) != 1 or matches[0] >= slot+1:
        return out
    origin = matches[0]
    if slot+1 < len(orders):
        return out  # Never displace a different supplied market order.
    order = orders[origin]
    quantity = order[2]
    if type(quantity) is not int or quantity <= 0:
        return out
    if type(shed_wheat) is not int or type(retained_wheat) is not int or retained_wheat < 0 or shed_wheat < quantity+retained_wheat:
        out['reason'] = 'stock_reservation'
        return out
    proposed = copy.deepcopy(fallback)
    proposed['market'][origin] = ['PASS']
    proposed['market'].extend([['PASS'] for _ in range(slot+2-len(orders))])
    proposed['market'][slot+1] = list(order)
    out.update(action=proposed, changed=True, reason='after_possible_feed_slot', sale_slot=slot+1)
    return out

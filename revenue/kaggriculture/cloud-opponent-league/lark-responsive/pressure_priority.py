"""Observation-only SELL-lot pressure opponent; not a canonical-policy patch.

The same-sized rival lot is an explicit proxy, never observed hidden inventory.
The injected quote function must be the pinned engine's pure public price curve.
Contiguous SELL blocks may reorder. A wholly sale-only executable prefix may
also compact known empty slots; parent quantities and production remain intact.
At the final actionable step, sale-only rows just beyond the market-order cap
may additionally move into otherwise dead empty executable slots.
"""
from __future__ import annotations

import copy
import math
import time
from collections.abc import Callable, Mapping
from typing import Any

from sell_priority import PRODUCTS, _quote

PriceFunction = Callable[[str, int, Mapping | None], int | float]
MAX_SCORING_UNITS = 256
MAX_SCORING_ORDERS = 64
SALE_ONLY_GOODS = frozenset(("CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL"))
_UNSET_RIVAL_QUANTITY = object()


def _engine_sell_quantity(order: Any) -> int | None:
    """Return the pinned engine's positive int()-coerced SELL quantity.

    Classify only; callers always keep the original row bytes.  This keeps every
    pressure sub-transform on the same grammar as sell_priority._quote().
    """
    if not isinstance(order, list) or len(order) < 3 or order[0] != 'SELL':
        return None
    try:
        quantity = int(order[2])
    except (TypeError, ValueError, OverflowError):
        return None
    return quantity if quantity > 0 else None


def _sale_only_terminal_row(order: Any) -> int | None:
    """Classify a row for terminal compaction: positive=1, empty=0, barrier=None."""
    if order == []:
        return 0
    quantity = _engine_sell_quantity(order)
    if quantity is None:
        return None
    item = order[1]
    if not isinstance(item, str) or item not in SALE_ONLY_GOODS:
        return None
    return 1


def promote_terminal_sale_only_suffix(orders: list, end: int, observation: Mapping,
                                      configuration: Mapping) -> list:
    """Fill dead final-turn executable holes from a contiguous sale-only suffix.

    Kaggriculture's runtime defines ``episodeSteps - 2`` as the final actionable
    step and its deadline fallback liquidates visible shed stock there.  A SELL
    row beyond ``maxMarketOrdersPerTurn`` can therefore never execute if it stays
    in the suffix.  On that one step only, compact a contiguous sale-only region
    across the executable boundary so positive sales occupy known empty slots
    first.

    This deliberately declines every economic, input, malformed or unknown row;
    it never crosses HIRE/BUY orders or operating-input sales, preserves relative
    positive-sale order and list length, and is an identity at every other step.
    """
    if (not isinstance(orders, list) or not isinstance(observation, Mapping)
            or not isinstance(configuration, Mapping) or end <= 0 or end >= len(orders)):
        return orders
    step = observation.get('step')
    episode_steps = configuration.get('episodeSteps', 720)
    if (isinstance(step, bool) or not isinstance(step, int)
            or isinstance(episode_steps, bool) or not isinstance(episode_steps, int)
            or episode_steps < 2 or step != episode_steps - 2):
        return orders

    prefix_kinds = [_sale_only_terminal_row(order) for order in orders[:end]]
    if any(kind is None for kind in prefix_kinds):
        return orders
    holes = sum(kind == 0 for kind in prefix_kinds)
    if holes == 0:
        return orders

    scan = end
    promoted = 0
    while scan < len(orders) and promoted < holes:
        kind = _sale_only_terminal_row(orders[scan])
        if kind is None:
            break
        promoted += int(kind == 1)
        scan += 1
    if promoted == 0:
        return orders

    region = orders[:scan]
    kinds = [_sale_only_terminal_row(order) for order in region]
    positive = [order for order, kind in zip(region, kinds) if kind == 1]
    empty = [order for order, kind in zip(region, kinds) if kind == 0]
    candidate = positive + empty + orders[scan:]
    return candidate if candidate != orders else orders


def compact_sale_only_prefix(orders: list, end: int, market: Mapping,
                             configuration: Mapping, quote: PriceFunction) -> list:
    """Move sales across known empty slots in a wholly sale-only prefix.

    Relative positive-sale order, quantities, row length and the non-executable
    suffix stay intact. Buyable operating inputs and every economic/unknown
    order decline compaction. This is a current-turn ordering rule: it does not
    project future purchases, crops, or opponent policy responses.

    With no intra-market town consumption or purchases of these goods, moving
    an own sale earlier crosses only rival sales. A nonincreasing price curve
    weakly improves the changed commodity's own-minus-rival sale receipts,
    including paired quotes and the floor. This is not a full-game guarantee.
    """
    prefix = orders[:end]; positive = []; empty = []; totals = {}
    cfg_capacity = configuration.get('shedCapacity', 100)
    if isinstance(cfg_capacity, bool) or cfg_capacity != 100:
        return orders
    for order in prefix:
        if order == []:
            empty.append(order); continue
        quantity = _engine_sell_quantity(order)
        if quantity is None:
            return orders
        item = order[1]
        if not isinstance(item, str) or item not in PRODUCTS or item not in SALE_ONLY_GOODS:
            return orders
        positive.append(order); totals[item] = totals.get(item, 0) + quantity
    candidate = positive + empty
    if not positive or not empty or candidate == prefix or sum(totals.values()) > cfg_capacity:
        return orders
    prices = market.get('prices', {}); inventories = market.get('inventory', {})
    params = market.get('params')
    if (not isinstance(prices, Mapping) or not isinstance(inventories, Mapping)
            or (params is not None and not isinstance(params, Mapping))):
        return orders
    exposed = False
    try:
        for item, quantity in totals.items():
            inventory = inventories.get(item)
            if isinstance(inventory, bool) or not isinstance(inventory, int):
                return orders
            visible = prices.get(item)
            if (isinstance(visible, bool) or not isinstance(visible, (int, float))
                    or not math.isfinite(visible) or visible < 1):
                return orders
            curve = [quote(item, inventory + k, params)
                     for k in range(quantity + cfg_capacity + 1)]
            if any(isinstance(p, bool) or not isinstance(p, (int, float))
                   or not math.isfinite(p) or p < 1 for p in curve):
                return orders
            if curve[0] != visible or any(a < b for a, b in zip(curve, curve[1:])):
                return orders
            exposed |= curve[0] > curve[-1]
    except (ArithmeticError, LookupError, TypeError, ValueError):
        return orders
    if not exposed:
        return orders
    return candidate + orders[end:]


def lot_pressure(order: Any, market: Mapping, quote: PriceFunction,
                 rival_quantity: Any = _UNSET_RIVAL_QUANTITY) -> float | None:
    """Return public-flow delay loss, or None when the order is an opaque barrier.

    For own requested quantity ``n`` at public inventory ``I``, compare the own
    receipt now against the same own lot after ``rival_quantity`` public units.
    When the argument is omitted, retain the historical same-sized ``n`` rival
    lot exactly as the fallback/proxy stress. A supplied zero is real zero-flow.
    Any explicitly supplied malformed value, including ``None``, is a barrier;
    omission and malformed public evidence are intentionally distinct states.
    Supplied quantities are public scenario inputs, never inferred private stock
    or future sales.

    Current quote consistency is required. Above bounded scoring limits, retain
    the order in place instead of silently approximating either quantity.
    """
    prices, inventory = market.get('prices', {}), market.get('inventory', {})
    if not isinstance(prices, Mapping) or not isinstance(inventory, Mapping):
        return None
    visible = _quote(order, prices)
    if visible is None:
        return None
    item, n = order[1], int(order[2])
    if n > MAX_SCORING_UNITS:
        return None
    if rival_quantity is _UNSET_RIVAL_QUANTITY:
        rival_n = n
    else:
        if (isinstance(rival_quantity, bool) or not isinstance(rival_quantity, int)
                or rival_quantity < 0 or rival_quantity > MAX_SCORING_UNITS):
            return None
        rival_n = rival_quantity
    stock = inventory.get(item)
    if isinstance(stock, bool) or not isinstance(stock, int):
        return None
    params = market.get('params')
    if params is not None and not isinstance(params, Mapping):
        return None

    def checked(at: int) -> float:
        value = quote(item, at, params)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('non-numeric public quote')
        if not math.isfinite(value) or value < 1:
            raise ValueError('non-finite or below-floor public quote')
        return float(value)

    try:
        if checked(stock) != visible:
            return None
        ahead = sum(checked(stock + k) for k in range(n))
        delayed = sum(checked(stock + rival_n + k) for k in range(n))
    except (ArithmeticError, LookupError, TypeError, ValueError):
        return None
    # Negative deterioration is not urgency. Equal scores keep parent order.
    return max(0., ahead - delayed)


def transform(action: dict, observation: Mapping,
              configuration: Mapping | None = None, *, quote: PriceFunction,
              rival_supply: Mapping[str, int] | None = None) -> dict:
    """Sort contiguous supported SELL lots by public rival-flow delay exposure.

    ``rival_supply`` is an optional product->public-quantity scenario. Missing
    product keys retain the historical same-sized proxy for that product; an
    explicit zero means no rival flow. Present malformed values (including
    ``None``) are barriers, so ambiguity cannot silently become proxy evidence.

    Preserve all orders, quantities, duplicate lots, economic barriers,
    executable-prefix boundaries and unit instructions. Known empty slots can
    move only inside a wholly eligible sale-only prefix, except that the final
    actionable step may pull sale-only rows across the executable boundary into
    otherwise dead holes. Economic feedback can still change later parent
    choices; this is not a global optimality claim.
    """
    if not isinstance(action, dict):
        raise ValueError('parent policy must return an action object')
    result = copy.deepcopy(action)
    # The pinned engine treats a non-list market container as an empty queue.
    # Pressure priority is an optional market transform, so match that no-op
    # boundary instead of converting engine-inert parent bytes into an exception.
    if not isinstance(action.get('market', []), list):
        return result
    market = observation.get('market', {}) if isinstance(observation, Mapping) else {}
    if not isinstance(market, Mapping):
        return result
    if rival_supply is not None and not isinstance(rival_supply, Mapping):
        return result
    cfg = configuration if isinstance(configuration, Mapping) else {}
    try:
        limit = max(1, int(cfg.get('maxMarketOrdersPerTurn', 10)))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('invalid maxMarketOrdersPerTurn') from exc
    orders = result.get('market', [])
    end = min(len(orders), limit)
    if end > MAX_SCORING_ORDERS:
        return result
    orders = promote_terminal_sale_only_suffix(orders, end, observation, cfg)
    result['market'] = orders

    def supplied_quantity(order: Any) -> Any:
        if rival_supply is None or not isinstance(order, list) or len(order) < 3:
            return _UNSET_RIVAL_QUANTITY
        item = order[1]
        # Lookup only the inherited SELL product grammar. Unhashable or unknown
        # items stay unset so _quote/lot_pressure remain the barrier authority.
        if not isinstance(item, str) or item not in PRODUCTS:
            return _UNSET_RIVAL_QUANTITY
        try:
            if item not in rival_supply:
                return _UNSET_RIVAL_QUANTITY
            return rival_supply[item]
        except TypeError:
            return _UNSET_RIVAL_QUANTITY

    scores = [lot_pressure(order, market, quote, supplied_quantity(order))
              for order in orders[:end]]
    start = 0
    while start < end:
        if scores[start] is None:
            start += 1
            continue
        stop = start + 1
        while stop < end and scores[stop] is not None:
            stop += 1
        ranked = sorted(zip(orders[start:stop], scores[start:stop]), key=lambda p: -p[1])
        orders[start:stop] = [order for order, _ in ranked]
        start = stop
    result['market'] = compact_sale_only_prefix(orders, end, market, cfg, quote)

    # The V5 close-game objective is an opt-in refinement of this already-final
    # SELL boundary. Keep the dependency lazy so standalone LARK source tests
    # remain self-contained when the V5 runtime module is not on sys.path.
    raw_mode = cfg.get('titanCloseGameSaleRisk', 'legacy')
    mode = raw_mode.strip().lower() if isinstance(raw_mode, str) else 'legacy'
    if mode != 'legacy':
        try:
            from close_game_sale_risk import transform as close_game_transform
        except ModuleNotFoundError:
            return result
        result = close_game_transform(result, observation, cfg, quote=quote)
    return result


def actor_class(base: type, quote: PriceFunction) -> type:
    """Compose with existing process-isolated Actor; use |supply-pressure.

    The price callback operates only on the public inventory and market params
    passed by transform. It must not read the evolving engine state or rivals.
    Parent RPC plus transform share the original supplied action deadline.
    """
    class PressurePriorityActor(base):
        def __init__(self, spec: str, *args: Any, **kwargs: Any):
            suffix = '|supply-pressure'
            self.pressure_priority = spec.endswith(suffix)
            parent = spec[:-len(suffix)] if self.pressure_priority else spec
            super().__init__(parent, *args, **kwargs)
            self.stats['pressure_priority_enabled'] = self.pressure_priority
            self.stats['pressure_priority_changed_turns'] = 0
            self.stats['pressure_priority_transform_seconds'] = []
            self.stats['pressure_priority_total_seconds'] = []

        def act(self, observation: dict, configuration: Any, timeout: float):
            entered = time.perf_counter()
            response = super().act(observation, configuration, timeout)
            if not self.pressure_priority or response.get('kind') != 'action':
                return response
            started = time.perf_counter()
            result = transform(response['action'], observation, configuration, quote=quote)
            duration = time.perf_counter() - started
            self.stats['pressure_priority_transform_seconds'].append(duration)
            if result != response['action']:
                self.stats['pressure_priority_changed_turns'] += 1
            total = time.perf_counter() - entered
            self.stats['pressure_priority_total_seconds'].append(total)
            if total > timeout:
                return {'kind': 'timeout', 'phase': 'pressure_priority',
                        'error': 'parent RPC plus transform exceeded the supplied action deadline'}
            return dict(response, action=result)

    return PressurePriorityActor

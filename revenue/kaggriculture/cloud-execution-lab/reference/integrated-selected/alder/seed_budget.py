# SPDX-License-Identifier: Apache-2.0
"""Bound purchases by all remaining own-route planting requests.

This component is for the intact frozen Arlene/SELL routes, not arbitrary route
rewriters. Counting every PLANT request (including future no-ops) and taking the
largest suffix count over prefix-compatible routes preserves a conservative stock budget.
It does not read the rival, replay actions, prices, hidden seeds, or future draws.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path
from types import MappingProxyType
import marshal

try:
    from plant_suffix import immutable_plant_suffixes
except ModuleNotFoundError:
    # Canonical archives place the helper at runtime root. Direct source-tree
    # consumers instead resolve the exact landed sibling without requiring a
    # caller-specific PYTHONPATH.
    source = Path(__file__).resolve().parents[4]/'cloud-runtime-pulse'/'plant_suffix.py'
    spec = importlib.util.spec_from_file_location('_titan_plant_suffix', source)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise ImportError(f'cannot load plant suffix helper from {source}')
    spec.loader.exec_module(module)
    immutable_plant_suffixes = module.immutable_plant_suffixes

# Process-local, bounded, content-keyed; never deserialize external input.
_DERIVED_CACHE = {}
_CACHE_LIMIT = 4
_CROPS = ('WHEAT', 'CARROT', 'TOMATO', 'STRAWBERRY', 'MELON')


def _derive(routes):
    suffixes = {}
    prefix_lengths = {}
    for name, route in routes.items():
        for other, candidate in routes.items():
            common = 0
            for a, b in zip(route, candidate):
                if a != b:
                    break
                common += 1
            prefix_lengths[name, other] = common
    for name, route in routes.items():
        suffixes[name] = immutable_plant_suffixes(route)
    return MappingProxyType(suffixes), MappingProxyType(prefix_lengths)


def _derived(routes):
    # marshal is only a local lossless builtin-content encoding, not a persisted
    # format or object identity key. Lists/tuples and every full action field
    # remain distinct. Version 2 omits reference-count-dependent sharing tags.
    # Unsupported object types take the uncached path.
    try:
        key = marshal.dumps(routes, 2)
    except (ValueError, TypeError):
        return _derive(routes)
    cached = _DERIVED_CACHE.get(key)
    if cached is not None:
        return cached
    result = _derive(routes)
    # Publish only after every suffix and prefix has completed and is immutable.
    if len(_DERIVED_CACHE) >= _CACHE_LIMIT:
        _DERIVED_CACHE.pop(next(iter(_DERIVED_CACHE)))
    _DERIVED_CACHE[key] = result
    return result


class SeedBudget:
    def __init__(self, routes):
        self.suffixes, self.prefix_lengths = _derived(routes)
        self.events = []

    def remaining(self, crop, after_step, current):
        return max((s[min(max(0, after_step + 1), len(s) - 1)].get(crop, 0)
                    for name, s in self.suffixes.items()
                    if name == current or self.prefix_lengths[current, name] > after_step), default=0)

    def apply(self, action, post_unit_seeds, step, current, max_orders=10, *, extra_requests=None):
        result = deepcopy(action)
        market = result.get('market', [])
        # Match the engine's queue boundary: a non-list market is ignored. This
        # reducer is not an action parser and must not turn malformed parent
        # bytes into an exception while deciding whether a valid seed buy is
        # redundant.
        if not isinstance(market, list):
            return result
        maximum = max(1, int(max_orders))
        stock = dict(post_unit_seeds)
        for slot, order in enumerate(market[:maximum]):
            # Official _parse_order() requires a list with at least three
            # fields. Unknown crops are later rejected by _process_market and
            # therefore remain inert here rather than being rewritten.
            if (not isinstance(order, list) or len(order) < 3
                    or order[0] != 'BUY_SEED' or order[1] not in _CROPS):
                continue
            crop = order[1]
            try:
                requested = int(order[2])
            except (TypeError, ValueError):
                continue
            if requested <= 0:
                continue
            # Route recovery adds only its explicit, still-future PLANT request.
            # Keep the original branch-compatible bound instead of deriving a
            # new prefix table from temporarily patched actor rows.
            bound = self.remaining(crop, step, current) + int((extra_requests or {}).get(crop,0))
            retained = min(requested, max(0, bound - int(stock.get(crop, 0))))
            if retained != requested:
                if retained:
                    # The engine ignores trailing fields, but downstream
                    # receipts may rely on their identity. Change only the
                    # executed quantity when pruning an otherwise valid row.
                    updated = list(order)
                    updated[2] = retained
                    result['market'][slot] = updated
                else:
                    result['market'][slot] = []
                self.events.append(dict(step=step, slot=slot, crop=crop,
                                        requested=requested, retained=retained,
                                        post_unit_stock=int(stock.get(crop, 0)),
                                        remaining_request_bound=bound))
            # If this buy is cash-limited, later buys at the same fixed price
            # cannot execute either unless intervening cash arrives. Reserving
            # its requested quantity can therefore suppress a later useful buy.
            # Do not assume fulfillment; later slots use observed stock alone.
        return result
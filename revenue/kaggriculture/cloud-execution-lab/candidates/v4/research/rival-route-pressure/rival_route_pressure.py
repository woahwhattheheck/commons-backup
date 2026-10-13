"""Public rival-production pressure evidence for inherited TITAN route branches.

Research-only.  This module does not select a route, mutate an action, inspect
private rival state, predict hidden episode RNG, or claim economic dominance.
It answers a narrower question: when one already-authored route tail requests
more future SELL units than another, what *publicly visible* rival standing
production and already-unlocked town demand coexist with that incremental load?

The output is designed as an admission/falsification input for the one existing
V4 route selector, not as a second controller.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any, Iterable, Mapping, Sequence

PRODUCTS = (
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
)
ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}

# Exact public shop catalog from the pinned official engine.  Only shops already
# present in observation.town.unlocked_shops are counted; future unlocks are
# intentionally unknown and never forecast here.
SHOPS = {
    "BAKERY": ("EGG", "WHEAT"),
    "PIZZA_SHOP": ("MILK", "TOMATO", "WHEAT"),
    "BRUNCH_SPOT": ("EGG", "WHEAT", "STRAWBERRY"),
    "YARN_STORE": ("WOOL",),
    "ICE_CREAM_SHOP": ("STRAWBERRY", "MILK", "WHEAT"),
    "PET_CAFE": ("CARROT",),
    "SMOOTHIE_SHOP": ("STRAWBERRY", "MILK"),
    "FARMERS_MARKET": ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY"),
}
TOWN_CENTER_PRODUCTS = frozenset(p for p in PRODUCTS if p != "FERTILIZER")


class UnsupportedEvidence(ValueError):
    """Raised when a supposedly authoritative public input cannot be parsed."""


def _strict_nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise UnsupportedEvidence(f"{label} must be a nonnegative integer")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise UnsupportedEvidence(f"{label} must be a positive integer")
    return value


def _market_limit(configuration: Mapping[str, Any]) -> int:
    raw = configuration.get("maxMarketOrdersPerTurn", 10)
    # The official interpreter uses max(1, int(...)); its JSON schema is integer.
    # Evidence code is stricter: malformed/bool input is not reinterpreted.
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise UnsupportedEvidence("maxMarketOrdersPerTurn must be an integer")
    return max(1, raw)


def _action_market(action: Any) -> list[Any]:
    if not isinstance(action, Mapping):
        raise UnsupportedEvidence("route action must be a mapping")
    market = action.get("market", [])
    if not isinstance(market, list):
        raise UnsupportedEvidence("route market must be a list")
    return market


def _sell_row(order: Any) -> tuple[str, int] | None:
    if order == []:
        return None
    if not isinstance(order, list) or not order:
        raise UnsupportedEvidence("market row must be a nonempty list or []")
    if order[0] != "SELL":
        return None
    if len(order) < 3:
        raise UnsupportedEvidence("SELL row must include product and quantity")
    item = order[1]
    if not isinstance(item, str) or item not in PRODUCTS:
        raise UnsupportedEvidence("SELL row has unsupported product")
    quantity = _strict_nonnegative_int(order[2], "SELL quantity")
    return item, quantity


def route_sell_signature(
    route: Sequence[Any],
    start: int,
    end: int,
    *,
    max_orders: int = 10,
) -> dict[str, int]:
    """Count executable requested SELL units in ``route[start:end+1]``.

    The raw market cap is honored independently on every step.  Rows beyond the
    executable prefix do not become evidence.  The route is never mutated.
    """
    start = _strict_nonnegative_int(start, "start")
    end = _strict_nonnegative_int(end, "end")
    max_orders = _positive_int(max_orders, "max_orders")
    if end < start:
        raise UnsupportedEvidence("end precedes start")
    totals: defaultdict[str, int] = defaultdict(int)
    for step in range(start, end + 1):
        if step >= len(route):
            continue
        market = _action_market(route[step])
        for order in market[:max_orders]:
            parsed = _sell_row(order)
            if parsed is None:
                continue
            item, quantity = parsed
            totals[item] += quantity
    return dict(sorted(totals.items()))


def branch_sell_delta(
    incumbent: Sequence[Any],
    target: Sequence[Any],
    start: int,
    end: int,
    *,
    max_orders: int = 10,
) -> dict[str, int]:
    """Target requested SELL signature minus incumbent requested signature."""
    before = route_sell_signature(incumbent, start, end, max_orders=max_orders)
    after = route_sell_signature(target, start, end, max_orders=max_orders)
    return {
        item: after.get(item, 0) - before.get(item, 0)
        for item in sorted(set(before) | set(after))
        if after.get(item, 0) != before.get(item, 0)
    }


def visible_rival_signal(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Extract exact public standing yield and source counts from rival tiles.

    ``standing_yield`` is inventory physically visible on a rival crop/animal
    tile now.  It is *not* claimed to be in the rival shed and is not assumed to
    be sold.  ``productive_sources`` counts public producer tiles separately so
    downstream work may distinguish current units from structural capacity.
    """
    if not isinstance(observation, Mapping):
        raise UnsupportedEvidence("observation must be a mapping")
    player = observation.get("player")
    if isinstance(player, bool) or player not in (0, 1):
        raise UnsupportedEvidence("player must be 0 or 1")
    farms = observation.get("farms")
    if not isinstance(farms, (list, tuple)) or len(farms) != 2:
        raise UnsupportedEvidence("farms must contain two public farms")
    rival = farms[1 - int(player)]
    if not isinstance(rival, Mapping) or not isinstance(rival.get("tiles"), list):
        raise UnsupportedEvidence("rival public tiles missing")

    standing: defaultdict[str, int] = defaultdict(int)
    sources: defaultdict[str, int] = defaultdict(int)
    fertilizer_ready = 0
    for row in rival["tiles"]:
        if not isinstance(row, list):
            raise UnsupportedEvidence("rival tile row must be a list")
        for tile in row:
            if tile is None or tile == "LOCKED":
                continue
            if not isinstance(tile, Mapping):
                raise UnsupportedEvidence("unsupported rival tile value")
            product: str | None = None
            if tile.get("kind") == "PLANT":
                crop = tile.get("crop")
                if isinstance(crop, str) and crop in PRODUCTS:
                    product = crop
            elif isinstance(tile.get("animal"), str):
                product = ANIMAL_PRODUCT.get(tile["animal"])
            if product is not None:
                sources[product] += 1
                units = _strict_nonnegative_int(tile.get("yield_units", 0), "yield_units")
                standing[product] += units
            # FERTILIZER is public only as a collectable-on-tile flag here.  Do
            # not promote that flag into sold units or private shed inventory.
            if tile.get("fertilizer_available") is True:
                fertilizer_ready += 1

    return {
        "standing_yield": dict(sorted(standing.items())),
        "productive_sources": dict(sorted(sources.items())),
        "collectable_fertilizer_tiles": fertilizer_ready,
    }


def known_town_absorption(
    item: str,
    start: int,
    end: int,
    observation: Mapping[str, Any],
    configuration: Mapping[str, Any],
    *,
    shops_catalog: Mapping[str, Sequence[str]] = SHOPS,
) -> int:
    """Exact future drain from *already unlocked* public shops + town center.

    No future shop unlock is guessed.  This is deliberately a lower-information
    schedule than the engine's hidden-seed future, and reports only what current
    public state makes deterministic.
    """
    if item not in PRODUCTS:
        raise UnsupportedEvidence("unknown product")
    start = _strict_nonnegative_int(start, "start")
    end = _strict_nonnegative_int(end, "end")
    if end < start:
        raise UnsupportedEvidence("end precedes start")
    if not isinstance(observation, Mapping) or not isinstance(configuration, Mapping):
        raise UnsupportedEvidence("observation/configuration must be mappings")
    town = observation.get("town", {})
    shops = town.get("unlocked_shops", []) if isinstance(town, Mapping) else None
    if not isinstance(shops, list) or not all(isinstance(name, str) for name in shops):
        raise UnsupportedEvidence("unlocked_shops must be a string list")
    shop_interval = _positive_int(
        configuration.get("townShopSellInterval", 4), "townShopSellInterval")
    center_interval = _positive_int(
        configuration.get("townCenterSellInterval", 24), "townCenterSellInterval")
    total = 0
    for step in range(start, end + 1):
        if step % shop_interval == 0:
            for shop in shops:
                products = shops_catalog.get(shop)
                if products is None:
                    raise UnsupportedEvidence(f"unknown unlocked shop: {shop}")
                if item in products:
                    total += 2 if len(products) == 1 else 1
        if item in TOWN_CENTER_PRODUCTS and step % center_interval == 0:
            total += 1
    return total


def route_pressure_report(
    routes: Mapping[str, Sequence[Any]],
    incumbent: str,
    target: str,
    observation: Mapping[str, Any],
    configuration: Mapping[str, Any],
    *,
    start: int,
    horizon: int = 72,
) -> dict[str, Any]:
    """Create public evidence for one inherited route transition.

    The report has no ``allow``/``deny``/``choose`` bit.  A positive
    ``public_pressure_units`` means only that incremental requested own SELL
    units plus visible rival standing yield exceed deterministic drain from
    shops already unlocked in the observation over this bounded window.
    """
    if not isinstance(routes, Mapping) or incumbent not in routes or target not in routes:
        raise UnsupportedEvidence("incumbent/target route missing")
    start = _strict_nonnegative_int(start, "start")
    horizon = _positive_int(horizon, "horizon")
    max_orders = _market_limit(configuration)
    end = start + horizon - 1
    delta = branch_sell_delta(
        routes[incumbent], routes[target], start, end, max_orders=max_orders)
    rival = visible_rival_signal(observation)
    rows = []
    for item, added in sorted((p, q) for p, q in delta.items() if q > 0):
        standing = int(rival["standing_yield"].get(item, 0))
        demand = known_town_absorption(item, start, end, observation, configuration)
        own_only_pressure = max(0, added - demand)
        public_pressure = max(0, added + standing - demand)
        rows.append({
            "product": item,
            "incremental_target_sell_units": added,
            "visible_rival_standing_yield": standing,
            "visible_rival_productive_sources": int(
                rival["productive_sources"].get(item, 0)),
            "known_current_shop_absorption": demand,
            "own_only_pressure_units": own_only_pressure,
            "public_pressure_units": public_pressure,
            "rival_exacerbated": public_pressure > own_only_pressure,
        })
    return {
        "schema": "titan-v4-public-rival-route-pressure-v1",
        "research_only": True,
        "decision_authority": False,
        "incumbent": incumbent,
        "target": target,
        "start": start,
        "end": end,
        "max_market_orders_per_turn": max_orders,
        "sell_delta": delta,
        "public_rival_signal": rival,
        "incremental_sell_rows": rows,
        "has_public_pressure_witness": any(r["public_pressure_units"] > 0 for r in rows),
        "limitations": [
            "visible rival yield is not rival private inventory and is not assumed sold",
            "future hidden-seed shop unlocks are not forecast",
            "requested route SELL units are not claimed filled",
            "this report does not select or veto a route",
        ],
    }


def branch_catalog(
    routes: Mapping[str, Sequence[Any]],
    decisions: Iterable[Sequence[Any]],
    *,
    horizon: int = 72,
    max_orders: int = 10,
) -> list[dict[str, Any]]:
    """Compare every inherited route against every authored branch target.

    This deliberately covers all possible incumbent tails instead of assuming a
    single branch history.  It is source structure evidence, not activation.
    """
    horizon = _positive_int(horizon, "horizon")
    max_orders = _positive_int(max_orders, "max_orders")
    names = sorted(routes)
    rows: list[dict[str, Any]] = []
    for decision in decisions:
        if not isinstance(decision, (list, tuple)) or len(decision) != 4:
            raise UnsupportedEvidence("decision must be (turn, feature, threshold, target)")
        turn, feature, threshold, target = decision
        turn = _strict_nonnegative_int(turn, "decision turn")
        if not isinstance(feature, str) or not isinstance(target, str) or target not in routes:
            raise UnsupportedEvidence("decision feature/target invalid")
        end = turn + horizon - 1
        for incumbent in names:
            if incumbent == target:
                continue
            delta = branch_sell_delta(
                routes[incumbent], routes[target], turn, end, max_orders=max_orders)
            rows.append({
                "turn": turn,
                "feature": feature,
                "threshold": deepcopy(threshold),
                "incumbent": incumbent,
                "target": target,
                "end": end,
                "sell_delta": delta,
                "incremental_sell_products": sorted(k for k, v in delta.items() if v > 0),
            })
    return rows

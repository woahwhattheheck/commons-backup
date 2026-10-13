"""Gemini-lineage public pressure evidence folded into V4 PARALLAX.

Research-only. This module preserves the useful public-state observations from
Gemini G01 O01/shop-arbitrage without reviving its gameplay mutations or its
1.5x absorption heuristic. It emits independent, continuous evidence that may
be consumed by the existing V4 research/evaluation lanes.

It never selects a route, buys land, deletes a SELL, mutates an action, reads
rival private inventory, predicts hidden shop RNG, or overrides engine
absorption.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

import rival_route_pressure as R


SCHEMA = "titan-v4-gemini-public-pressure-v1"
DEFAULT_EARLY_STEP_MAX = 144
DEFAULT_DUMP_THRESHOLD = 15.0
DEFAULT_HORIZON = 24
QUADRANT_ORDER = ("NW", "NE", "SW", "SE")


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise R.UnsupportedEvidence(f"{label} must be a nonnegative integer")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise R.UnsupportedEvidence(f"{label} must be a positive integer")
    return value


def _finite_nonnegative_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise R.UnsupportedEvidence(f"{label} must be a finite nonnegative number")
    out = float(value)
    if not math.isfinite(out) or out < 0:
        raise R.UnsupportedEvidence(f"{label} must be a finite nonnegative number")
    return out


def _public_farms(observation: Mapping[str, Any]) -> tuple[int, Mapping[str, Any], Mapping[str, Any]]:
    if not isinstance(observation, Mapping):
        raise R.UnsupportedEvidence("observation must be a mapping")
    player = observation.get("player")
    if isinstance(player, bool) or player not in (0, 1):
        raise R.UnsupportedEvidence("player must be 0 or 1")
    farms = observation.get("farms")
    if not isinstance(farms, (list, tuple)) or len(farms) != 2:
        raise R.UnsupportedEvidence("farms must contain two public farms")
    own = farms[int(player)]
    rival = farms[1 - int(player)]
    if not isinstance(own, Mapping) or not isinstance(rival, Mapping):
        raise R.UnsupportedEvidence("public farms must be mappings")
    return int(player), own, rival


def _quadrants(farm: Mapping[str, Any], label: str) -> tuple[str, ...] | None:
    raw = farm.get("unlocked_quadrants")
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or not all(isinstance(q, str) and q for q in raw):
        raise R.UnsupportedEvidence(f"{label}.unlocked_quadrants must be a string sequence")
    quadrants = tuple(raw)
    if not quadrants or quadrants != QUADRANT_ORDER[: len(quadrants)]:
        raise R.UnsupportedEvidence(
            f"{label}.unlocked_quadrants must be a reachable prefix of {QUADRANT_ORDER!r}")
    return quadrants


def _price_map(observation: Mapping[str, Any]) -> dict[str, float]:
    market = observation.get("market", {})
    if not isinstance(market, Mapping):
        raise R.UnsupportedEvidence("market must be a mapping")
    prices = market.get("prices", {})
    if not isinstance(prices, Mapping):
        raise R.UnsupportedEvidence("market.prices must be a mapping")
    out: dict[str, float] = {}
    for item in R.PRODUCTS:
        if item in prices:
            out[item] = _finite_nonnegative_number(prices[item], f"price[{item}]")
    return out


def _previous_price_map(
    previous_prices: Mapping[str, Any] | None,
    *,
    current_step: int,
    previous_step: int | None,
) -> dict[str, float]:
    """Authenticate a price snapshot as the immediately preceding callback.

    A bare/stale price dictionary is not temporal evidence. The former API
    could mint a Gemini dump witness by pairing a current observation with any
    old mapping. Price-drop evidence now exists only when the caller also binds
    that mapping to exactly ``current_step - 1``.
    """
    if previous_prices is None:
        if previous_step is not None:
            raise R.UnsupportedEvidence("previous_step requires previous_prices")
        return {}
    if not isinstance(previous_prices, Mapping):
        raise R.UnsupportedEvidence("previous_prices must be a mapping or None")
    if previous_step is None:
        raise R.UnsupportedEvidence("previous_prices requires adjacent previous_step")
    prior_step = _nonnegative_int(previous_step, "previous_step")
    if current_step == 0 or prior_step != current_step - 1:
        raise R.UnsupportedEvidence("previous price snapshot must be from step-1")
    out: dict[str, float] = {}
    for item in R.PRODUCTS:
        if item in previous_prices:
            out[item] = _finite_nonnegative_number(
                previous_prices[item], f"previous_price[{item}]")
    return out


def public_pressure_profile(
    observation: Mapping[str, Any],
    configuration: Mapping[str, Any],
    previous_prices: Mapping[str, Any] | None = None,
    *,
    previous_step: int | None = None,
    horizon: int = DEFAULT_HORIZON,
) -> dict[str, Any]:
    """Return bounded public evidence descended from Gemini O01/shop-arb.

    The former mutually-exclusive archetype is decomposed into independent
    facts. An early-expansion witness and one or more item-level price-drop
    witnesses can coexist. Current shop demand is reported through PARALLAX's
    exact known-town drain rather than multiplying engine absorption.

    Missing public ``unlocked_quadrants`` does not poison price/town evidence;
    expansion evidence is explicitly marked unavailable. Malformed present
    values fail closed. A price-drop witness additionally requires a snapshot
    authenticated to the immediately preceding executable callback. Named
    Gemini witnesses use the recovered-source canonical boundaries
    ``step <= 144`` and ``price_drop >= 15.0``; callers cannot redefine them.
    """
    if not isinstance(configuration, Mapping):
        raise R.UnsupportedEvidence("configuration must be a mapping")
    horizon = _positive_int(horizon, "horizon")
    early_step_max = DEFAULT_EARLY_STEP_MAX
    threshold = DEFAULT_DUMP_THRESHOLD

    _, own, rival_farm = _public_farms(observation)
    step = _nonnegative_int(observation.get("step"), "step")
    episode_steps = _positive_int(configuration.get("episodeSteps", 720), "episodeSteps")
    if episode_steps < 2:
        raise R.UnsupportedEvidence("episodeSteps must permit an action callback")
    last_callback = episode_steps - 2
    if step > last_callback:
        raise R.UnsupportedEvidence("step must be an executable callback")
    end = min(step + horizon - 1, last_callback)

    own_quadrants = _quadrants(own, "own")
    rival_quadrants = _quadrants(rival_farm, "rival")
    expansion_available = own_quadrants is not None and rival_quadrants is not None
    if expansion_available:
        rival_count = len(rival_quadrants)
        own_count = len(own_quadrants)
        expansion = {
            "available": True,
            "own_unlocked_quadrants": own_count,
            "rival_unlocked_quadrants": rival_count,
            "rival_quadrant_lead": rival_count - own_count,
            "gemini_early_expander_witness": step <= early_step_max and rival_count > 1,
            "rival_leads_own": rival_count > own_count,
        }
    else:
        expansion = {
            "available": False,
            "own_unlocked_quadrants": None,
            "rival_unlocked_quadrants": None,
            "rival_quadrant_lead": None,
            "gemini_early_expander_witness": False,
            "rival_leads_own": False,
        }

    current_prices = _price_map(observation)
    prior_prices = _previous_price_map(
        previous_prices,
        current_step=step,
        previous_step=previous_step,
    )
    rival_signal = R.visible_rival_signal(observation)

    rows: list[dict[str, Any]] = []
    for item in R.PRODUCTS:
        current = current_prices.get(item)
        prior = prior_prices.get(item)
        drop = None if current is None or prior is None else prior - current
        dump_witness = drop is not None and drop >= threshold
        known_drain = R.known_town_absorption(
            item, step, end, observation, configuration)
        rows.append({
            "product": item,
            "current_price": current,
            "previous_price": prior,
            "price_drop": drop,
            "gemini_dump_witness": dump_witness,
            "visible_rival_standing_yield": int(
                rival_signal["standing_yield"].get(item, 0)),
            "visible_rival_productive_sources": int(
                rival_signal["productive_sources"].get(item, 0)),
            "known_current_town_drain": known_drain,
            "has_known_current_town_drain": known_drain > 0,
        })

    dump_products = [row["product"] for row in rows if row["gemini_dump_witness"]]
    return {
        "schema": SCHEMA,
        "research_only": True,
        "decision_authority": False,
        "mutates_action": False,
        "overrides_engine_absorption": False,
        "step": step,
        "end": end,
        "last_executable_callback": last_callback,
        "previous_price_step": previous_step,
        "early_step_max": early_step_max,
        "dump_threshold": threshold,
        "expansion_evidence": expansion,
        "product_rows": rows,
        "dump_witness_products": dump_products,
        "has_dump_witness": bool(dump_products),
        "public_rival_signal": rival_signal,
        "lineage": {
            "gemini_o01": "public early-expansion and adjacent price-drop observations retained as evidence",
            "gemini_shop_arb": "1.5x absorption heuristic retired; exact current town drain retained",
            "e11_owner": "V4 donor/e11_rival_sell.py plus market-baseline/TOWN-SALE-DEFERRAL.md",
            "row_shed_owner": "V4 STRATUM/row-shed-sell-order lineage",
            "e20_owner": "V4 donor/e20_hire_guard.py executable-prefix repair",
        },
        "limitations": [
            "early expansion is a public witness, not a BUY_LAND instruction",
            "a one-callback price drop is a public witness, not proof that the rival caused it",
            "visible rival yield is not rival private inventory and is not assumed sold",
            "only already-unlocked town demand is counted; hidden future shop RNG is not forecast",
            "this report does not defer, delete, append, or reorder market actions",
        ],
    }

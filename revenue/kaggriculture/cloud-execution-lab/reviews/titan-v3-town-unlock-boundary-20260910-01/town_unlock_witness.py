#!/usr/bin/env python3
"""Exact arithmetic witness for a future town-shop unlock boundary.

This is an additive review artifact for TITAN V3 PR #12053.  It mirrors the
relevant constants and formulas from the pinned official Kaggriculture engine
Git blob 3c202c7ee921da239356789e266b694635103fc4.

The witness proves that replaying _town_consume() with only the *current*
``town["unlocked_shops"]`` list is insufficient when a protected funding
horizon crosses an end-of-day shop unlock.  It intentionally changes no TITAN
source, route, provider, game, or Kaggle state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
PRICE_FLOOR = 1
MAX_SHOP_INSTANCES = 8
SHOPS: dict[str, list[str]] = {
    "BAKERY": ["EGG", "WHEAT"],
    "PIZZA_SHOP": ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT": ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE": ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE": ["CARROT"],
    "SMOOTHIE_SHOP": ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}
WHEAT_PARAMS: dict[str, Any] = {
    "base": 25,
    "I0": 10_000,
    "T": 400,
    "below_func": "sqrt",
    "below_target": 0.80,
    "above_func": "log",
    "above_target": 0.20,
}


def _shape(func: str, x: float, threshold: float | None = None) -> float:
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "log10":
        return math.log10(1.0 + x)
    if func == "hinge":
        if not threshold or threshold <= 0:
            return x
        u = x / threshold
        return u + 8.0 * max(0.0, u - 1.0) ** 2
    return x


def wheat_price(inventory: int) -> int:
    """Mirror official ``market_price('WHEAT', inventory)`` exactly."""
    p = WHEAT_PARAMS
    base = p["base"]
    i0 = p["I0"]
    threshold = p["T"]
    if inventory < i0:
        func = p["below_func"]
        amplitude = p["below_target"] * base / _shape(func, threshold, threshold)
        price = base + amplitude * _shape(func, i0 - inventory, threshold)
    else:
        func = p["above_func"]
        amplitude = p["above_target"] * base / _shape(func, threshold, threshold)
        price = base - amplitude * _shape(func, inventory - i0, threshold)
    return max(PRICE_FLOOR, int(round(price)))


def next_shop(*, episode_seed: int, current_day: int, prior_rng_draws: int = 0) -> str:
    """Mirror the engine's end-of-day RNG and shop draw.

    The fixture uses a one-cell, fully occupied board for both players, so
    ``_spawn_weeds`` performs zero random draws before ``rng.choice``.
    """
    rng = random.Random((episode_seed * 1_000_003) ^ current_day)
    for _ in range(prior_rng_draws):
        rng.random()
    return rng.choice(sorted(SHOPS))


def build_receipt() -> dict[str, Any]:
    # Absolute timing.  At the end of step 71, current day 2 advances to day 3.
    start_step = 60
    unlock_after_step = 71
    first_new_shop_tick = 72
    buy_step = 73
    turns_per_day = 24
    shop_unlock_interval_days = 3
    shop_sell_interval_steps = 4
    center_sell_interval_steps = 1000
    episode_seed = 0

    assert unlock_after_step // turns_per_day == 2
    assert (unlock_after_step + 1) // turns_per_day == 3
    assert 3 % shop_unlock_interval_days == 0
    assert first_new_shop_tick % shop_sell_interval_steps == 0
    assert first_new_shop_tick % center_sell_interval_steps != 0

    drawn_shop = next_shop(episode_seed=episode_seed, current_day=2)
    assert drawn_shop == "BAKERY"
    assert "WHEAT" in SHOPS[drawn_shop]
    assert len(SHOPS[drawn_shop]) > 1  # multiplier is exactly one.

    initial_wheat_inventory = 9_999

    # A static-current-town replay sees no shops for the whole horizon.
    static_before_buy = initial_wheat_inventory
    static_post_buy = static_before_buy - 1
    static_buy_price = wheat_price(static_post_buy)

    # Official evolution unlocks BAKERY after step 71, then consumes one WHEAT
    # after the step-72 market stage.  BUY_PRODUCT at step 73 quotes post-buy.
    official_before_buy = initial_wheat_inventory - 1
    official_post_buy = official_before_buy - 1
    official_buy_price = wheat_price(official_post_buy)

    starting_cash = 26
    assert static_buy_price == 26
    assert official_buy_price == 27
    assert starting_cash >= static_buy_price
    assert starting_cash < official_buy_price

    # Any executed current one-unit product sale earns at least PRICE_FLOOR.
    current_sale_floor_receipt = PRICE_FLOOR
    assert starting_cash + current_sale_floor_receipt >= official_buy_price

    controls = {
        "horizon_ending_at_step_71": {
            "new_shop_consumptions": 0,
            "static_equals_official": True,
        },
        "already_at_max_shop_instances": {
            "shop_count": MAX_SHOP_INSTANCES,
            "unlock_occurs": False,
            "static_equals_official_for_unlock_effect": True,
        },
        "non_unlock_day": {
            "next_day": 4,
            "unlock_interval_days": shop_unlock_interval_days,
            "unlock_occurs": False,
        },
    }

    receipt: dict[str, Any] = {
        "claim": "TITAN-V3-FUNDING-TOWN-UNLOCK-BOUNDARY-REVIEW-20260910-01",
        "disposition": "STATIC_TOWN_SNAPSHOT_UNSAFE_ACROSS_UNLOCK_BOUNDARY",
        "official_engine_git_blob": ENGINE_GIT_BLOB,
        "fixture": {
            "episode_seed": episode_seed,
            "board": "one fully occupied tile per player; zero weed RNG draws",
            "start_step": start_step,
            "turns_per_day": turns_per_day,
            "town_shop_unlock_interval_days": shop_unlock_interval_days,
            "town_shop_sell_interval_steps": shop_sell_interval_steps,
            "town_center_sell_interval_steps": center_sell_interval_steps,
            "current_unlocked_shops": [],
            "initial_wheat_inventory": initial_wheat_inventory,
            "starting_cash": starting_cash,
            "current_sale": ["SELL", "MILK", 1],
            "future_buy": {"step": buy_step, "order": ["BUY_PRODUCT", "WHEAT", 1]},
            "stress_units": 0,
        },
        "official_transition": {
            "unlock_after_step": unlock_after_step,
            "new_day": 3,
            "drawn_shop": drawn_shop,
            "first_consumption_step": first_new_shop_tick,
            "wheat_units_consumed_by_new_shop": 1,
        },
        "static_current_town_projection": {
            "wheat_before_buy": static_before_buy,
            "wheat_post_buy_quote_inventory": static_post_buy,
            "buy_price": static_buy_price,
            "buy_fills_without_current_sale": True,
            "minimum_now": 0,
        },
        "official_dynamic_town_projection": {
            "wheat_before_buy": official_before_buy,
            "wheat_post_buy_quote_inventory": official_post_buy,
            "buy_price": official_buy_price,
            "buy_fills_without_current_sale": False,
            "buy_fills_with_one_current_sale_at_price_floor": True,
            "minimum_now": 1,
        },
        "controls": controls,
        "required_closure": [
            "prove every protected funding horizon ends before the next unresolved shop unlock",
            "or model the exact end-of-day RNG/shop-state evolution and all later town ticks",
            "or conservatively stress every product a possible newly unlocked shop can consume",
        ],
        "nonclaims": [
            "no canonical TITAN source/config/archive/pointer mutation",
            "no game, provider, Kaggle, submission, merge, or promotion action",
            "no verdict on PR implementation bytes until exact-head patch readback",
        ],
    }

    canonical_without_digest = json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    receipt["receipt_sha256"] = hashlib.sha256(canonical_without_digest).hexdigest()
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    receipt = build_receipt()
    rendered = json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if args.out is not None:
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

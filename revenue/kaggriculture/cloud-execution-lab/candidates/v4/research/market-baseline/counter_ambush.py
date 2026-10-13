#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""TITAN V4 COMEBACK: authenticated adversarial market counterfactuals.

Research only. No runtime action chooser. The Apex schedule is source-bound to
the exact public Apex V7 wrapper and reference-policy-bank identity used by the
canonical market-pressure source-custody packet.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
APEX_MAIN_SHA256 = "1f7cd5fb8a16585936d2562a3667f85bb6661688718ef58f73006de66148354a"
PRICE_FLOOR = 1

AUTHENTICATED_APEX_SELL_STEPS = {
    "MELON": (249,),
    "STRAWBERRY": (381, 403, 499, 500, 501),
    "FERTILIZER": (522,),
}
APEX_ANTI_CLONE = {
    "clone_window": (2, 10),
    "clone_min_opponent_hands": 3,
    "clone_min_opponent_structures": 1,
    "events": (
        {"steps": (249,), "item": "MELON", "min_shed": 6, "max_sell": 12},
        {"steps": (381,), "item": "STRAWBERRY", "min_shed": 6, "max_sell": 8},
        {"steps": (403,), "item": "STRAWBERRY", "min_shed": 6, "max_sell": 8},
        {"steps": (499, 500, 501), "item": "STRAWBERRY", "min_shed": 8, "max_sell": 8},
        {
            "steps": (522,),
            "item": "FERTILIZER",
            "min_shed": 18,
            "max_sell": 4,
            "quantity_rule": "min(fert - 16, 4)",
        },
    ),
}
SCHEDULE_AUTHENTICATED = True

MARKET = {
    "WHEAT": dict(base=25, I0=10000, T=400, below_func="sqrt", below_target=.80, above_func="log", above_target=.20),
    "STRAWBERRY": dict(base=120, I0=10000, T=100, below_func="sqrt", below_target=.70, above_func="linear", above_target=1.60),
    "MELON": dict(base=250, I0=10000, T=300, below_func="log", below_target=.20, above_func="sq", above_target=3.60),
    "FERTILIZER": dict(base=100, I0=10000, T=200, below_func="linear", below_target=.40, above_func="linear", above_target=.40),
}
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
TOWN_CENTER_PRODUCTS = {"WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL"}


def _git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise RuntimeError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise RuntimeError(f"non-finite JSON constant: {value}")


def verify_engine(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    actual = _git_blob(data)
    if actual != ENGINE_BLOB:
        raise RuntimeError(f"engine drift: expected {ENGINE_BLOB}, got {actual}")
    text = data.decode("utf-8")
    required = (
        'def _process_market',
        'Both players see the same pre-commit inventory for this unit.',
        'market_price(item, market["inventory"][item] - 1',
        'if price > 1:',
        'market["inventory"][item] -= 1',
        'if op == "FERTILIZE":',
        'day + 2',
        '(2 if fertilized else 1)',
        'def _town_consume',
    )
    missing = [needle for needle in required if needle not in text]
    if missing:
        raise RuntimeError(f"engine contract drift: {missing}")
    u = text.find("_apply_unit_action(")
    m = text.find("_process_market(state, env)")
    t = text.find("_town_consume(env, state, step)")
    if min(u, m, t) < 0 or not (u < m < t):
        raise RuntimeError("UNIT -> MARKET -> TOWN ordering drift")
    return {"engine_blob": actual, "unit_market_town_order": True}


def verify_apex_source(apex_path: Path, reference_manifest_path: Path) -> dict[str, str]:
    apex = apex_path.read_bytes()
    apex_sha = _sha256(apex)
    if apex_sha != APEX_MAIN_SHA256:
        raise RuntimeError(f"Apex source drift: expected {APEX_MAIN_SHA256}, got {apex_sha}")
    manifest = json.loads(
        reference_manifest_path.read_text(encoding="utf-8"),
        object_pairs_hook=_no_dupes,
        parse_constant=_reject_constant,
    )
    declared = (
        manifest.get("policies", {})
        .get("apex_v7", {})
        .get("files", {})
        .get("main.py")
    )
    if declared != APEX_MAIN_SHA256:
        raise RuntimeError(
            f"reference-policy-bank Apex declaration drift: expected {APEX_MAIN_SHA256}, got {declared!r}"
        )
    return {"apex_main_sha256": apex_sha, "reference_declared_apex_sha256": declared}


def _shape(name: str, x: float, T: float) -> float:
    x = max(0.0, x)
    if name == "linear": return x
    if name == "sq": return x * x
    if name == "sqrt": return math.sqrt(x)
    if name == "log": return math.log(1.0 + x)
    raise ValueError(name)


def market_price(item: str, inventory: int) -> int:
    p = MARKET[item]
    base, I0, T = p["base"], p["I0"], p["T"]
    if inventory < I0:
        fn = p["below_func"]
        amp = p["below_target"] * base / _shape(fn, T, T)
        value = base + amp * _shape(fn, I0 - inventory, T)
    else:
        fn = p["above_func"]
        amp = p["above_target"] * base / _shape(fn, T, T)
        value = base - amp * _shape(fn, inventory - I0, T)
    return max(PRICE_FLOOR, int(round(value)))


def sell_units(item: str, inventory: int, units: int) -> dict[str, Any]:
    gross, prices = 0, []
    for _ in range(units):
        price = market_price(item, inventory)
        gross += price
        prices.append(price)
        if price > PRICE_FLOOR:
            inventory += 1
    return {"gross": gross, "prices": prices, "ending_inventory": inventory}


def buy_product_units(item: str, inventory: int, units: int) -> dict[str, Any]:
    cost, prices = 0, []
    for _ in range(units):
        price = market_price(item, inventory - 1)
        cost += price
        prices.append(price)
        inventory -= 1
    return {"cost": cost, "prices": prices, "ending_inventory": inventory}


def town_drain(item: str, step: int, unlocked_shops: Iterable[str]) -> int:
    total = 0
    if step % 4 == 0:
        for shop in unlocked_shops:
            products = SHOPS[shop]
            if item in products:
                total += 2 if len(products) == 1 else 1
    if step % 24 == 0 and item in TOWN_CENTER_PRODUCTS:
        total += 1
    return total


def predump_counterfactual(*, item: str, starting_inventory: int, own_units: int,
                           rival_units: int, pre_step: int,
                           unlocked_shops: Iterable[str] = ()) -> dict[str, Any]:
    """Compare our t-1 sale against waiting until t+1 around a rival t sale."""
    shops = tuple(unlocked_shops)
    early = sell_units(item, starting_inventory, own_units)
    d0 = town_drain(item, pre_step, shops)
    inv = max(0, early["ending_inventory"] - d0)
    rival_after_early = sell_units(item, inv, rival_units)
    d1 = town_drain(item, pre_step + 1, shops)
    early_terminal = max(0, rival_after_early["ending_inventory"] - d1)

    base_inv = max(0, starting_inventory - d0)
    rival_baseline = sell_units(item, base_inv, rival_units)
    base_after_rival = max(0, rival_baseline["ending_inventory"] - d1)
    late = sell_units(item, base_after_rival, own_units)

    own_gain = early["gross"] - late["gross"]
    rival_suppression = rival_baseline["gross"] - rival_after_early["gross"]
    return {
        "item": item,
        "pre_step": pre_step,
        "town_drain_after_pre": d0,
        "town_drain_after_rival": d1,
        "own_early_gross": early["gross"],
        "own_late_gross": late["gross"],
        "own_timing_gain": own_gain,
        "rival_baseline_gross": rival_baseline["gross"],
        "rival_counter_gross": rival_after_early["gross"],
        "rival_suppression": rival_suppression,
        "gross_relative_margin_swing": own_gain + rival_suppression,
        "early_terminal_inventory": early_terminal,
        "decision_authority": False,
    }


def source_bonus_ceiling_per_fertilizer(crop: str) -> int:
    """Optimistic extra crop units from one 3-day fertilizer window."""
    return {"WHEAT": 2, "CARROT": 1, "MELON": 2, "TOMATO": 3, "STRAWBERRY": 2}[crop]


def earliest_fertilize_step(buy_step: int, movement_distance: int = 0) -> int:
    if buy_step < 0 or movement_distance < 0:
        raise ValueError("negative step/distance")
    return buy_step + 2 + movement_distance


def fertilizer_sponge(*, starting_inventory: int, rival_sell_units: int,
                       our_buy_units: int, target_crop: str = "WHEAT",
                       observed_crop_price: int | None = None,
                       buy_step: int = 523, movement_distance: int = 0) -> dict[str, Any]:
    dump = sell_units("FERTILIZER", starting_inventory, rival_sell_units)
    after = buy_product_units("FERTILIZER", dump["ending_inventory"], our_buy_units)
    baseline = buy_product_units("FERTILIZER", starting_inventory, our_buy_units)
    ceiling = source_bonus_ceiling_per_fertilizer(target_crop)
    avg_cost = after["cost"] / our_buy_units
    threshold = math.ceil(avg_cost / ceiling)
    out = {
        "rival_dump_gross": dump["gross"],
        "rival_market_units_added": dump["ending_inventory"] - starting_inventory,
        "our_buy_cost_after_dump": after["cost"],
        "our_buy_cost_without_dump": baseline["cost"],
        "opponent_created_purchase_discount": baseline["cost"] - after["cost"],
        "target_crop": target_crop,
        "source_bonus_ceiling_units_per_fertilizer": ceiling,
        "minimum_crop_sale_price_for_gross_ceiling_break_even": threshold,
        "earliest_best_case_fertilize_step": earliest_fertilize_step(buy_step, movement_distance),
        "decision_authority": False,
    }
    if observed_crop_price is not None:
        gross_ceiling = ceiling * our_buy_units * observed_crop_price
        out.update(observed_crop_price=observed_crop_price,
                   gross_crop_value_ceiling=gross_ceiling,
                   gross_ceiling_covers_fertilizer_cost=gross_ceiling >= after["cost"])
    return out


def sample_report() -> dict[str, Any]:
    strawberry_shops = ("BRUNCH_SPOT", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP", "FARMERS_MARKET") * 2
    return {
        "schema": "titan-v4-comeback-counter-ambush/v2",
        "authenticated_apex_schedule": AUTHENTICATED_APEX_SELL_STEPS,
        "apex_source_sha256": APEX_MAIN_SHA256,
        "schedule_authenticated": SCHEDULE_AUTHENTICATED,
        "apex_contract": APEX_ANTI_CLONE,
        "strawberry_380_source_real_max_shop_drain": predump_counterfactual(
            item="STRAWBERRY", starting_inventory=10000, own_units=8, rival_units=8,
            pre_step=380, unlocked_shops=strawberry_shops),
        "strawberry_402_source_real_no_shop_drain": predump_counterfactual(
            item="STRAWBERRY", starting_inventory=10000, own_units=8, rival_units=8,
            pre_step=402, unlocked_shops=()),
        "fert4_buy4_wheat_base": fertilizer_sponge(
            starting_inventory=10000, rival_sell_units=4, our_buy_units=4,
            target_crop="WHEAT", observed_crop_price=25),
        "fert_floor_control": fertilizer_sponge(
            starting_inventory=10493, rival_sell_units=4, our_buy_units=4,
            target_crop="WHEAT", observed_crop_price=25),
        "decision_authority": False,
    }


if __name__ == "__main__":
    print(json.dumps(sample_report(), indent=2, sort_keys=True))

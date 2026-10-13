#!/usr/bin/env python3
"""Verify the official engine's town-consumption contract without importing Kaggle.

This research verifier intentionally reads the pinned reference engine as data. It
keeps the result independent of the production TITAN runtime and makes the two
important rates explicit: shop *unlock* cadence and shop *consumption* cadence.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
LAB = HERE.parents[4]
ENGINE = LAB / "reference" / "engine" / "kaggriculture.py"
CONFIG = LAB / "reference" / "engine" / "kaggriculture.json"
EXPECTED_ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"


def _git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _literal_assignment(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing literal assignment: {name}")


def _function_source(source: str, tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            segment = ast.get_source_segment(source, node)
            if segment is None:
                raise AssertionError(f"cannot recover function source: {name}")
            return segment
    raise AssertionError(f"missing function: {name}")


def derive() -> dict[str, Any]:
    engine_bytes = ENGINE.read_bytes()
    actual_engine_blob = _git_blob_sha1(engine_bytes)
    assert actual_engine_blob == EXPECTED_ENGINE_BLOB, (
        actual_engine_blob,
        EXPECTED_ENGINE_BLOB,
    )
    source = engine_bytes.decode("utf-8")
    tree = ast.parse(source)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg = config["configuration"]

    shops = _literal_assignment(tree, "SHOPS")
    max_shops = int(_literal_assignment(tree, "MAX_SHOP_INSTANCES"))
    products = _literal_assignment(tree, "PRODUCTS")
    town_center_products = [item for item in products if item != "FERTILIZER"]

    town_consume = _function_source(source, tree, "_town_consume")
    end_of_day = _function_source(source, tree, "_end_of_day")

    # These are the semantic seams this correction is meant to freeze. Keeping
    # the checks source-facing prevents a copied local model from blessing itself.
    required_consume_fragments = (
        'get(cfg, "townShopSellInterval", 4)',
        'get(cfg, "townCenterSellInterval", 24)',
        'multiplier = 2 if len(products) == 1 else 1',
        'for shop_name in town.get("unlocked_shops", [])',
        'market["inventory"][item] -= multiplier',
        'market["inventory"][item] -= 1',
    )
    for fragment in required_consume_fragments:
        assert fragment in town_consume, fragment

    required_unlock_fragments = (
        'get(cfg, "townShopUnlockInterval", 3)',
        'next_day % shop_interval == 0',
        'len(town["unlocked_shops"]) < MAX_SHOP_INSTANCES',
        'rng.choice(sorted(SHOPS))',
    )
    for fragment in required_unlock_fragments:
        assert fragment in end_of_day, fragment

    turns_per_day = int(cfg["turnsPerDay"]["default"])
    shop_sell_interval = int(cfg["townShopSellInterval"]["default"])
    center_sell_interval = int(cfg["townCenterSellInterval"]["default"])
    shop_unlock_interval = int(cfg["townShopUnlockInterval"]["default"])
    assert turns_per_day % shop_sell_interval == 0
    assert turns_per_day % center_sell_interval == 0

    shop_ticks_per_day = turns_per_day // shop_sell_interval
    center_ticks_per_day = turns_per_day // center_sell_interval

    per_shop_tick: dict[str, dict[str, int]] = {}
    for shop_name, shop_products in shops.items():
        multiplier = 2 if len(shop_products) == 1 else 1
        per_shop_tick[shop_name] = {
            item: multiplier for item in shop_products
        }

    egg_shops = sorted(
        name for name, demand in per_shop_tick.items() if "EGG" in demand
    )
    doubled_shops = sorted(
        name
        for name, demand in per_shop_tick.items()
        if demand and next(iter(demand.values())) == 2
    )
    assert egg_shops == ["BAKERY", "BRUNCH_SPOT"]
    assert doubled_shops == ["PET_CAFE", "YARN_STORE"]
    assert all(per_shop_tick[name]["EGG"] == 1 for name in egg_shops)

    def max_daily_demand(item: str, unlocked_instances: int) -> int:
        best_per_tick = max(
            (demand.get(item, 0) for demand in per_shop_tick.values()),
            default=0,
        )
        center = center_ticks_per_day if item in town_center_products else 0
        return unlocked_instances * best_per_tick * shop_ticks_per_day + center

    max_at_cap = {
        item: max_daily_demand(item, max_shops) for item in products
    }
    # At the default 3-day unlock cadence, only two instances exist at the
    # start of either zero-indexed day 8 or colloquial/one-indexed day 8.
    instances_by_start_of_day8_zero_indexed = min(8 // shop_unlock_interval, max_shops)
    instances_by_start_of_day8_one_indexed = min(7 // shop_unlock_interval, max_shops)
    assert instances_by_start_of_day8_zero_indexed == 2
    assert instances_by_start_of_day8_one_indexed == 2

    egg_per_shop_per_day = per_shop_tick["BAKERY"]["EGG"] * shop_ticks_per_day
    egg_day8_upper_bound = max_daily_demand("EGG", 2)

    return {
        "engine_blob": actual_engine_blob,
        "defaults": {
            "turns_per_day": turns_per_day,
            "shop_unlock_interval_days": shop_unlock_interval,
            "shop_sell_interval_turns": shop_sell_interval,
            "town_center_sell_interval_turns": center_sell_interval,
            "shop_ticks_per_day": shop_ticks_per_day,
            "town_center_ticks_per_day": center_ticks_per_day,
            "max_shop_instances": max_shops,
        },
        "egg": {
            "consumer_shops": egg_shops,
            "multiplier_per_tick": 1,
            "per_shop_per_day": egg_per_shop_per_day,
            "max_instances_through_day8": 2,
            "day8_total_demand_upper_bound_including_center": egg_day8_upper_bound,
            "full_cap_total_demand_upper_bound_including_center": max_at_cap["EGG"],
        },
        "doubled_single_product_shops": doubled_shops,
        "max_daily_demand_at_eight_shop_cap_including_center": max_at_cap,
    }


def main() -> None:
    result = derive()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

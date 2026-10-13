#!/usr/bin/env python3
"""Source-exact reduced no-action town/market baseline for Kaggriculture.

This model copies only the official engine semantics reachable when both players
always PASS and submit no market orders. It intentionally models the shared RNG
consumption caused by weeds because weed draws occur before shop choice on each
end-of-day RNG stream and therefore change the unlocked-shop sequence.

Pinned engine blob: 3c202c7ee921da239356789e266b694635103fc4
Pinned spec blob:   b354d06b742fe48402513792253f1a5c29366b20
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from pathlib import Path

ENGINE_BLOB_SHA = "3c202c7ee921da239356789e266b694635103fc4"
SPEC_BLOB_SHA = "b354d06b742fe48402513792253f1a5c29366b20"
EPISODE_STEPS = 720
ACTION_STEPS = EPISODE_STEPS - 1  # framework's initialized observation + steps 0..718
TURNS_PER_DAY = 24
BOARD_SIZE = 10
WEED_SPAWN_CHANCE = 0.005
SHOP_UNLOCK_INTERVAL = 3
SHOP_SELL_INTERVAL = 4
CENTER_SELL_INTERVAL = 24
MAX_SHOP_INSTANCES = 8
MARKET_I0 = 10_000
PRICE_FLOOR = 1
HINGE_GAIN = 8.0

PRODUCTS = [
    "WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
    "EGG", "MILK", "WOOL", "FERTILIZER",
]
MARKET_PARAMS = {
    "WHEAT":      {"base": 25,  "I0": MARKET_I0, "T": 400, "below_func": "sqrt",  "below_target": 0.80, "above_func": "log",    "above_target": 0.20},
    "CARROT":     {"base": 35,  "I0": MARKET_I0, "T": 450, "below_func": "hinge", "below_target": 1.00, "above_func": "sqrt",   "above_target": 0.70},
    "TOMATO":     {"base": 60,  "I0": MARKET_I0, "T": 200, "below_func": "hinge", "below_target": 0.40, "above_func": "sqrt",   "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "I0": MARKET_I0, "T": 100, "below_func": "sqrt",  "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "I0": MARKET_I0, "T": 300, "below_func": "log",   "below_target": 0.20, "above_func": "sq",     "above_target": 3.60},
    "EGG":        {"base": 50,  "I0": MARKET_I0, "T": 332, "below_func": "hinge", "below_target": 0.40, "above_func": "log",    "above_target": 0.20},
    "MILK":       {"base": 160, "I0": MARKET_I0, "T": 122, "below_func": "sqrt",  "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "I0": MARKET_I0, "T": 105, "below_func": "log",   "below_target": 0.20, "above_func": "sq",     "above_target": 3.20},
    "FERTILIZER": {"base": 100, "I0": MARKET_I0, "T": 200, "below_func": "linear","below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}
SHOPS = {
    "BAKERY":         ["EGG", "WHEAT"],
    "PIZZA_SHOP":     ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT":    ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE":     ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE":       ["CARROT"],
    "SMOOTHIE_SHOP":  ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}
SORTED_SHOPS = sorted(SHOPS)
TOWN_CENTER_PRODUCTS = [p for p in PRODUCTS if p != "FERTILIZER"]


def _shape(func: str, x: float, T: float | None = None) -> float:
    x = max(0.0, x)
    if func == "linear": return x
    if func == "sq": return x * x
    if func == "sqrt": return math.sqrt(x)
    if func == "log": return math.log(1.0 + x)
    if func == "log10": return math.log10(1.0 + x)
    if func == "hinge":
        if not T or T <= 0:
            return x
        u = x / T
        return u + HINGE_GAIN * max(0.0, u - 1.0) ** 2
    return x


def market_price(item: str, inventory: int) -> int:
    p = MARKET_PARAMS[item]
    base, I0, T = p["base"], p["I0"], p["T"]
    if inventory < I0:
        f = p["below_func"]
        amp = p["below_target"] * base / _shape(f, T, T)
        value = base + amp * _shape(f, I0 - inventory, T)
    else:
        f = p["above_func"]
        amp = p["above_target"] * base / _shape(f, T, T)
        value = base - amp * _shape(f, inventory - I0, T)
    return max(PRICE_FLOOR, int(round(value)))


def simulate(seed: int) -> dict:
    """Run the exact reachable no-action market/town/RNG state for one seed."""
    inventory = {p: MARKET_I0 for p in PRODUCTS}
    prices = {p: MARKET_PARAMS[p]["base"] for p in PRODUCTS}
    shops: list[str] = []
    # Only NW is unlocked and no player action changes tiles.  Each farm begins
    # with 25 empty NW tiles; weeds persist, so future RNG draws skip them.
    empty_tiles = [25, 25]
    steps = []
    unlocks = []

    for step in range(ACTION_STEPS):  # 0..718, matching interpreter decisions
        if step % SHOP_SELL_INTERVAL == 0:
            for shop in shops:
                products = SHOPS[shop]
                mult = 2 if len(products) == 1 else 1
                for item in products:
                    inventory[item] -= mult
        if step % CENTER_SELL_INTERVAL == 0:
            for item in TOWN_CENTER_PRODUCTS:
                inventory[item] -= 1
        prices = {p: market_price(p, inventory[p]) for p in PRODUCTS}
        steps.append({
            "step": step,
            "day": step // TURNS_PER_DAY,
            "hour": step % TURNS_PER_DAY,
            "shop_count": len(shops),
            "inventory": dict(inventory),
            "prices": dict(prices),
        })

        if (step + 1) % TURNS_PER_DAY == 0:
            day = step // TURNS_PER_DAY
            rng = random.Random((int(seed) * 1_000_003) ^ day)
            for player in (0, 1):
                spawned = 0
                for _ in range(empty_tiles[player]):
                    if rng.random() < WEED_SPAWN_CHANCE:
                        spawned += 1
                empty_tiles[player] -= spawned
            next_day = day + 1
            if next_day > 0 and next_day % SHOP_UNLOCK_INTERVAL == 0:
                if len(shops) < MAX_SHOP_INSTANCES:
                    shop = rng.choice(SORTED_SHOPS)
                    shops.append(shop)
                    unlocks.append({"day": next_day, "shop": shop})

    return {
        "seed": int(seed),
        "engine_blob_sha": ENGINE_BLOB_SHA,
        "spec_blob_sha": SPEC_BLOB_SHA,
        "unlocks": unlocks,
        "final_empty_tiles": empty_tiles,
        "steps": steps,
    }


def _quantile(values: list[float], q: float) -> float:
    xs = sorted(values)
    if not xs:
        raise ValueError("empty quantile")
    if len(xs) == 1:
        return float(xs[0])
    k = (len(xs) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    if lo == hi:
        return float(xs[lo])
    return float(xs[lo] + (xs[hi] - xs[lo]) * (k - lo))


def summarize(seeds: list[int]) -> tuple[list[dict], list[dict], dict]:
    runs = [simulate(seed) for seed in seeds]
    step_rows = []
    for step in range(ACTION_STEPS):
        for item in PRODUCTS:
            iv = [r["steps"][step]["inventory"][item] for r in runs]
            pv = [r["steps"][step]["prices"][item] for r in runs]
            step_rows.append({
                "step": step,
                "day": step // TURNS_PER_DAY,
                "hour": step % TURNS_PER_DAY,
                "product": item,
                "inventory_mean": statistics.fmean(iv),
                "inventory_min": min(iv),
                "inventory_p10": _quantile(iv, .10),
                "inventory_median": statistics.median(iv),
                "inventory_p90": _quantile(iv, .90),
                "inventory_max": max(iv),
                "price_mean": statistics.fmean(pv),
                "price_min": min(pv),
                "price_p10": _quantile(pv, .10),
                "price_median": statistics.median(pv),
                "price_p90": _quantile(pv, .90),
                "price_max": max(pv),
            })

    # End-of-day/post-step snapshots: hour23 where available, plus final step718.
    day_rows = [row for row in step_rows if row["hour"] == 23 or row["step"] == ACTION_STEPS - 1]

    crossings = {}
    for item in PRODUCTS:
        T = MARKET_PARAMS[item]["T"]
        first_steps = []
        for run in runs:
            first = None
            for row in run["steps"]:
                if MARKET_I0 - row["inventory"][item] >= T:
                    first = row["step"]
                    break
            first_steps.append(first)
        reached = [x for x in first_steps if x is not None]
        crossings[item] = {
            "curve": MARKET_PARAMS[item]["below_func"],
            "T": T,
            "seeds_reaching_T": len(reached),
            "fraction_reaching_T": len(reached) / len(runs),
            "first_step_min": min(reached) if reached else None,
            "first_step_median": statistics.median(reached) if reached else None,
            "first_step_max": max(reached) if reached else None,
            "first_day_min": (min(reached) // TURNS_PER_DAY) if reached else None,
            "first_day_median": (statistics.median(reached) / TURNS_PER_DAY) if reached else None,
            "first_day_max": (max(reached) // TURNS_PER_DAY) if reached else None,
            "per_seed_first_step": first_steps,
        }

    final = {}
    for item in PRODUCTS:
        iv = [r["steps"][-1]["inventory"][item] for r in runs]
        pv = [r["steps"][-1]["prices"][item] for r in runs]
        final[item] = {
            "depletion_min": MARKET_I0 - max(iv),
            "depletion_mean": MARKET_I0 - statistics.fmean(iv),
            "depletion_max": MARKET_I0 - min(iv),
            "price_min": min(pv),
            "price_mean": statistics.fmean(pv),
            "price_median": statistics.median(pv),
            "price_max": max(pv),
        }

    shop_sequences = [tuple(u["shop"] for u in r["unlocks"]) for r in runs]
    shop_counts = {shop: sum(seq.count(shop) for seq in shop_sequences) for shop in SORTED_SHOPS}
    report = {
        "engine_blob_sha": ENGINE_BLOB_SHA,
        "spec_blob_sha": SPEC_BLOB_SHA,
        "model": "source-exact reduced no-action semantics; not a full kaggle_environments interpreter execution",
        "seed_count": len(seeds),
        "seeds": seeds,
        "action_steps": ACTION_STEPS,
        "shop_unlock_days": [3, 6, 9, 12, 15, 18, 21, 24],
        "shop_instance_counts_across_all_seeds": shop_counts,
        "threshold_crossings": crossings,
        "final": final,
        "curve_note": "T is a normalization scale for all curves; only below_func=hinge has a hinge knee at T. STRAWBERRY=sqrt and WOOL=log do not spike at T.",
    }
    return step_rows, day_rows, report


def write_outputs(out_dir: Path, seeds: list[int]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    step_rows, day_rows, report = summarize(seeds)
    for name, rows in (("price_curve_steps.csv", step_rows), ("price_curve_days.csv", day_rows)):
        with (out_dir / name).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    with (out_dir / "baseline_summary.json").open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("."))
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--seed-count", type=int, default=100)
    args = parser.parse_args()
    seeds = list(range(args.seed_start, args.seed_start + args.seed_count))
    write_outputs(args.out, seeds)


if __name__ == "__main__":
    main()

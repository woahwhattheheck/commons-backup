#!/usr/bin/env python3
"""Source-bound opening/expansion economics probes for TITAN V4.

This is research only. It does not change the controller, config, runtime, or defaults.
It binds to the canonical reference engine by Git blob identity and models only:
  * the exact `_spawn_weeds` Bernoulli kernel on eligible empty unlocked tiles; and
  * a rigorous lower bound on one-farmer Day-0 goose placement work.

The weed panel intentionally does NOT claim to be a full-interpreter replay: town/shop
RNG and the other farm can advance the shared RNG stream. Its expectation is exact for
the source kernel; its fixed-seed samples are a reproducible kernel panel.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
CONFIG_GIT_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
DEFAULT_WEED_CHANCE = 0.005
DEFAULT_TURNS_PER_DAY = 24
DEFAULT_STARTING_MONEY = 3000
GOOSE_COST = 300

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[3]
ENGINE = LAB / "reference" / "engine" / "kaggriculture.py"
CONFIG = LAB / "reference" / "engine" / "kaggriculture.json"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def assert_authority() -> dict:
    engine = ENGINE.read_bytes()
    config = CONFIG.read_bytes()
    got_engine = git_blob(engine)
    got_config = git_blob(config)
    if got_engine != ENGINE_GIT_BLOB:
        raise SystemExit(f"engine drift: {got_engine} != {ENGINE_GIT_BLOB}")
    if got_config != CONFIG_GIT_BLOB:
        raise SystemExit(f"config drift: {got_config} != {CONFIG_GIT_BLOB}")
    cfg = json.loads(config)
    c = cfg["configuration"]
    facts = {
        "engine_git_blob": got_engine,
        "config_git_blob": got_config,
        "weedSpawnChance": c["weedSpawnChance"]["default"],
        "turnsPerDay": c["turnsPerDay"]["default"],
        "startingMoney": c["startingMoney"]["default"],
        "maxMarketOrdersPerTurn": c["maxMarketOrdersPerTurn"]["default"],
    }
    expected = {
        "weedSpawnChance": DEFAULT_WEED_CHANCE,
        "turnsPerDay": DEFAULT_TURNS_PER_DAY,
        "startingMoney": DEFAULT_STARTING_MONEY,
        "maxMarketOrdersPerTurn": 10,
    }
    for k, v in expected.items():
        if facts[k] != v:
            raise SystemExit(f"config fact drift: {k}={facts[k]!r} != {v!r}")
    return facts


def expected_spawn_events(empty_tiles: int, days: int = 30, p: float = DEFAULT_WEED_CHANCE) -> float:
    """Expected weed spawns if weeds are cleared and all N sites become empty each day."""
    return empty_tiles * days * p


def expected_distinct_uncleared(empty_tiles: int, days: int = 30, p: float = DEFAULT_WEED_CHANCE) -> float:
    """Expected occupied weed sites after D days if spawned weeds are never cleared."""
    return empty_tiles * (1.0 - (1.0 - p) ** days)


def simulate_kernel(seed: int, empty_tiles: int, days: int = 30,
                    p: float = DEFAULT_WEED_CHANCE, clear_daily: bool = True) -> int:
    """Mirror `_spawn_weeds` over a fixed set of otherwise-empty eligible tiles."""
    rng = random.Random(seed)
    weed = [False] * empty_tiles
    events = 0
    for _ in range(days):
        if clear_daily:
            weed = [False] * empty_tiles
        for i in range(empty_tiles):
            if not weed[i] and rng.random() < p:
                weed[i] = True
                events += 1
    return events


def panel(seeds=range(1, 101), days: int = 30, p: float = DEFAULT_WEED_CHANCE) -> dict:
    out = {}
    for clear_daily in (True, False):
        label = "clear_daily" if clear_daily else "never_clear"
        out[label] = {}
        for n in (25, 100):
            values = [simulate_kernel(s, n, days, p, clear_daily) for s in seeds]
            out[label][str(n)] = {
                "n_seeds": len(values),
                "mean_events": statistics.fmean(values),
                "median_events": statistics.median(values),
                "min_events": min(values),
                "max_events": max(values),
                "population_sd": statistics.pstdev(values),
            }
    return out


def action_banking_tile_cost(days: int = 30, p: float = DEFAULT_WEED_CHANCE) -> dict:
    """Compare a blanket zero-cost structure blocker with leaving one tile empty until use."""
    weed_probability = 1.0 - (1.0 - p) ** days
    return {
        "days": days,
        "weed_probability_if_left_empty": weed_probability,
        "expected_busy_day_digs_empty_tile": weed_probability,
        "guaranteed_busy_day_digs_prebuilt_structure": 1.0,
        "structure_to_empty_expected_dig_ratio": 1.0 / weed_probability if weed_probability else float("inf"),
        "disposition": "BLANKET_STRUCTURE_BANKING_INCREASES_EXPECTED_FUTURE_DIGS",
    }


def goose_one_farmer_lower_bound(n_geese: int) -> dict:
    """Rigorous action lower bound for the stated no-hire Day-0 opener.

    One connected-path placement of n animals needs n BUILD_COOP, n PLACE,
    n-1 moves, and one PICKUP from the shed. BUY_ANIMAL is market work, but
    unit work runs first, so callback-0 purchases are not usable until callback 1.
    """
    if n_geese < 1:
        return {"n_geese": n_geese, "minimum_unit_actions": 0, "feasible_one_farmer_day0": True}
    minimum = n_geese + n_geese + (n_geese - 1) + 1
    return {
        "n_geese": n_geese,
        "minimum_unit_actions": minimum,
        "day0_unit_action_capacity": DEFAULT_TURNS_PER_DAY,
        "post_purchase_callbacks_available": DEFAULT_TURNS_PER_DAY - 1,
        "post_purchase_actions_required_after_callback0_build": minimum - 1,
        "feasible_one_farmer_day0": minimum <= DEFAULT_TURNS_PER_DAY,
        "animal_cash": n_geese * GOOSE_COST,
        "starting_money": DEFAULT_STARTING_MONEY,
    }


def report() -> dict:
    authority = assert_authority()
    p = float(authority["weedSpawnChance"])
    days = 30
    seeds = range(1, 101)
    p25 = expected_spawn_events(25, days, p)
    p100 = expected_spawn_events(100, days, p)
    u25 = expected_distinct_uncleared(25, days, p)
    u100 = expected_distinct_uncleared(100, days, p)
    one = goose_one_farmer_lower_bound(10)
    max_one = max(n for n in range(1, 11) if goose_one_farmer_lower_bound(n)["feasible_one_farmer_day0"])
    return {
        "schema": "titan-v4-opening-expansion-economics/v1",
        "authority": authority,
        "weed_kernel": {
            "interpretation": (
                "Weed exposure scales with eligible EMPTY unlocked tiles, not unlocked quadrants per se. "
                "The source kernel is linear in eligible None tiles; occupied plant/structure/weed tiles are ineligible."
            ),
            "analytic_clear_daily": {
                "25_empty_tiles_expected_events_30d": p25,
                "100_empty_tiles_expected_events_30d": p100,
                "incremental_events_100_minus_25": p100 - p25,
                "ratio": p100 / p25,
            },
            "analytic_never_clear": {
                "25_empty_tiles_expected_distinct_30d": u25,
                "100_empty_tiles_expected_distinct_30d": u100,
                "incremental_distinct_100_minus_25": u100 - u25,
            },
            "fixed_seed_kernel_panel": panel(seeds, days, p),
            "limit": (
                "Kernel-exact, not a full-interpreter RNG replay: town/shop selection and the other farm "
                "advance the shared episode RNG. Expectations remain exact for the source Bernoulli kernel."
            ),
        },
        "action_banking": action_banking_tile_cost(days, p),
        "goose_printer": {
            "stated_10_goose_no_hire": one,
            "one_farmer_day0_ideal_path_max_geese": max_one,
            "max_day0_fertilizer_from_that_ideal_no_hire_path": max_one,
            "headline": (
                "The stated 10-goose / one-farmer Day-0 opener is mechanically impossible as written: "
                "it omits shed PICKUP and movement. Even an obstacle-free connected path requires 30 unit actions "
                "against 24 callbacks. The ideal one-farmer upper bound is 8 placed geese before EOD0; "
                "hires may change feasibility and must be evaluated as a different opener."
            ),
            "limit": (
                "This is a lower-bound/falsification result, not a proof that an 8-goose path is globally optimal "
                "or that a hired-hand goose opener beats crops/land."
            ),
        },
        "disposition": "RESEARCH_ONLY_NO_POLICY_PROMOTION",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    args = ap.parse_args()
    r = report()
    text = json.dumps(r, sort_keys=True, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

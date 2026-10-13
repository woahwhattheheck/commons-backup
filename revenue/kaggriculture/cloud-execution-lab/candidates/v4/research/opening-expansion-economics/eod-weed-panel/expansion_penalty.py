#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound TITAN V4 land-expansion weed-pressure oracle.

Quantifies the random-weed burden created by empty unlocked tiles under the
pinned official Kaggriculture engine.  Two explicit envelopes are measured:

* perfect-clear: every random weed is cleared before the next EOD, so every
  empty unlocked tile is eligible every day; this is the maximum recurring
  random-spawn exposure and a lower bound on DIG service actions;
* persistent: random weeds are never cleared, so occupied weed tiles stop
  drawing future random-spawn rolls; this measures passive end-state occupancy.

The tool is evidence only.  It does not decide whether BUY_LAND is profitable,
because production value, occupancy, travel, routing and worker opportunity cost
are outside the random-spawn mechanism.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import statistics
import sys
import types
from typing import Any, Iterable

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
CONFIG_GIT_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
CONFIG_SHA256 = "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867"
REFERENCE_ARCHIVE_SHA256 = "b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9"
T_CRIT_DF99_95 = 1.9842169515


class ExpansionError(RuntimeError):
    pass


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _verify_file(path: str | Path, *, blob: str, sha256: str, label: str) -> bytes:
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise ExpansionError(f"cannot read {label}: {p}: {exc}") from exc
    actual_blob = _git_blob_sha(data)
    actual_sha = hashlib.sha256(data).hexdigest()
    if actual_blob != blob or actual_sha != sha256:
        raise ExpansionError(
            f"{label} identity mismatch: git_blob={actual_blob} sha256={actual_sha}"
        )
    return data


def load_engine(path: str | Path):
    _verify_file(path, blob=ENGINE_GIT_BLOB, sha256=ENGINE_SHA256, label="engine")
    inserted: list[str] = []
    try:
        import kaggle_environments.utils  # type: ignore  # noqa: F401
    except ModuleNotFoundError:
        pkg = types.ModuleType("kaggle_environments")
        util = types.ModuleType("kaggle_environments.utils")
        util.resolve_episode_seed = lambda env: getattr(env, "info", {}).get("seed", 0)
        pkg.utils = util
        sys.modules["kaggle_environments"] = pkg
        sys.modules["kaggle_environments.utils"] = util
        inserted = ["kaggle_environments.utils", "kaggle_environments"]

    spec = importlib.util.spec_from_file_location("titan_expansion_reference", Path(path))
    if spec is None or spec.loader is None:
        raise ExpansionError("cannot import pinned engine")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        for name in inserted:
            sys.modules.pop(name, None)
    return module


def load_config(path: str | Path) -> dict[str, Any]:
    data = _verify_file(path, blob=CONFIG_GIT_BLOB, sha256=CONFIG_SHA256, label="config")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ExpansionError("config root must be an object")
    return value


def default_value(config: dict[str, Any], key: str) -> Any:
    raw = config.get("configuration", {}).get(key)
    if not isinstance(raw, dict) or "default" not in raw:
        raise ExpansionError(f"missing config default for {key}")
    return raw["default"]


def _farm_with_quadrants(engine, total_quadrants: int, board_size: int = 10):
    if total_quadrants not in (1, 2, 3, 4):
        raise ExpansionError("total_quadrants must be in 1..4")
    farm = engine._new_farm(board_size, 10_000_000)
    while len(farm["unlocked_quadrants"]) < total_quadrants:
        engine._do_buy_land(farm, board_size)
    return farm


def _weed_count(farm) -> int:
    return sum(
        isinstance(tile, dict) and tile.get("kind") == "WEED"
        for row in farm["tiles"]
        for tile in row
    )


def _clear_random_weeds(farm) -> None:
    for y, row in enumerate(farm["tiles"]):
        for x, tile in enumerate(row):
            if isinstance(tile, dict) and tile.get("kind") == "WEED":
                farm["tiles"][y][x] = None


def unlocked_empty_tiles(farm) -> int:
    return sum(tile is None for row in farm["tiles"] for tile in row)


def simulate_seed(
    engine,
    *,
    seed: int,
    total_quadrants: int,
    days: int,
    weed_chance: float,
    perfect_clear: bool,
) -> dict[str, int]:
    farm = _farm_with_quadrants(engine, total_quadrants)
    initial_eligible = unlocked_empty_tiles(farm)
    cumulative = 0
    for day in range(days):
        before = _weed_count(farm)
        rng = random.Random((seed * 1_000_003) ^ day)
        engine._spawn_weeds(farm, 10, weed_chance, rng)
        after = _weed_count(farm)
        cumulative += after - before
        if perfect_clear:
            _clear_random_weeds(farm)
    return {
        "initial_eligible_tiles": initial_eligible,
        "spawn_events": cumulative,
        "final_weeds": _weed_count(farm),
    }


def _summary(values: list[int]) -> dict[str, float | int]:
    ordered = sorted(values)
    def quantile(q: float) -> float:
        pos = (len(ordered) - 1) * q
        lo = math.floor(pos)
        hi = math.ceil(pos)
        if lo == hi:
            return float(ordered[lo])
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)
    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "sample_stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "p05": quantile(0.05),
        "p25": quantile(0.25),
        "median": quantile(0.50),
        "p75": quantile(0.75),
        "p95": quantile(0.95),
        "max": max(values),
    }


def _paired_summary(values: list[int]) -> dict[str, float | int | None]:
    result = _summary(values)
    sd = float(result["sample_stdev"])
    se = sd / math.sqrt(len(values)) if values else 0.0
    mean = float(result["mean"])
    result["standard_error"] = se
    if len(values) == 100:
        result["t95_low"] = mean - T_CRIT_DF99_95 * se
        result["t95_high"] = mean + T_CRIT_DF99_95 * se
    else:
        # T_CRIT_DF99_95 is exact only for the canonical 100-seed panel.
        # Arbitrary CLI sample sizes remain useful for smoke/analytic runs, but
        # must not be mislabeled as having a df=99 Student-t confidence interval.
        result["t95_low"] = None
        result["t95_high"] = None
    result["negative_pairs"] = sum(v < 0 for v in values)
    result["zero_pairs"] = sum(v == 0 for v in values)
    result["positive_pairs"] = sum(v > 0 for v in values)
    return result


def run_panel(engine, config: dict[str, Any], seeds: Iterable[int], *, days: int = 30):
    seed_list = list(seeds)
    if not seed_list:
        raise ExpansionError("need at least one seed")
    if any(type(seed) is not int or seed < 0 for seed in seed_list):
        raise ExpansionError("seeds must be nonnegative literal integers")
    weed_chance = float(default_value(config, "weedSpawnChance"))
    board_size = int(default_value(config, "boardSize"))
    if board_size != 10:
        raise ExpansionError(f"expected pinned boardSize 10, got {board_size}")

    rows: list[dict[str, Any]] = []
    for seed in seed_list:
        q1_clear = simulate_seed(
            engine, seed=seed, total_quadrants=1, days=days,
            weed_chance=weed_chance, perfect_clear=True,
        )
        q4_clear = simulate_seed(
            engine, seed=seed, total_quadrants=4, days=days,
            weed_chance=weed_chance, perfect_clear=True,
        )
        q1_persistent = simulate_seed(
            engine, seed=seed, total_quadrants=1, days=days,
            weed_chance=weed_chance, perfect_clear=False,
        )
        q4_persistent = simulate_seed(
            engine, seed=seed, total_quadrants=4, days=days,
            weed_chance=weed_chance, perfect_clear=False,
        )
        rows.append({
            "seed": seed,
            "q1_clear_events": q1_clear["spawn_events"],
            "q4_clear_events": q4_clear["spawn_events"],
            "incremental_clear_events": q4_clear["spawn_events"] - q1_clear["spawn_events"],
            "q1_persistent_final_weeds": q1_persistent["final_weeds"],
            "q4_persistent_final_weeds": q4_persistent["final_weeds"],
            "incremental_persistent_weeds": q4_persistent["final_weeds"] - q1_persistent["final_weeds"],
        })

    q1_clear_values = [r["q1_clear_events"] for r in rows]
    q4_clear_values = [r["q4_clear_events"] for r in rows]
    clear_diff = [r["incremental_clear_events"] for r in rows]
    q1_persistent_values = [r["q1_persistent_final_weeds"] for r in rows]
    q4_persistent_values = [r["q4_persistent_final_weeds"] for r in rows]
    persistent_diff = [r["incremental_persistent_weeds"] for r in rows]

    q1_tiles = 25
    q4_tiles = 100
    extra_tiles = q4_tiles - q1_tiles
    expected_clear_q1 = q1_tiles * weed_chance * days
    expected_clear_q4 = q4_tiles * weed_chance * days
    expected_persistent_q1 = q1_tiles * (1 - (1 - weed_chance) ** days)
    expected_persistent_q4 = q4_tiles * (1 - (1 - weed_chance) ** days)
    land_cost = sum(engine.LAND_PRICES)

    summary = {
        "schema": "titan-v4-expansion-weed-pressure/v1",
        "engine_git_blob": ENGINE_GIT_BLOB,
        "engine_sha256": ENGINE_SHA256,
        "config_git_blob": CONFIG_GIT_BLOB,
        "config_sha256": CONFIG_SHA256,
        "reference_archive_sha256": REFERENCE_ARCHIVE_SHA256,
        "seeds": seed_list,
        "days": days,
        "weed_spawn_chance": weed_chance,
        "land_prices": list(engine.LAND_PRICES),
        "one_to_four_quadrant_land_cost": land_cost,
        "empty_unlocked_tiles": {"q1": q1_tiles, "q4": q4_tiles, "incremental": extra_tiles},
        "perfect_clear_spawn_events": {
            "q1": _summary(q1_clear_values),
            "q4": _summary(q4_clear_values),
            "incremental_q4_minus_q1": _paired_summary(clear_diff),
            "analytic_expectation": {
                "q1": expected_clear_q1,
                "q4": expected_clear_q4,
                "incremental": expected_clear_q4 - expected_clear_q1,
            },
        },
        "persistent_no_clear_final_weeds": {
            "q1": _summary(q1_persistent_values),
            "q4": _summary(q4_persistent_values),
            "incremental_q4_minus_q1": _paired_summary(persistent_diff),
            "analytic_expectation": {
                "q1": expected_persistent_q1,
                "q4": expected_persistent_q4,
                "incremental": expected_persistent_q4 - expected_persistent_q1,
            },
        },
        "break_even": {
            "extra_land_cash_cost": land_cost,
            "minimum_expected_extra_dig_actions_if_kept_empty_and_perfectly_cleared": (
                expected_clear_q4 - expected_clear_q1
            ),
            "minimum_hurdle_formula": "7000 + 11.25*A + travel/routing opportunity cost, where A is value per DIG action",
            "average_upfront_cash_per_extra_tile": land_cost / extra_tiles,
            "expected_random_digs_per_extra_empty_tile_over_30d": weed_chance * days,
        },
        "interpretation": {
            "strict_one_quadrant_superiority_proven": False,
            "reason": (
                "random weeds apply only to None tiles; productive structures/plants/animals remove tiles from this random-spawn surface, "
                "and extra land has production/routing value not represented by the weed oracle"
            ),
            "perfect_clear_is": "maximum recurring random-spawn exposure for the stated empty-tile board and a lower bound on DIG service actions; movement is additional",
            "persistent_is": "passive occupancy envelope with no maintenance, not an action-cost estimate",
        },
    }
    return rows, summary


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "seed", "q1_clear_events", "q4_clear_events", "incremental_clear_events",
        "q1_persistent_final_weeds", "q4_persistent_final_weeds", "incremental_persistent_weeds",
    ]
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--seed-count", type=int, default=100)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--csv-out", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)
    if args.seed_count <= 0 or args.days <= 0:
        parser.error("seed-count and days must be positive")
    try:
        engine = load_engine(args.engine)
        config = load_config(args.config)
        rows, summary = run_panel(
            engine, config,
            range(args.seed_start, args.seed_start + args.seed_count),
            days=args.days,
        )
    except (ExpansionError, OSError, ValueError) as exc:
        parser.error(str(exc))
    if args.csv_out:
        write_csv(args.csv_out, rows)
    payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        args.json_out.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

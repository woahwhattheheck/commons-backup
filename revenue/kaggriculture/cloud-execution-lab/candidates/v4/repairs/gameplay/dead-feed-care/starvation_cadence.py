#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound verifier for safe intermittent animal feeding.

This is research/evidence tooling for the existing TITAN V4 dead-feed-care
family.  It loads the pinned official Kaggriculture interpreter by exact bytes,
runs complete interpreter transitions for constructed placed-animal controls,
and compares daily feeding with the minimum no-two-consecutive-unfed cadence.
It is not a controller and does not mutate runtime defaults.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
from types import SimpleNamespace
from typing import Any

ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
REFERENCE_ARCHIVE_SHA256 = "b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9"
EXPECTED_PRODUCTS = {"GOOSE": 27, "COW": 12, "SHEEP": 9}
EXPECTED_HELD_CAPS = {"GOOSE": 4, "COW": 6, "SHEEP": 6}


class VerificationError(RuntimeError):
    pass


def _git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _engine_bytes(path: str | Path) -> bytes:
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as exc:
        raise VerificationError(f"cannot read engine: {p}: {exc}") from exc
    sha256 = hashlib.sha256(data).hexdigest()
    blob = _git_blob_sha(data)
    if sha256 != ENGINE_SHA256 or blob != ENGINE_GIT_BLOB:
        raise VerificationError(
            "official engine identity mismatch: "
            f"git_blob={blob} sha256={sha256}"
        )
    return data


def load_engine(path: str | Path):
    """Import the exact pinned engine without substituting transition logic."""
    _engine_bytes(path)
    p = Path(path)

    inserted: list[str] = []
    try:
        import kaggle_environments.utils  # type: ignore  # noqa: F401
    except ModuleNotFoundError:
        # The checked engine imports only resolve_episode_seed from this package.
        # The constructed verifier supplies env.info['seed']; _initialize does not
        # otherwise use the returned local seed.  All game transition functions
        # still come from the exact authenticated official engine bytes.
        pkg = types.ModuleType("kaggle_environments")
        util = types.ModuleType("kaggle_environments.utils")

        def resolve_episode_seed(env):
            info = getattr(env, "info", {})
            return info.get("seed", 0) if isinstance(info, dict) else 0

        util.resolve_episode_seed = resolve_episode_seed
        pkg.utils = util
        sys.modules["kaggle_environments"] = pkg
        sys.modules["kaggle_environments.utils"] = util
        inserted = ["kaggle_environments.utils", "kaggle_environments"]

    module_name = f"titan_starvation_reference_{hashlib.sha256(str(p).encode()).hexdigest()[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, p)
    if spec is None or spec.loader is None:
        raise VerificationError(f"cannot create import spec for {p}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        for name in inserted:
            sys.modules.pop(name, None)
    return module


def _make_state_env(engine, seed: int = 1909087201):
    cfg = SimpleNamespace(
        boardSize=10,
        startingMoney=3000,
        turnsPerDay=24,
        shedCapacity=10000,
        weedSpawnChance=0.0,
        townShopUnlockInterval=10**9,
        townShopSellInterval=10**9,
        townCenterSellInterval=10**9,
        episodeSteps=100000,
        farmHandCostMult=1,
        maxMarketOrdersPerTurn=10,
    )
    env = SimpleNamespace(configuration=cfg, info={"seed": seed}, done=False)
    state = [
        SimpleNamespace(
            observation=SimpleNamespace(step=0),
            action={"farmer": ["PASS"]},
            status="ACTIVE",
            reward=0.0,
        )
        for _ in range(2)
    ]
    engine._initialize(state, env)
    return state, env


def _present_animal(tile: Any, species: str) -> bool:
    return isinstance(tile, dict) and tile.get("animal") == species


def run_cadence(
    engine,
    species: str,
    *,
    days: int = 30,
    feed_mode: str = "daily",
    phase: int = 0,
    care_every_day: bool = False,
    harvest_every_day: bool = True,
) -> dict[str, Any]:
    """Run one complete-interpreter constructed animal cadence.

    ``feed_mode='alternating'`` feeds on days where ``day % 2 == phase``.
    The harness harvests and collects fertilizer daily to avoid confusing held
    capacity with production.  ``harvest_every_day=False`` is the cap control.
    """
    if species not in engine.ANIMALS:
        raise VerificationError(f"unknown species: {species}")
    if feed_mode not in {"daily", "alternating", "never"}:
        raise VerificationError(f"unsupported feed_mode: {feed_mode}")
    if phase not in (0, 1):
        raise VerificationError("phase must be 0 or 1")
    if days <= 0:
        raise VerificationError("days must be positive")

    state, env = _make_state_env(engine)
    farm = state[0].observation.farms[0]
    private = state[0].observation.private
    x, y = farm["farmer"]
    farm["tiles"][y][x] = engine._new_animal(species, 0)

    initial_wheat = 1000
    private["shed"]["WHEAT"] = initial_wheat
    counts = {"pickup": 0, "feed": 0, "care": 0, "harvest": 0, "fertilizer_collect": 0}

    for day in range(days):
        if feed_mode == "daily":
            feed_today = True
        elif feed_mode == "alternating":
            feed_today = day % 2 == phase
        else:
            feed_today = False

        actions: dict[int, list[Any]] = {0: ["COLLECT_FERTILIZER"]}
        counts["fertilizer_collect"] += 1
        if harvest_every_day:
            actions[1] = ["HARVEST"]
            counts["harvest"] += 1
        if feed_today:
            actions[2] = ["PICKUP", "WHEAT", 1]
            actions[3] = ["FEED"]
            counts["pickup"] += 1
            counts["feed"] += 1
        if care_every_day:
            actions[4] = ["CARE"]
            counts["care"] += 1

        for hour in range(24):
            step = day * 24 + hour
            state[0].observation.step = step
            state[0].action = {"farmer": actions.get(hour, ["PASS"])}
            state[1].action = {"farmer": ["PASS"]}
            engine.interpreter(state, env)

        tile = farm["tiles"][y][x]
        if not _present_animal(tile, species):
            return {
                "species": species,
                "feed_mode": feed_mode,
                "phase": phase,
                "days_requested": days,
                "survived": False,
                "escaped_day": day,
                "action_attempts": counts,
            }

    tile = farm["tiles"][y][x]
    product = engine.ANIMALS[species]["product"]
    product_total = (
        private["shed"].get(product, 0)
        + sum(inv.get(product, 0) for inv in private["inventories"])
        + tile.get("yield_units", 0)
    )
    fertilizer_total = (
        private["shed"].get("FERTILIZER", 0)
        + sum(inv.get("FERTILIZER", 0) for inv in private["inventories"])
        + (1 if tile.get("fertilizer_available") else 0)
    )
    wheat_remaining = private["shed"].get("WHEAT", 0) + sum(
        inv.get("WHEAT", 0) for inv in private["inventories"]
    )
    return {
        "species": species,
        "product": product,
        "feed_mode": feed_mode,
        "phase": phase,
        "days_requested": days,
        "survived": True,
        "escaped_day": None,
        "product_total": product_total,
        "fertilizer_total": fertilizer_total,
        "wheat_consumed": initial_wheat - wheat_remaining,
        "final_yield_units": tile.get("yield_units", 0),
        "final_consecutive_unfed": tile.get("consecutive_unfed"),
        "action_attempts": counts,
    }


def build_receipt(engine_path: str | Path) -> dict[str, Any]:
    engine = load_engine(engine_path)
    rows = []
    cap_rows = []
    care_rows = []
    for species in sorted(engine.ANIMALS):
        daily = run_cadence(engine, species, feed_mode="daily")
        alt0 = run_cadence(engine, species, feed_mode="alternating", phase=0)
        alt1 = run_cadence(engine, species, feed_mode="alternating", phase=1)
        rows.append({"species": species, "daily": daily, "alternating_phase0": alt0, "alternating_phase1": alt1})

        cap_rows.append(
            {
                "species": species,
                "daily": run_cadence(engine, species, feed_mode="daily", harvest_every_day=False),
                "alternating": run_cadence(
                    engine, species, feed_mode="alternating", phase=0, harvest_every_day=False
                ),
            }
        )
        care_rows.append(
            {
                "species": species,
                "daily": run_cadence(engine, species, feed_mode="daily", care_every_day=True),
                "alternating": run_cadence(
                    engine, species, feed_mode="alternating", phase=0, care_every_day=True
                ),
            }
        )

    escape = {
        species: run_cadence(engine, species, days=2, feed_mode="never")
        for species in sorted(engine.ANIMALS)
    }
    return {
        "schema": "titan-v4-starvation-oracle/v1",
        "engine_git_blob": ENGINE_GIT_BLOB,
        "engine_sha256": ENGINE_SHA256,
        "reference_archive_sha256": REFERENCE_ARCHIVE_SHA256,
        "scope": "constructed placed-animal complete-interpreter mechanism controls; not field EV or activation",
        "base_no_care": rows,
        "held_capacity_control": cap_rows,
        "care_counterexample": care_rows,
        "two_consecutive_unfed_escape": escape,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = build_receipt(args.engine)
    except VerificationError as exc:
        parser.error(str(exc))
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

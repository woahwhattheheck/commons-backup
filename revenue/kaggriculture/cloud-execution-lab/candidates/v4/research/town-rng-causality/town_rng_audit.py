"""Source-pinned, offline TITAN town-path causal diagnostics.

This is evaluation/research tooling, not an agent feature. It does not infer a
hidden episode seed, change RNG draws, modify the engine source, or activate V4.
A same-seed score delta is a total policy effect; differing shop paths make it
insufficient evidence for a *direct crop-profit* claim without further controls.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import platform
import sys
import types
from pathlib import Path
from typing import Any

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
# SHA256 is also recorded from the unchanged loaded engine bytes.
CANONICAL_WORKSPACE = "revenue/kaggriculture/cloud-execution-lab/candidates/v4"
DEFAULT_CONFIG = {
    "boardSize": 10, "turnsPerDay": 24, "weedSpawnChance": 0.005,
    "shedCapacity": 100, "townShopUnlockInterval": 3,
    "townShopSellInterval": 4, "townCenterSellInterval": 24,
    "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1, "episodeSteps": 720,
}
S = types.SimpleNamespace


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load_engine(path: Path) -> Any:
    """Load unchanged, hash-verified engine; reject initialization via shim.

    The tests construct explicit states, so the Kaggle framework's episode-seed
    resolver must never run. The temporary import shim raises if called. It is
    removed/restored immediately after import; no engine operation is stubbed.
    """
    data = path.read_bytes()
    actual = git_blob(data)
    if actual != ENGINE_BLOB:
        raise ValueError(f"Engine identity mismatch: {actual}; expected {ENGINE_BLOB}")
    sentinel = object()
    names = ("kaggle_environments", "kaggle_environments.utils")
    saved = {name: sys.modules.get(name, sentinel) for name in names}
    parent = types.ModuleType(names[0])
    utils = types.ModuleType(names[1])

    def no_initialization(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Framework initialization is outside this offline diagnostic")

    utils.resolve_episode_seed = no_initialization
    parent.utils = utils
    sys.modules[names[0]] = parent
    sys.modules[names[1]] = utils
    try:
        spec = importlib.util.spec_from_file_location("_titan_pinned_town_engine", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot load pinned engine")
        engine = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(engine)
    finally:
        for name, prior in saved.items():
            if prior is sentinel:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior
    engine._audit_source_sha256 = hashlib.sha256(data).hexdigest()
    return engine


def pass_action() -> dict[str, Any]:
    return {"farmer": ["PASS"], "hands": [], "market": []}


def fixture(engine: Any, seed: int, step: int = 0,
            weed_chance: float = 0.005) -> tuple[list[Any], Any]:
    cfg = S(**{**DEFAULT_CONFIG, "weedSpawnChance": weed_chance})
    farms = [engine._new_farm(cfg.boardSize, 3000) for _ in range(2)]
    market, town = engine._new_market(), engine._new_town()
    state = [S(observation=S(player=i, step=step, day=step // cfg.turnsPerDay,
                            hour=step % cfg.turnsPerDay, farms=farms, market=market,
                            town=town, private=engine._new_private()),
               action=pass_action(), status="ACTIVE", reward=0) for i in range(2)]
    return state, S(configuration=cfg, info={"seed": seed}, done=False)


def empty_tiles(farm: dict[str, Any], board_size: int) -> int:
    return sum(farm["tiles"][y][x] is None
               for y in range(board_size) for x in range(board_size))


class TownAudit:
    """Observe real end-of-day transitions without changing RNG/state/results.

    Single-threaded use with a dedicated engine module only. Counts are measured
    at _spawn_weeds entry, AFTER plant/animal refresh, not from a stale input
    observation. Both farms share the RNG later used by the town shop draw.
    """
    def __init__(self, engine: Any):
        self.engine = engine
        self.events: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._entered = False

    def __enter__(self) -> "TownAudit":
        if self._entered or getattr(self.engine, "_town_audit_attached", False):
            raise RuntimeError("TownAudit is non-reentrant; use a dedicated engine module")
        self._entered = True
        self.engine._town_audit_attached = True
        self._spawn = self.engine._spawn_weeds
        self._eod = self.engine._end_of_day
        self.engine._spawn_weeds = self._observed_spawn
        self.engine._end_of_day = self._observed_eod
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        self.engine._spawn_weeds = self._spawn
        self.engine._end_of_day = self._eod
        del self.engine._town_audit_attached
        self._entered = False
        return False

    def _observed_spawn(self, farm: Any, board_size: int,
                        weed_chance: float, rng: Any) -> Any:
        before = empty_tiles(farm, board_size)
        result = self._spawn(farm, board_size, weed_chance, rng)
        if self._current is not None:
            after = empty_tiles(farm, board_size)
            self._current["farms"].append({
                "empty_before_weed": before, "empty_after_weed": after,
                "new_weeds": before - after,
                "weed_rng_calls": before,
            })
        return result

    def _observed_eod(self, state: Any, env: Any, day: int) -> Any:
        if self._current is not None:
            raise RuntimeError("Unexpected nested end-of-day call")
        obs = state[0].observation
        before = list(obs.town["unlocked_shops"])
        event = {
            "day": day, "step": self.engine.get(obs, "step", None),
            "seed": env.info.get("seed", 0), "farms": [],
            "shops_before": before,
        }
        self._current = event
        try:
            result = self._eod(state, env, day)
            event["shops_after"] = list(obs.town["unlocked_shops"])
            event["new_shops"] = event["shops_after"][len(before):]
            event["weed_rng_calls"] = sum(f["weed_rng_calls"] for f in event["farms"])
            self.events.append(event)
            return result
        finally:
            self._current = None


def compare_traces(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> dict[str, Any]:
    """Never silently zip away missing days or compare misaligned trials."""
    if not left or not right:
        raise ValueError("No end-of-day evidence; empty traces are not a passing control")
    if len(left) != len(right):
        raise ValueError("Trace lengths differ; align complete games before attribution")
    first = None
    previous_day = None
    for a, b in zip(left, right):
        for key in ("day", "step", "seed"):
            if key not in a or key not in b or a[key] != b[key]:
                raise ValueError(f"Unpaired trace field: {key}")
        if previous_day is not None and a["day"] != previous_day + 1:
            raise ValueError("Nonconsecutive or duplicate end-of-day records")
        previous_day = a["day"]
        for key in ("shops_before", "shops_after", "weed_rng_calls"):
            if key not in a or key not in b:
                raise ValueError(f"Incomplete trace: {key}")
        if first is None and a["shops_after"] != b["shops_after"]:
            first = {"day": a["day"], "step": a["step"],
                     "left_rng_calls": a["weed_rng_calls"],
                     "right_rng_calls": b["weed_rng_calls"],
                     "left_shops": a["shops_after"], "right_shops": b["shops_after"]}
    return {
        "days_compared": len(left), "same_shop_path": first is None,
        "first_shop_divergence": first,
        "interpretation": "Total policy effect remains valid; this is not a direct-crop-profit decomposition",
    }


def planting_pair(engine: Any, seed: int = 0, seat: int = 0,
                  weed_chance: float = 0.0) -> dict[str, Any]:
    if seat not in (0, 1):
        raise ValueError("seat must be 0 or 1")
    left, env = fixture(engine, seed, step=71, weed_chance=weed_chance)
    for item in left:
        item.observation.private["seeds"]["TOMATO"] = 1
    right = copy.deepcopy(left)
    right[seat].action["farmer"] = ["PLANT", "TOMATO"]
    with TownAudit(engine) as a:
        engine.interpreter(left, copy.deepcopy(env))
    with TownAudit(engine) as b:
        engine.interpreter(right, copy.deepcopy(env))
    return {
        "seed": seed, "seat": seat, "step": 71, "weed_chance": weed_chance,
        "PASS": a.events[0], "PLANT_TOMATO": b.events[0],
        "same_immediate_cash": [f["money"] for f in left[0].observation.farms] == [f["money"] for f in right[0].observation.farms],
        "same_immediate_market": left[0].observation.market == right[0].observation.market,
        "comparison": compare_traces(a.events, b.events),
    }


def run_pass_season(engine: Any, seed: int, target: int = 1470) -> dict[str, Any]:
    """719 real interpreter callbacks from an explicit standard initial state."""
    state, env = fixture(engine, seed)
    first = None
    peak = 0
    with TownAudit(engine) as audit:
        for step in range(env.configuration.episodeSteps - 1):
            for player in state:
                player.observation.step = step
            market = state[0].observation.market
            price = engine.market_price("TOMATO", market["inventory"]["TOMATO"], market.get("params"))
            peak = max(peak, price)
            if first is None and price >= target:
                first = {"step": step, "price": price, "inventory": market["inventory"]["TOMATO"]}
            engine.interpreter(state, env)
    return {"seed": seed, "policy": "PASS vs PASS", "official_callbacks": 719,
            "peak_pre_market_quote": peak, "first_quote_at_target": first,
            "shops": list(state[0].observation.town["unlocked_shops"]),
            "final_money": [f["money"] for f in state[0].observation.farms],
            "terminal_status": [p.status for p in state], "town_trace": audit.events,
            "scope": "Synthetic PASS season, not a TITAN benchmark or realized trading profit"}


def build_report(engine: Any, sample_seeds: int = 256) -> dict[str, Any]:
    if not 1 <= sample_seeds <= 10000:
        raise ValueError("sample_seeds must be in [1, 10000]")
    counts = []
    for weed in (0.0, 0.005):
        for seat in (0, 1):
            flips = sum(not planting_pair(engine, seed, seat, weed)["comparison"]["same_shop_path"]
                        for seed in range(sample_seeds))
            counts.append({"weed_chance": weed, "seat": seat,
                           "paired_trials": sample_seeds, "shop_flips": flips})
    return {
        "source": {"engine_git_blob": ENGINE_BLOB, "engine_sha256": engine._audit_source_sha256,
                   "artifact_id": 10285621024, "source_checkout": "8250aec877974e9a1feba2b8e33fcd51000857d4",
                   "python": platform.python_version()},
        "canonical_workspace": CANONICAL_WORKSPACE,
        "witness": planting_pair(engine), "planting_shop_flip_panel": counts,
        "panel_scope": {"unique_seeds": sample_seeds, "cells": 4 * sample_seeds,
                        "kind": "One-turn midgame fixtures, NOT full games or independent replicas"},
        "prior_work": {"rng_map_donor": "36a90365add6757d8e0896e2ef7de031d46d4c49",
                       "scope": "Adds real-engine state-dependent offset witnesses; does not replace the existing RNG3 map or counterfactual harness"},
        "natural_default_pass_season": run_pass_season(engine, 7040),
        "nonclaims": ["No TITAN gameplay gain measured", "No hidden-seed input to an online agent",
                      "No production runtime/default/archive/entrypoint changed", "No V4 branch created",
                      "No Slack send, GitHub commit, merge, or Kaggle submission executed"],
    }


def default_engine_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        path = parent / "reference/engine/kaggriculture.py"
        if path.is_file():
            return path
    return Path(__file__).with_name("kaggriculture.py")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, default=default_engine_path())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample-seeds", type=int, default=256)
    args = parser.parse_args()
    report = build_report(load_engine(args.engine), args.sample_seeds)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

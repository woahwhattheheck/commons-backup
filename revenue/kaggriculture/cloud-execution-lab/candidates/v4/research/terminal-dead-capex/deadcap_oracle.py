#!/usr/bin/env python3
"""Fail-closed terminal-capex oracle for the canonical TITAN V4 donor route.

The oracle proves only acquisitions whose purchased asset has no authored route
to later cash. It deliberately over-approximates possible use: uncertainty is
REFUSE, never DEAD.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import sys
import types
from pathlib import Path

TAPE_BLOB = "a43289b9cc5e34a2481fddf652762a7d92f427ef"
TAPE_SHA256 = "4a60e775e52905048257aff4871a11c5ba49de6ba464177ed6ae4d9bd3120e18"
ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
FOUNDATION_ARTIFACT_ID = 10175943272
CURRENT_MAIN_BLOB = "4a8cf7bcda1f0fea231a144692cb84a779a9e73e"
CURRENT_RUNTIME_BLOB = "6d9720f4aa1e6b46e92ee5183897074d8e9ea5a0"
CURRENT_CONFIG_BLOB = "3a3bef83899d3010fad623b628d9e95d9978111b"
WITNESS = {"tape": 12, "step": 284, "order": ["BUY_SEED", "MELON", 1], "cost": 80}
FIRST_YIELD_DAY = {"WHEAT": 2, "CARROT": 2, "TOMATO": 8, "STRAWBERRY": 10, "MELON": 10}
BUY_OPS = frozenset(("BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "BUY_LAND"))


def git_blob(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def authenticate_current(runtime_root: Path) -> dict:
    receipt = {
        "main_blob": git_blob(runtime_root / "main.py"),
        "runtime_blob": git_blob(runtime_root / "titan_runtime.py"),
        "config_blob": git_blob(runtime_root / "TITAN-CONFIG.json"),
    }
    expected = {
        "main_blob": CURRENT_MAIN_BLOB,
        "runtime_blob": CURRENT_RUNTIME_BLOB,
        "config_blob": CURRENT_CONFIG_BLOB,
    }
    if receipt != expected:
        raise RuntimeError(f"current production drift: {receipt}")
    return receipt


def authenticate(tape_path: Path, engine_path: Path) -> dict:
    raw = tape_path.read_bytes()
    receipt = {
        "tape_bytes": len(raw),
        "tape_blob": git_blob(tape_path),
        "tape_sha256": hashlib.sha256(raw).hexdigest(),
        "engine_blob": git_blob(engine_path),
    }
    expected = {
        "tape_bytes": 32955,
        "tape_blob": TAPE_BLOB,
        "tape_sha256": TAPE_SHA256,
        "engine_blob": ENGINE_BLOB,
    }
    if receipt != expected:
        raise RuntimeError(f"source drift: {receipt}")
    return receipt


def load_tapes(tape_path: Path) -> list[list[dict]]:
    spec = importlib.util.spec_from_file_location("_deadcap_tapes", tape_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    tapes = module.load_tapes()
    if len(tapes) != 13 or any(len(tape) != 719 for tape in tapes):
        raise RuntimeError("expected exact 13x719 donor tapes")
    return tapes


def unit_actions(action: dict):
    farmer = action.get("farmer", ["PASS"])
    hands = action.get("hands", [])
    return [farmer, *(hands if isinstance(hands, list) else [])]


def seed_cash_path(tape: list[dict], buy_step: int, crop: str):
    """Return a generous future PLANT->maturity->SELL witness, else None.

    HARVEST/DROP feasibility is intentionally *not* required. Therefore if this
    over-approximation still finds no path, the bought seed cannot reach cash.
    """
    if crop not in FIRST_YIELD_DAY:
        return None
    for plant_step in range(buy_step + 1, len(tape)):  # market follows units
        if not any(
            isinstance(a, list) and len(a) >= 2 and a[0] == "PLANT" and a[1] == crop
            for a in unit_actions(tape[plant_step])
        ):
            continue
        mature_day = plant_step // 24 + FIRST_YIELD_DAY[crop]
        for sale_step in range(plant_step + 1, len(tape)):
            if sale_step // 24 < mature_day:
                continue
            if any(
                isinstance(row, list) and len(row) >= 2
                and row[0] == "SELL" and row[1] == crop
                for row in tape[sale_step].get("market", [])
            ):
                return {"plant_step": plant_step, "mature_day": mature_day, "sale_step": sale_step}
    return None


def acquisition_census(tapes: list[list[dict]]) -> dict:
    counts = {}
    late = 0
    dead_seed = []
    for tape_id, tape in enumerate(tapes):
        for step, action in enumerate(tape):
            for row_index, row in enumerate(action.get("market", [])):
                if not isinstance(row, list) or not row or row[0] not in BUY_OPS:
                    continue
                counts[row[0]] = counts.get(row[0], 0) + 1
                late += int(step >= 480)
                if row[0] == "BUY_SEED" and len(row) >= 3:
                    path = seed_cash_path(tape, step, row[1])
                    if path is None:
                        dead_seed.append({
                            "tape": tape_id,
                            "step": step,
                            "row_index": row_index,
                            "order": row,
                            "reason": "no_future_plant_maturity_sale_path",
                        })
    return {"counts": counts, "late_ge_480": late, "dead_seed_candidates": dead_seed}


class AttrDict(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc
    __setattr__ = dict.__setitem__


class State:
    def __init__(self, player: int):
        self.observation = AttrDict(step=0, player=player)
        self.action = {}
        self.status = "ACTIVE"
        self.reward = 0.0


class Env:
    def __init__(self, seed: int):
        self.configuration = AttrDict(
            episodeSteps=720, boardSize=10, startingMoney=3000,
            maxMarketOrdersPerTurn=10, turnsPerDay=24, shedCapacity=100,
            weedSpawnChance=0.005, townShopUnlockInterval=3,
            townShopSellInterval=4, townCenterSellInterval=24,
            seed=seed, farmHandCostMult=1, marketParams={},
        )
        self.info = {}
        self.done = False


def load_engine(engine_path: Path):
    """Load the pinned engine without requiring kaggle_environments installed."""
    package = sys.modules.get("kaggle_environments")
    utils = sys.modules.get("kaggle_environments.utils")
    if package is None:
        package = types.ModuleType("kaggle_environments")
        sys.modules["kaggle_environments"] = package
    if utils is None:
        utils = types.ModuleType("kaggle_environments.utils")
        sys.modules["kaggle_environments.utils"] = utils

    def resolve_episode_seed(env):
        seed = env.info.get("seed")
        if seed is None:
            seed = getattr(env.configuration, "seed", None)
        if seed is None:
            seed = 0
        env.configuration.seed = None
        env.info["seed"] = seed
        return seed

    utils.resolve_episode_seed = resolve_episode_seed
    spec = importlib.util.spec_from_file_location("_deadcap_engine", engine_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _zero_witness(step: int, action: dict) -> dict:
    if step != WITNESS["step"]:
        return action
    result = copy.deepcopy(action)
    result["market"] = [
        [] if row == WITNESS["order"] else row
        for row in result.get("market", [])
    ]
    return result


def replay_pair(engine, own_tape, rival_tape, *, seat: int, seed: int, remove_witness: bool):
    state = [State(0), State(1)]
    env = Env(seed)
    engine.interpreter(state, env)
    capture = {}
    for step in range(719):
        for s in state:
            s.observation.step = step
        own_action = copy.deepcopy(own_tape[step])
        rival_action = copy.deepcopy(rival_tape[step])
        actions = [own_action, rival_action] if seat == 0 else [rival_action, own_action]
        own_index = seat
        if remove_witness:
            actions[own_index] = _zero_witness(step, actions[own_index])
        state[0].action, state[1].action = actions
        if step == WITNESS["step"]:
            private = state[own_index].observation.private
            capture["pre_money"] = float(state[own_index].observation.farms[own_index]["money"])
            capture["pre_melon_seeds"] = private["seeds"].get("MELON", 0)
        engine.interpreter(state, env)
        if step == WITNESS["step"]:
            private = state[own_index].observation.private
            capture["post_money"] = float(state[own_index].observation.farms[own_index]["money"])
            capture["post_melon_seeds"] = private["seeds"].get("MELON", 0)
    own = state[own_index]
    rival = state[1 - own_index]
    capture["terminal_melon_seeds"] = own.observation.private["seeds"].get("MELON", 0)
    return float(own.reward), float(rival.reward), capture


def witness_receipt(tapes, engine) -> dict:
    base_own, base_rival, base_cap = replay_pair(
        engine, tapes[12], tapes[0], seat=0, seed=0, remove_witness=False)
    arm_own, arm_rival, _ = replay_pair(
        engine, tapes[12], tapes[0], seat=0, seed=0, remove_witness=True)
    return {
        "baseline_reward": base_own,
        "arm_reward": arm_own,
        "own_delta": arm_own - base_own,
        "rival_delta": arm_rival - base_rival,
        **base_cap,
    }


def matrix_receipt(tapes, engine, seeds=range(4)) -> dict:
    deltas = []
    rival_deltas = []
    cells = 0
    for seat in (0, 1):
        for seed in seeds:
            for opponent in range(13):
                base_own, base_rival, _ = replay_pair(
                    engine, tapes[12], tapes[opponent], seat=seat, seed=seed,
                    remove_witness=False)
                arm_own, arm_rival, _ = replay_pair(
                    engine, tapes[12], tapes[opponent], seat=seat, seed=seed,
                    remove_witness=True)
                deltas.append(arm_own - base_own)
                rival_deltas.append(arm_rival - base_rival)
                cells += 1
    return {
        "cells": cells,
        "own_delta_min": min(deltas),
        "own_delta_max": max(deltas),
        "own_delta_unique": sorted(set(deltas)),
        "rival_delta_unique": sorted(set(rival_deltas)),
    }


def current_native_probe(runtime_root: Path, engine, tapes, *, seed=0, rival_tape=0) -> dict:
    """Replay the current production entrypoint to the donor witness boundary.

    This is an engagement check only. It does not assume the current controller
    is the donor tape and does not alter the returned action.
    """
    import json
    import time

    module_name = "_deadcap_current_main"
    sys.modules.pop(module_name, None)
    for name in (
        "titan_runtime", "mechanics", "scheduler", "frozen_selected",
        "selected_action_sell", "selected_sell_core",
    ):
        loaded = sys.modules.get(name)
        loaded_file = getattr(loaded, "__file__", "") if loaded is not None else ""
        if loaded_file and str(runtime_root) in str(loaded_file):
            sys.modules.pop(name, None)

    spec = importlib.util.spec_from_file_location(module_name, runtime_root / "main.py")
    current_main = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(current_main)
    current_main._INSTANCE = None

    cfg = json.loads((runtime_root / "TITAN-CONFIG.json").read_text())
    env_cfg = {
        "episodeSteps": 720, "boardSize": 10, "startingMoney": 3000,
        "maxMarketOrdersPerTurn": 10, "turnsPerDay": 24, "shedCapacity": 100,
        "weedSpawnChance": 0.005, "townShopUnlockInterval": 3,
        "townShopSellInterval": 4, "townCenterSellInterval": 24,
        "farmHandCostMult": 1, "marketParams": {},
    }
    state = [State(0), State(1)]
    env = Env(seed)
    engine.interpreter(state, env)
    action284 = None
    started = time.perf_counter()
    old_path = list(sys.path)
    try:
        sys.path.insert(0, str(runtime_root))
        for step in range(WITNESS["step"] + 1):
            for s in state:
                s.observation.step = step
            obs = state[0].observation
            public = {
                "step": step, "player": 0,
                "farms": copy.deepcopy(obs.farms),
                "private": copy.deepcopy(obs.private),
                "market": copy.deepcopy(obs.market),
                "town": copy.deepcopy(obs.town),
                "day": obs.day, "hour": obs.hour,
            }
            own_action = current_main.agent(public, env_cfg)
            if step == WITNESS["step"]:
                action284 = copy.deepcopy(own_action)
            state[0].action = own_action
            state[1].action = copy.deepcopy(tapes[rival_tape][step])
            engine.interpreter(state, env)
    finally:
        sys.path[:] = old_path
    melon = state[0].observation.private["seeds"].get("MELON", 0)
    market = action284.get("market", []) if isinstance(action284, dict) else []
    emits_witness = any(row == WITNESS["order"] for row in market)
    return {
        "seed": seed,
        "seat": 0,
        "rival_tape": rival_tape,
        "step": WITNESS["step"],
        "returned_market": market,
        "emits_witness": emits_witness,
        "post_melon_seeds": melon,
        "elapsed_seconds": time.perf_counter() - started,
        "config_deadcap_key_present": any("deadcap" in str(k).lower() for k in cfg),
    }


def result_bundle(tape_path: Path, engine_path: Path, *, full_matrix=False) -> dict:
    auth = authenticate(tape_path, engine_path)
    tapes = load_tapes(tape_path)
    census = acquisition_census(tapes)
    engine = load_engine(engine_path)
    result = {
        "schema": "titan-v4-deadcap/v1",
        "foundation_artifact_id": FOUNDATION_ARTIFACT_ID,
        "sources": auth,
        "census": census,
        "witness": witness_receipt(tapes, engine),
        "disposition": "DONOR_BUG_CURRENT_NATIVE_ENGAGEMENT_REQUIRED",
    }
    if full_matrix:
        result["matrix"] = matrix_receipt(tapes, engine)
    return result

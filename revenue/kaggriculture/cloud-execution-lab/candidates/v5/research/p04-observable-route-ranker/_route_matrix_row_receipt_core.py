#!/usr/bin/env python3
"""Emit one P04-compatible route-matrix row from one exact native game.

This is an observation-only wrapper around the pinned evaluator: it imports and
SHA-verifies the evaluator, calls its original ``play`` function, and temporarily
wraps ``Actor.act`` only to copy the candidate's public step-144 observation
before delegating exactly once to the original method. The raw/private
observation is never serialized.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
from typing import Any

from p04_route_ranker import (
    canonical_public_snapshot,
    expected_incumbent_plan,
    normalize_row,
    snapshot_sha256,
)

SCHEMA = "titan-v5-route-matrix-row-receipt/v1"
ROUTE_MANIFEST_SCHEMA = "titan-v5-route-matrix-build/v1"
EVALUATOR_SHA256 = "e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c"
LOADER_SHA256 = "61093af280494f95d0f3e5137f716c980ebaf7a2bb53fb333b03566810808e6e"
ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
PRODUCTION_ARCHIVE_SHA256 = "20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239"
ROUTER_SHA256 = "41ea55c5f20c43cd58c5099fbadb212de62ec95a95dfc2e6e1e19c3d4d55b39a"
ROUTER = "r04_full_router.py"
ROUTE_STEP = 144
FINAL_PLAN_STEP = 648
TERMINAL_PLAN = 2
EXPECTED_STEPS = 719
EXPECTED_EPISODE_STEPS = 720


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _plain_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    return _mapping(value, label)


def validate_route_manifest(manifest: Any, forced_plan: int) -> dict[str, Any]:
    manifest = _mapping(manifest, "route manifest")
    if manifest.get("schema") != ROUTE_MANIFEST_SCHEMA:
        raise ValueError("unexpected route manifest schema")
    if manifest.get("baseline_candidate_archive_sha256") != PRODUCTION_ARCHIVE_SHA256:
        raise ValueError("route manifest baseline identity drift")
    if manifest.get("router_before_sha256") != ROUTER_SHA256:
        raise ValueError("route manifest router identity drift")
    if manifest.get("route_step") != ROUTE_STEP:
        raise ValueError("route manifest ROUTE_STEP drift")
    if manifest.get("final_plan_step") != FINAL_PLAN_STEP:
        raise ValueError("route manifest FINAL_PLAN_STEP drift")
    if manifest.get("terminal_plan") != TERMINAL_PLAN:
        raise ValueError("route manifest terminal plan drift")
    if manifest.get("selection_step") != ROUTE_STEP:
        raise ValueError("row recorder only accepts the step-144 matrix")
    if manifest.get("selection_kind") != "shop_pair":
        raise ValueError("route manifest must identify shop_pair selection")
    if manifest.get("plan_index") != forced_plan:
        raise ValueError("route manifest plan does not match requested forced plan")
    if manifest.get("changed_members") != [ROUTER]:
        raise ValueError("step-144 route candidate must change only r04_full_router.py")
    candidate = manifest.get("candidate_archive_sha256")
    if not isinstance(candidate, str) or len(candidate) != 64:
        raise ValueError("route manifest is missing candidate archive SHA256")
    files = _mapping(manifest.get("files"), "route manifest files")
    if files.get(ROUTER) != manifest.get("router_after_sha256"):
        raise ValueError("route manifest router postimage is not bound by files map")
    return manifest


def _farm_counts(farm: Any, label: str) -> tuple[int, dict[str, int], dict[str, int]]:
    farm = _mapping(farm, label)
    farmer = farm.get("farmer")
    hands = farm.get("hands")
    tiles = farm.get("tiles")
    if not isinstance(farmer, (list, tuple)) or len(farmer) != 2:
        raise ValueError(f"{label}.farmer must be one visible coordinate")
    if not isinstance(hands, list):
        raise ValueError(f"{label}.hands must be a visible list")
    if not isinstance(tiles, list) or not tiles:
        raise ValueError(f"{label}.tiles must be a nonempty visible grid")

    animal_counts: dict[str, int] = {}
    crop_counts: dict[str, int] = {}
    width = None
    for y, row in enumerate(tiles):
        if not isinstance(row, list) or not row:
            raise ValueError(f"{label}.tiles[{y}] must be a nonempty row")
        width = len(row) if width is None else width
        if len(row) != width:
            raise ValueError(f"{label}.tiles must be rectangular")
        for cell in row:
            if cell is None or cell == "LOCKED":
                continue
            if not isinstance(cell, dict):
                raise ValueError(f"{label}.tiles contains an unknown visible cell")
            if cell.get("kind") == "PLANT":
                crop = cell.get("crop")
                if not isinstance(crop, str) or not crop:
                    raise ValueError(f"{label}.tiles has malformed visible crop")
                crop_counts[crop] = crop_counts.get(crop, 0) + 1
            if "animal" in cell:
                animal = cell.get("animal")
                if not isinstance(animal, str) or not animal:
                    raise ValueError(f"{label}.tiles has malformed visible animal")
                animal_counts[animal] = animal_counts.get(animal, 0) + 1
    return 1 + len(hands), dict(sorted(animal_counts.items())), dict(sorted(crop_counts.items()))


def public_step144_snapshot(observation: Any) -> dict[str, Any]:
    observation = _mapping(observation, "observation")
    if observation.get("step") != ROUTE_STEP:
        raise ValueError("snapshot observation must be exactly step 144")
    player = _plain_int(observation.get("player"), "observation.player")
    if player not in (0, 1):
        raise ValueError("observation.player must be 0 or 1")

    farms = observation.get("farms")
    if not isinstance(farms, list) or len(farms) != 2:
        raise ValueError("observation.farms must contain exactly two public farms")
    own_farm = _mapping(farms[player], "own farm")
    rival_farm = _mapping(farms[1 - player], "rival farm")
    own_workers, own_animals, own_crops = _farm_counts(own_farm, "own farm")
    _, rival_animals, rival_crops = _farm_counts(rival_farm, "rival farm")

    market = _mapping(observation.get("market"), "observation.market")
    prices = _mapping(market.get("prices"), "observation.market.prices")
    inventory = _mapping(market.get("inventory"), "observation.market.inventory")
    town = _mapping(observation.get("town"), "observation.town")
    shops = town.get("unlocked_shops")
    if not isinstance(shops, list) or len(shops) < 2:
        raise ValueError("step-144 town must expose at least two unlocked shops")
    first_two = shops[:2]
    if not all(isinstance(shop, str) and shop for shop in first_two):
        raise ValueError("first two shops must be nonempty strings")

    snapshot = {
        "first_two_shops": list(first_two),
        "market": {"prices": dict(prices), "inventory": dict(inventory)},
        "own": {
            "cash": _finite(own_farm.get("money"), "own farm money"),
            "worker_count": own_workers,
            "animal_counts": own_animals,
            "crop_counts": own_crops,
        },
        "rival": {
            "animal_counts": rival_animals,
            "crop_counts": rival_crops,
        },
        "incumbent_plan": expected_incumbent_plan(first_two),
    }
    # This normalizer also proves that no private/future fields escaped.
    return canonical_public_snapshot(snapshot)


def _import_exact_evaluator(path: Path):
    actual = sha256_file(path)
    if actual != EVALUATOR_SHA256:
        raise ValueError(f"evaluator identity drift: {actual}")
    spec = importlib.util.spec_from_file_location("titan_route_row_exact_evaluator", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot import pinned evaluator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if getattr(module, "ENGINE_REF", None) != ENGINE_REF:
        raise ValueError("evaluator ENGINE_REF drift")
    if not hasattr(module, "Actor") or not callable(getattr(module, "play", None)):
        raise ValueError("pinned evaluator API drift")
    return module


def play_with_public_snapshot(
    evaluator: Any,
    engine: Any,
    specs: list[str],
    cache: Path,
    loader: Path,
    seed: int,
    candidate_seat: int,
    rng_seed: int,
    action_timeout: float,
    startup_timeout: float,
    game_timeout: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call exact evaluator.play once while observing candidate input at step 144."""
    if candidate_seat not in (0, 1):
        raise ValueError("candidate_seat must be 0 or 1")
    original = evaluator.Actor.act
    captures: list[dict[str, Any]] = []
    capture_errors: list[str] = []

    def observed_act(actor, observation, configuration, timeout):
        try:
            if (
                isinstance(observation, dict)
                and observation.get("step") == ROUTE_STEP
                and observation.get("player") == candidate_seat
            ):
                captures.append(public_step144_snapshot(observation))
        except Exception as exc:  # Evidence failure must not perturb scoring.
            capture_errors.append(f"{type(exc).__name__}: {exc}")
        return original(actor, observation, configuration, timeout)

    evaluator.Actor.act = observed_act
    try:
        game = evaluator.play(
            engine,
            specs,
            cache,
            loader,
            seed,
            candidate_seat,
            rng_seed,
            action_timeout,
            startup_timeout,
            game_timeout,
        )
    finally:
        evaluator.Actor.act = original

    if capture_errors:
        raise ValueError("step-144 capture failed: " + "; ".join(capture_errors))
    if len(captures) != 1:
        raise ValueError(f"expected exactly one candidate step-144 capture, got {len(captures)}")
    return game, captures[0]


def _validate_complete_game(game: Any, seed: int, seat: int) -> tuple[float, float]:
    game = _mapping(game, "game result")
    if game.get("seed") != seed or game.get("candidate_seat") != seat:
        raise ValueError("game identity does not match requested cell")
    if game.get("status") != "complete" or game.get("failure") is not None:
        raise ValueError("row publication requires a completed failure-free game")
    if game.get("steps") != EXPECTED_STEPS or game.get("episode_steps") != EXPECTED_EPISODE_STEPS:
        raise ValueError("row publication requires the exact 719/720 native horizon")
    scores = game.get("scores")
    if not isinstance(scores, list) or len(scores) != 2:
        raise ValueError("completed game must contain two scores")
    values = [_finite(value, f"scores[{i}]") for i, value in enumerate(scores)]
    return values[seat], values[1 - seat]


def _entry_fingerprint(evaluator: Any, spec: str, expected_sha: str, label: str) -> dict[str, Any]:
    fp = evaluator.fingerprint(spec)
    if fp.get("sha256") != expected_sha:
        raise ValueError(f"{label} entry SHA256 drift")
    return fp


def make_row(
    manifest: dict[str, Any],
    forced_plan: int,
    seed: int,
    opponent: str,
    seat: int,
    snapshot: dict[str, Any],
    game: dict[str, Any],
) -> dict[str, Any]:
    validate_route_manifest(manifest, forced_plan)
    own, rival = _validate_complete_game(game, seed, seat)
    row = {
        "seed": seed,
        "opponent": opponent,
        "seat": seat,
        "forced_plan": forced_plan,
        "snapshot": snapshot,
        "snapshot_sha256": snapshot_sha256(snapshot),
        "terminal_own": own,
        "terminal_rival": rival,
        "terminal_margin": own - rival,
        "failures": [],
    }
    return normalize_row(row)


def _reserve_pair(row_path: Path, receipt_path: Path):
    if row_path.resolve(strict=False) == receipt_path.resolve(strict=False):
        raise ValueError("row and receipt paths must differ")
    row_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    opened = []
    try:
        for path in (row_path, receipt_path):
            handle = path.open("x", encoding="utf-8")
            opened.append((path, handle, os.fstat(handle.fileno())))
        return opened
    except Exception:
        for _, handle, _ in opened:
            handle.close()
        for path, _, stat in opened:
            try:
                current = path.stat()
                if current.st_dev == stat.st_dev and current.st_ino == stat.st_ino:
                    path.unlink()
            except FileNotFoundError:
                pass
        raise


def _publish_pair(row_path: Path, receipt_path: Path, row: dict[str, Any], receipt: dict[str, Any]) -> None:
    opened = _reserve_pair(row_path, receipt_path)
    success = False
    try:
        payloads = (
            json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
            json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        )
        for (_, handle, _), payload in zip(opened, payloads):
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        success = True
    finally:
        for _, handle, _ in opened:
            handle.close()
        if not success:
            for path, _, stat in opened:
                try:
                    current = path.stat()
                    if current.st_dev == stat.st_dev and current.st_ino == stat.st_ino:
                        path.unlink()
                except FileNotFoundError:
                    pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluator", type=Path, required=True)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--loader", type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--candidate-entry-sha256", required=True)
    parser.add_argument("--route-manifest", type=Path, required=True)
    parser.add_argument("--opponent-label", required=True)
    parser.add_argument("--opponent", required=True)
    parser.add_argument("--opponent-entry-sha256", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--seat", type=int, choices=(0, 1), required=True)
    parser.add_argument("--plan-index", type=int, choices=range(13), required=True)
    parser.add_argument("--rng-seed", type=int, default=20260912)
    parser.add_argument("--action-timeout", type=float, default=1.25)
    parser.add_argument("--startup-timeout", type=float, default=10.0)
    parser.add_argument("--game-timeout", type=float, default=900.0)
    parser.add_argument("--row-out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    args = parser.parse_args()

    manifest = validate_route_manifest(
        _load_json(args.route_manifest, "route manifest"), args.plan_index
    )
    if sha256_file(args.loader) != LOADER_SHA256:
        raise ValueError("loader identity drift")
    evaluator = _import_exact_evaluator(args.evaluator)
    candidate = evaluator.resolve_spec(args.candidate)
    opponent_spec = evaluator.resolve_spec(args.opponent)
    candidate_fp_before = _entry_fingerprint(
        evaluator, candidate, args.candidate_entry_sha256, "candidate"
    )
    opponent_fp_before = _entry_fingerprint(
        evaluator, opponent_spec, args.opponent_entry_sha256, "opponent"
    )

    engine, engine_hashes = evaluator.get_engine(args.engine_dir, args.loader)
    pair = [candidate, opponent_spec] if args.seat == 0 else [opponent_spec, candidate]
    game, snapshot = play_with_public_snapshot(
        evaluator,
        engine,
        pair,
        args.engine_dir,
        args.loader,
        args.seed,
        args.seat,
        args.rng_seed,
        args.action_timeout,
        args.startup_timeout,
        args.game_timeout,
    )
    candidate_fp_after = _entry_fingerprint(
        evaluator, candidate, args.candidate_entry_sha256, "candidate"
    )
    opponent_fp_after = _entry_fingerprint(
        evaluator, opponent_spec, args.opponent_entry_sha256, "opponent"
    )
    if candidate_fp_after != candidate_fp_before or opponent_fp_after != opponent_fp_before:
        raise ValueError("entry fingerprint changed during native game")

    row = make_row(
        manifest,
        args.plan_index,
        args.seed,
        args.opponent_label,
        args.seat,
        snapshot,
        game,
    )
    receipt = {
        "schema": SCHEMA,
        "route_candidate_archive_sha256": manifest["candidate_archive_sha256"],
        "baseline_candidate_archive_sha256": PRODUCTION_ARCHIVE_SHA256,
        "forced_plan": args.plan_index,
        "selection_step": ROUTE_STEP,
        "evaluator_sha256": EVALUATOR_SHA256,
        "loader_sha256": LOADER_SHA256,
        "engine_ref": ENGINE_REF,
        "engine_sha256": engine_hashes,
        "candidate": candidate_fp_after,
        "opponent_label": args.opponent_label,
        "opponent": opponent_fp_after,
        "seed": args.seed,
        "seat": args.seat,
        "rng_seed": args.rng_seed,
        "snapshot_sha256": row["snapshot_sha256"],
        "game_trace_sha256": game.get("trace_sha256"),
        "steps": game.get("steps"),
        "episode_steps": game.get("episode_steps"),
        "private_observation_persisted": False,
        "p04_row_sha256": hashlib.sha256(
            json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest(),
    }
    _publish_pair(args.row_out, args.receipt_out, row, receipt)
    print(json.dumps({
        "seed": args.seed,
        "opponent": args.opponent_label,
        "seat": args.seat,
        "forced_plan": args.plan_index,
        "snapshot_sha256": row["snapshot_sha256"],
        "terminal_margin": row["terminal_margin"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

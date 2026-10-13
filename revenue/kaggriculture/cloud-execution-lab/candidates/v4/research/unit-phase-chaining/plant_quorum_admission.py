#!/usr/bin/env python3
"""Default-OFF relief for Kaggriculture atomic same-crop PLANT collateral.

The official engine pre-counts every authored PLANT row for each crop before it
checks actor existence or tile legality.  If demand exceeds available seeds,
*all* PLANT rows for that crop are replaced by PASS for the callback.

This helper is deliberately narrower than a general plant scheduler.  It only
removes authored PLANT rows that are source-certain no-ops because the actor is
missing or is the sole actor on a non-empty/LOCKED tile.  It engages only when
removing those poison rows alone restores demand <= observed seeds and at least
one remaining authored PLANT is guaranteed legal on a unique empty tile.  It
never chooses among competing legal plants, reorders actors, invents a crop,
or changes non-PLANT/market rows.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
from pathlib import Path
from typing import Any, Mapping

EXPECTED_ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
HERE = Path(__file__).resolve()
V4_ROOT = HERE.parents[2]
ENGINE_PATH = V4_ROOT.parent.parent / "reference" / "engine" / "kaggriculture.py"


class PlantQuorumError(RuntimeError):
    pass


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def verify_engine_source(path: Path = ENGINE_PATH) -> dict[str, str]:
    actual = git_blob_sha(path)
    if actual != EXPECTED_ENGINE_BLOB:
        raise PlantQuorumError(
            f"engine drift: expected {EXPECTED_ENGINE_BLOB}, got {actual}"
        )
    source = path.read_text(encoding="utf-8")
    markers = (
        "# Atomic PLANT validation: if total PLANT requests for a crop this turn",
        'plant_demand[a[1]] = plant_demand.get(a[1], 0) + 1',
        'blocked = {crop for crop, n in plant_demand.items() if n > seeds.get(crop, 0)}',
        'if isinstance(a, list) and len(a) >= 2 and a[0] == "PLANT" and a[1] in blocked:',
        'return ["PASS"]',
    )
    missing = [marker for marker in markers if marker not in source]
    if missing:
        raise PlantQuorumError(f"engine atomic-PLANT markers drifted: {missing!r}")
    return {"engine_blob": actual, "modeled_rule": "callback-wide same-crop PLANT preflight"}


def _source_rows(action: Mapping[str, Any]) -> tuple[list[Any], list[Any]]:
    farmer = action.get("farmer", ["PASS"])
    hands = action.get("hands", [])
    if not isinstance(hands, list):
        hands = []
    return [farmer, *hands], hands


def effective_rows_under_engine_preflight(rows: list[Any], seeds: Mapping[str, Any]) -> list[Any]:
    """Mirror only the engine's callback-wide atomic PLANT preflight."""
    demand: Counter[str] = Counter()
    for row in rows:
        if isinstance(row, list) and len(row) >= 2 and row[0] == "PLANT":
            crop = row[1]
            if not isinstance(crop, str):
                raise PlantQuorumError(f"malformed PLANT crop: {crop!r}")
            demand[crop] += 1
    blocked: set[str] = set()
    for crop, count in demand.items():
        available = seeds.get(crop, 0)
        if isinstance(available, bool) or not isinstance(available, int) or available < 0:
            raise PlantQuorumError(f"malformed seed count for {crop}: {available!r}")
        if count > available:
            blocked.add(crop)
    return [
        ["PASS"]
        if isinstance(row, list)
        and len(row) >= 2
        and row[0] == "PLANT"
        and isinstance(row[1], str)
        and row[1] in blocked
        else copy.deepcopy(row)
        for row in rows
    ]


def _normalize_context(obs: Mapping[str, Any], action: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(obs, Mapping) or not isinstance(action, Mapping):
        raise PlantQuorumError("obs and action must be mappings")
    player = obs.get("player", 0)
    farms = obs.get("farms")
    private = obs.get("private")
    if isinstance(player, bool) or not isinstance(player, int) or player < 0:
        raise PlantQuorumError(f"invalid player {player!r}")
    if not isinstance(farms, list) or player >= len(farms) or not isinstance(farms[player], Mapping):
        raise PlantQuorumError("missing player farm")
    if not isinstance(private, Mapping):
        raise PlantQuorumError("missing private state")
    farm = farms[player]
    tiles = farm.get("tiles")
    if not isinstance(tiles, list) or not tiles or not all(isinstance(row, list) for row in tiles):
        raise PlantQuorumError("malformed farm tiles")
    height = len(tiles)
    width = len(tiles[0])
    if width <= 0 or any(len(row) != width for row in tiles):
        raise PlantQuorumError("ragged farm tiles")
    farmer = farm.get("farmer")
    hands = farm.get("hands", [])
    if not isinstance(hands, list):
        raise PlantQuorumError("malformed farm hands")
    positions_raw = [farmer, *hands]
    positions: list[tuple[int, int] | None] = []
    for raw in positions_raw:
        if (
            not isinstance(raw, (list, tuple))
            or len(raw) < 2
            or isinstance(raw[0], bool)
            or isinstance(raw[1], bool)
            or not isinstance(raw[0], int)
            or not isinstance(raw[1], int)
        ):
            raise PlantQuorumError(f"malformed actor position {raw!r}")
        x, y = raw[0], raw[1]
        if not (0 <= x < width and 0 <= y < height):
            raise PlantQuorumError(f"actor position out of bounds {(x, y)!r}")
        positions.append((x, y))
    seeds = private.get("seeds", {})
    if not isinstance(seeds, Mapping):
        raise PlantQuorumError("malformed private seeds")
    rows, hands_actions = _source_rows(action)
    return {
        "farm": farm,
        "tiles": tiles,
        "seeds": seeds,
        "rows": rows,
        "hands_actions": hands_actions,
        "positions": positions,
    }


def _classify_plant_row(
    actor: int,
    positions: list[tuple[int, int] | None],
    occupancy: Counter[tuple[int, int]],
    tiles: list[list[Any]],
) -> tuple[str, list[int] | None]:
    if actor >= len(positions) or positions[actor] is None:
        return "SOURCE_CERTAIN_NOOP_MISSING_ACTOR", None
    x, y = positions[actor]
    position = (x, y)
    if occupancy[position] != 1:
        return "AMBIGUOUS_COLOCATED", [x, y]
    tile = tiles[y][x]
    if tile is None:
        return "GUARANTEED_LEGAL_UNIQUE_EMPTY", [x, y]
    return "SOURCE_CERTAIN_NOOP_UNIQUE_NONEMPTY", [x, y]


def relieve_atomic_plant_collateral(
    obs: Mapping[str, Any],
    action: Mapping[str, Any],
    *,
    enabled: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pass only source-certain poison PLANT rows to restore the engine quorum.

    Fail-closed: malformed context returns exact source action semantics with an
    error report rather than guessing.  `enabled=False` always returns unchanged
    action content.
    """
    source = copy.deepcopy(dict(action)) if isinstance(action, Mapping) else action
    base_report: dict[str, Any] = {
        "schema": "titan-v4-plantquorum-admission-v1",
        "enabled": bool(enabled),
        "decision_authority": False,
        "changed": False,
        "changed_actors": [],
        "crops": [],
        "error": None,
    }
    if not enabled:
        return copy.deepcopy(source), base_report

    try:
        ctx = _normalize_context(obs, action)
        rows = ctx["rows"]
        seeds = ctx["seeds"]
        positions = ctx["positions"]
        occupancy: Counter[tuple[int, int]] = Counter(
            position for position in positions if position is not None
        )
        demand: Counter[str] = Counter()
        crop_rows: dict[str, list[int]] = {}
        for actor, row in enumerate(rows):
            if not (isinstance(row, list) and len(row) >= 2 and row[0] == "PLANT"):
                continue
            crop = row[1]
            if not isinstance(crop, str):
                raise PlantQuorumError(f"malformed PLANT crop: {crop!r}")
            demand[crop] += 1
            crop_rows.setdefault(crop, []).append(actor)

        rewrites: dict[int, list[str]] = {}
        crop_reports: list[dict[str, Any]] = []
        for crop in sorted(crop_rows):
            available = seeds.get(crop, 0)
            if isinstance(available, bool) or not isinstance(available, int) or available < 0:
                raise PlantQuorumError(f"malformed seed count for {crop}: {available!r}")
            actors = crop_rows[crop]
            if demand[crop] <= available:
                crop_reports.append(
                    {
                        "crop": crop,
                        "demand_before": demand[crop],
                        "available_seeds": available,
                        "status": "NOT_BLOCKED",
                        "rows": [],
                    }
                )
                continue

            classified = []
            poison: list[int] = []
            guaranteed: list[int] = []
            for actor in actors:
                kind, position = _classify_plant_row(
                    actor, positions, occupancy, ctx["tiles"]
                )
                classified.append({"actor": actor, "classification": kind, "position": position})
                if kind.startswith("SOURCE_CERTAIN_NOOP_"):
                    poison.append(actor)
                elif kind == "GUARANTEED_LEGAL_UNIQUE_EMPTY":
                    guaranteed.append(actor)

            remaining = demand[crop] - len(poison)
            if poison and guaranteed and remaining <= available:
                for actor in poison:
                    rewrites[actor] = ["PASS"]
                status = "RELIEVE_SOURCE_CERTAIN_POISON"
            elif not poison:
                status = "BLOCKED_NO_SOURCE_CERTAIN_POISON"
            elif not guaranteed:
                status = "BLOCKED_NO_GUARANTEED_LEGAL_SURVIVOR"
            else:
                status = "BLOCKED_POISON_REMOVAL_INSUFFICIENT"
            crop_reports.append(
                {
                    "crop": crop,
                    "demand_before": demand[crop],
                    "available_seeds": available,
                    "poison_rows": poison,
                    "guaranteed_legal_rows": guaranteed,
                    "remaining_demand_after_poison_removal": remaining,
                    "status": status,
                    "rows": classified,
                }
            )

        result = copy.deepcopy(dict(action))
        farmer = copy.deepcopy(result.get("farmer", ["PASS"]))
        hands = result.get("hands", [])
        if not isinstance(hands, list):
            hands = []
        hands = copy.deepcopy(hands)
        for actor, replacement in sorted(rewrites.items()):
            if actor == 0:
                farmer = replacement
            else:
                hand_index = actor - 1
                if hand_index < len(hands):
                    hands[hand_index] = replacement
        if rewrites:
            result["farmer"] = farmer
            result["hands"] = hands

        base_report.update(
            {
                "changed": bool(rewrites),
                "changed_actors": sorted(rewrites),
                "crops": crop_reports,
            }
        )
        return result, base_report
    except PlantQuorumError as exc:
        base_report["error"] = str(exc)
        return copy.deepcopy(source), base_report

# SPDX-License-Identifier: Apache-2.0
"""TEST-ONLY current-runtime entry for the default-OFF HYDRA water-skip helper.

This execution fixture delegates every callback to the unmodified native
``main.py::agent`` first, then optionally applies the exact source-bound HYDRA
helper.  It is copied beside an authenticated disposable runtime package only;
it is not production wiring and never mutates production configuration.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
MODE_PATH = ROOT / "HYDRA-FIELD-MODE.json"
TELEMETRY_PATH = ROOT / "HYDRA-FIELD-TELEMETRY.json"
_parent = None
_helper = None
_mode = None

stats = {
    "callbacks": 0,
    "enabled": None,
    "authored_water_rows": 0,
    "authored_water_by_crop": {},
    "eligible_rows": 0,
    "eligible_by_crop": {},
    "eligible_by_day": {},
    "eligible_by_hour": {},
    "transformed_actions": 0,
    "rewritten_rows": 0,
    "first_change_step": None,
    "last_change_step": None,
    "prior_streak_blocks": 0,
    "fertilizer_bonus_blocks": 0,
    "followup_next_day_water": 0,
    "weed_after_rewrite": 0,
    "missing_or_replaced_after_rewrite": 0,
    "rewrite_events": [],
}
_open_events = []


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _ensure_loaded():
    global _parent, _helper
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    if _parent is None:
        _parent = _load("hydra_native_parent", ROOT / "main.py")
    if _helper is None:
        _helper = _load("hydra_source_helper_runtime", ROOT / "ongoing_water_skip.py")


def _cfg(configuration, name: str, default=None):
    if isinstance(configuration, dict):
        return configuration.get(name, default)
    return getattr(configuration, name, default)


def _mode_config() -> dict:
    global _mode
    if _mode is not None:
        return _mode
    try:
        payload = json.loads(MODE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"missing or invalid HYDRA field mode file: {exc}") from exc
    if (not isinstance(payload, dict)
            or payload.get("schema") != "titan.v4.hydra.field-mode.v1"
            or type(payload.get("enabled")) is not bool
            or set(payload) != {"schema", "enabled"}):
        raise RuntimeError("invalid HYDRA field mode schema")
    _mode = payload
    return _mode


def _enabled() -> bool:
    return _mode_config()["enabled"]


def _inc_mapping(name: str, key, delta: int = 1) -> None:
    mapping = stats[name]
    key = str(key)
    mapping[key] = mapping.get(key, 0) + delta


def _action_rows(action):
    if not isinstance(action, dict):
        return []
    hands = action.get("hands")
    if not isinstance(hands, list):
        return []
    return [action.get("farmer"), *hands]


def _water_sites(action, observation):
    """Return authored WATER rows with actor/site/tile metadata, fail closed."""
    if not isinstance(action, dict) or not isinstance(observation, dict):
        return []
    player = observation.get("player")
    farms = observation.get("farms")
    if type(player) is not int or player not in (0, 1) or not isinstance(farms, list) or len(farms) != 2:
        return []
    farm = farms[player]
    if not isinstance(farm, dict):
        return []
    hands = farm.get("hands")
    tiles = farm.get("tiles")
    if not isinstance(hands, list) or not isinstance(tiles, list):
        return []
    positions = [farm.get("farmer"), *hands]
    rows = _action_rows(action)
    if len(rows) != len(positions):
        return []
    result = []
    for actor, (position, row) in enumerate(zip(positions, rows)):
        if row != ["WATER"]:
            continue
        if (not isinstance(position, list) or len(position) != 2
                or any(type(v) is not int or not 0 <= v < 10 for v in position)):
            continue
        x, y = position
        if y >= len(tiles) or not isinstance(tiles[y], list) or x >= len(tiles[y]):
            continue
        result.append({"actor": actor, "site": [x, y], "tile": tiles[y][x]})
    return result


def _classify_block(tile, day: int) -> str | None:
    """Classify only the two explicit HYDRA handoff blockers, without eligibility claims."""
    if not isinstance(tile, dict) or tile.get("kind") != "PLANT":
        return None
    crop = tile.get("crop")
    if crop not in getattr(_helper, "CROPS", {}):
        return None
    spec = _helper.CROPS[crop]
    placed = tile.get("planted_day")
    watered = tile.get("watered_today")
    streak = tile.get("consecutive_unwatered")
    units = tile.get("yield_units")
    fertilized_until = tile.get("fertilized_until_day")
    if (type(placed) is not int or not 0 <= placed < day
            or type(watered) is not bool or watered
            or type(streak) is not int
            or type(units) is not int or not 0 <= units <= spec["max_yield"]
            or type(fertilized_until) is not int):
        return None
    if streak != 0:
        return "prior_streak"
    if (_helper._production_due(tile, day, spec)
            and fertilized_until >= day and units < spec["max_yield"]):
        return "fertilizer_bonus"
    return None


def _tile_for_site(observation, site):
    try:
        player = observation["player"]
        x, y = site
        return observation["farms"][player]["tiles"][y][x]
    except (KeyError, IndexError, TypeError):
        return None


def _observe_followups(parent, observation, day: int, water_sites) -> None:
    water_set = {tuple(row["site"]) for row in water_sites}
    keep = []
    for event in _open_events:
        target_day = event["rewrite_day"] + 1
        if day < target_day:
            keep.append(event)
            continue
        if day == target_day:
            site = event["site"]
            tile = _tile_for_site(observation, site)
            if not event["state_checked"]:
                if isinstance(tile, dict) and tile.get("kind") == "WEED":
                    stats["weed_after_rewrite"] += 1
                    event["weed_after_rewrite"] = True
                elif not (isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == event["crop"]):
                    stats["missing_or_replaced_after_rewrite"] += 1
                    event["missing_or_replaced"] = True
                event["state_checked"] = True
            if tuple(site) in water_set and not event["followup_water"]:
                stats["followup_next_day_water"] += 1
                event["followup_water"] = True
            keep.append(event)
            continue
        if day == target_day + 1:
            # The second EOD is where a missed recovery WATER can turn streak 1
            # into the engine's >=2 terminal plant-loss transition.
            site = event["site"]
            tile = _tile_for_site(observation, site)
            if isinstance(tile, dict) and tile.get("kind") == "WEED":
                if not event["weed_after_rewrite"]:
                    stats["weed_after_rewrite"] += 1
                event["weed_after_rewrite"] = True
            elif not (isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == event["crop"]):
                if not event["missing_or_replaced"]:
                    stats["missing_or_replaced_after_rewrite"] += 1
                event["missing_or_replaced"] = True
            event["post_next_day_state_checked"] = True
            event["closed"] = True
            continue
        event["closed"] = True
    _open_events[:] = keep


def _write_telemetry() -> None:
    try:
        payload = dict(stats)
        payload["open_rewrite_events"] = [dict(event) for event in _open_events]
        payload["unresolved_rewrite_events"] = len(_open_events)
        path = Path(TELEMETRY_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    except Exception:
        # Telemetry must never affect the returned action.
        pass


def agent(observation, configuration=None):
    _ensure_loaded()
    enabled = _enabled()
    if stats["enabled"] is None:
        stats["enabled"] = enabled
    elif stats["enabled"] is not enabled:
        raise RuntimeError("HYDRA field mode changed within one actor process")

    parent = _parent.agent(observation, configuration)
    stats["callbacks"] += 1
    step = observation.get("step") if isinstance(observation, dict) else getattr(observation, "step", None)
    day = step // 24 if type(step) is int else -1
    hour = step % 24 if type(step) is int else -1

    waters = _water_sites(parent, observation)
    _observe_followups(parent, observation, day, waters)
    for authored in waters:
        stats["authored_water_rows"] += 1
        tile = authored["tile"]
        crop = tile.get("crop") if isinstance(tile, dict) else "NON_PLANT"
        _inc_mapping("authored_water_by_crop", crop)
        reason = _classify_block(tile, day)
        if reason == "prior_streak":
            stats["prior_streak_blocks"] += 1
        elif reason == "fertilizer_bonus":
            stats["fertilizer_bonus_blocks"] += 1

    plans = _helper.plan_ongoing_water_skip(parent, observation, configuration)
    stats["eligible_rows"] += len(plans)
    for plan in plans:
        _inc_mapping("eligible_by_crop", plan.get("crop", "UNKNOWN"))
        _inc_mapping("eligible_by_day", day)
        _inc_mapping("eligible_by_hour", hour)

    candidate = _helper.apply_ongoing_water_skip(
        parent, observation, configuration, enabled=enabled)
    if candidate != parent:
        stats["transformed_actions"] += 1
        before_rows = _action_rows(parent)
        after_rows = _action_rows(candidate)
        stats["rewritten_rows"] += sum(a != b for a, b in zip(before_rows, after_rows))
        stats["last_change_step"] = step
        if stats["first_change_step"] is None:
            stats["first_change_step"] = step
        for plan in plans:
            event = {
                "rewrite_step": step,
                "rewrite_day": day,
                "site": list(plan["site"]),
                "crop": plan["crop"],
                "production_due": bool(plan["production_due"]),
                "followup_water": False,
                "weed_after_rewrite": False,
                "missing_or_replaced": False,
                "state_checked": False,
                "post_next_day_state_checked": False,
                "closed": False,
            }
            _open_events.append(event)
            # Keep a bounded admission sample in the telemetry body.
            if len(stats["rewrite_events"]) < 128:
                stats["rewrite_events"].append(event)

    episode_steps = _cfg(configuration, "episodeSteps", 720)
    if type(step) is int and type(episode_steps) is int and step >= episode_steps - 2:
        _write_telemetry()
    return candidate

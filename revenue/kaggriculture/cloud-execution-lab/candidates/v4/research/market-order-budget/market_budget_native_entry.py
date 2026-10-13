# SPDX-License-Identifier: Apache-2.0
"""TEST-ONLY telemetry wrapper around the authenticated current native agent.

It returns the parent's action *unchanged*. Telemetry describes only raw market
queue pressure against the engine cap; telemetry failures are swallowed so this
fixture cannot alter gameplay through its reporting path. Evidence consumers
must require every attempted callback to have one successful telemetry record.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
TELEMETRY_PATH = os.environ.get("ORDERBUDGET_TELEMETRY_PATH")
_parent = None
_budget = None
stats = {
    "callback_attempts": 0,
    "callbacks": 0,
    "telemetry_errors": 0,
    "max_raw_rows": 0,
    "max_active_slot": None,
    "structural_overflow_callbacks": 0,
    "dropped_nonempty_callbacks": 0,
    "dropped_nonempty_rows": 0,
    "no_admission_slot_callbacks": 0,
    "raw_rows_histogram": {},
    "active_rows_histogram": {},
    "first_structural_overflow_step": None,
    "first_dropped_nonempty_step": None,
    "first_no_admission_slot_step": None,
    "witnesses": [],
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _ensure_loaded():
    global _parent, _budget
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    if _parent is None:
        _parent = _load("orderbudget_native_parent", ROOT / "main.py")
    if _budget is None:
        _budget = _load("orderbudget_helper", ROOT / "market_order_budget.py")


def _get(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def _bump(hist: dict, value: int) -> None:
    key = str(value)
    hist[key] = hist.get(key, 0) + 1


def _record(step, action, configuration) -> None:
    # Count the attempt before any telemetry operation that can fail. The
    # wrapper remains gameplay-inert on telemetry failure, while the census
    # can now fail closed instead of silently publishing incomplete evidence.
    stats["callback_attempts"] += 1
    try:
        raw_cap = _get(configuration, "maxMarketOrdersPerTurn", 10)
        cap = max(1, int(raw_cap))
        row = _budget.analyze_action(action, cap)
        stats["callbacks"] += 1
        stats["max_raw_rows"] = max(stats["max_raw_rows"], row["raw_rows"])
        if row["last_active_slot"] is not None:
            old = stats["max_active_slot"]
            stats["max_active_slot"] = row["last_active_slot"] if old is None else max(old, row["last_active_slot"])
        _bump(stats["raw_rows_histogram"], row["raw_rows"])
        _bump(stats["active_rows_histogram"], row["active_rows"])
        stats["structural_overflow_callbacks"] += int(row["structural_overflow"])
        stats["dropped_nonempty_callbacks"] += int(row["dropped_nonempty_count"] > 0)
        stats["dropped_nonempty_rows"] += row["dropped_nonempty_count"]
        stats["no_admission_slot_callbacks"] += int(not row["has_admission_slot"])
        if row["structural_overflow"] and stats["first_structural_overflow_step"] is None:
            stats["first_structural_overflow_step"] = step
        if row["dropped_nonempty_count"] and stats["first_dropped_nonempty_step"] is None:
            stats["first_dropped_nonempty_step"] = step
        if not row["has_admission_slot"] and stats["first_no_admission_slot_step"] is None:
            stats["first_no_admission_slot_step"] = step
        if len(stats["witnesses"]) < 24 and (row["structural_overflow"] or not row["has_admission_slot"]):
            stats["witnesses"].append({
                "step": step,
                "cap": cap,
                "raw_rows": row["raw_rows"],
                "active_rows": row["active_rows"],
                "admission_slot": row["admission_slot"],
                "dropped_nonempty": row["dropped_nonempty"],
            })
    except Exception:
        stats["telemetry_errors"] += 1


def _write() -> None:
    if not TELEMETRY_PATH:
        return
    try:
        path = Path(TELEMETRY_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stats, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    except Exception:
        pass


def agent(observation, configuration=None):
    _ensure_loaded()
    parent = _parent.agent(observation, configuration)
    step = _get(observation, "step")
    _record(step, parent, configuration)
    episode_steps = _get(configuration, "episodeSteps", 720)
    if type(step) is int and type(episode_steps) is int and step >= episode_steps - 2:
        _write()
    return parent

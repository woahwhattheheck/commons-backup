# SPDX-License-Identifier: Apache-2.0
"""Executable P01 wrapper around the unchanged exact-current TITAN entrypoint."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import main as _canonical
import mechanics as _mechanics
from opening_turnover import MODES, prioritize_opening_seeds

MODE = os.environ.get("P01_MODE", "annual").strip().lower()
MAX_DAY = int(os.environ.get("P01_MAX_DAY", "10"))
TRACE_FRONTIERS = os.environ.get("P01_TRACE_FRONTIERS", "1").strip().lower() not in {"0", "false", "no"}
if MODE not in MODES:
    raise ValueError(f"unsupported P01_MODE={MODE!r}")


def _digest(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _has_seed_frontier(action) -> bool:
    market = action.get("market") if isinstance(action, dict) else None
    if not isinstance(market, list):
        return False
    positive = 0
    for row in market:
        if (isinstance(row, list) and len(row) >= 3 and row[0] == "BUY_SEED"
                and isinstance(row[2], int) and not isinstance(row[2], bool) and row[2] > 0):
            positive += 1
            if positive >= 2:
                return True
    return False


def _cell_identity() -> dict:
    """Source-bound cell identity supplied by the hosted screen runner."""
    seed_raw = os.environ.get("P01_CELL_SEED", "").strip()
    seat_raw = os.environ.get("P01_CELL_SEAT", "").strip()
    label = os.environ.get("P01_CELL_LABEL", "").strip()
    out: dict = {}
    if seed_raw:
        try:
            out["seed"] = int(seed_raw)
        except ValueError:
            out["seed"] = seed_raw
    if seat_raw:
        try:
            out["candidate_seat"] = int(seat_raw)
        except ValueError:
            out["candidate_seat"] = seat_raw
    if label:
        out["label"] = label
    return out


def _emit(observation, before, after, report) -> None:
    day = report.get("day")
    audit_frontier = (TRACE_FRONTIERS and isinstance(day, int) and not isinstance(day, bool)
                      and 0 <= day <= MAX_DAY and _has_seed_frontier(before))
    if not report.get("changed") and not audit_frontier:
        return
    directory = Path(os.environ.get("P01_TRACE_DIR", "/tmp/p01-traces"))
    directory.mkdir(parents=True, exist_ok=True)
    cell = _cell_identity()
    # Unique path per cell when identity is supplied; fall back to pid-only.
    if "seed" in cell and "candidate_seat" in cell and "label" in cell:
        stem = f"p01-{MODE}-s{cell['seed']}-seat{cell['candidate_seat']}-{cell['label']}-{os.getpid()}"
    else:
        stem = f"p01-{MODE}-{os.getpid()}"
    path = directory / f"{stem}.jsonl"
    row = {
        "schema": 1,
        "mode": MODE,
        "pid": os.getpid(),
        "step": int(observation.get("step", report.get("step", -1))),
        "player": int(observation.get("player", -1)),
        "changed": bool(report.get("changed")),
        "before_action_sha256": _digest(before),
        "after_action_sha256": _digest(after),
        "before_market": before.get("market", []),
        "after_market": after.get("market", []),
        "report": report,
        **cell,
    }
    # Prefer official info.seed when the observation carries it.
    info = observation.get("info") if isinstance(observation, dict) else None
    if isinstance(info, dict) and info.get("seed") is not None and "seed" not in row:
        row["seed"] = info["seed"]
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")


def agent(observation, configuration=None):
    cfg = dict(configuration or {})
    selected = _canonical.agent(observation, cfg)
    result, report = prioritize_opening_seeds(
        _mechanics, observation, cfg, selected, mode=MODE, max_day=MAX_DAY
    )
    _emit(observation, selected, result, report)
    return result

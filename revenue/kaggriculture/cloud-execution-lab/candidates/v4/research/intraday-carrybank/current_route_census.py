from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from carrybank import admit_carrybank_pickup

EXPECTED_ARLENE_BLOB = "bdb9cf58148a3c7961c085f4902759537decabf6"


def _git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def _load_arlene(path: Path):
    got = _git_blob(path)
    if got != EXPECTED_ARLENE_BLOB:
        raise RuntimeError(f"Arlene source drift: expected {EXPECTED_ARLENE_BLOB}, got {got}")
    spec = importlib.util.spec_from_file_location("_carrybank_census_arlene", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _actors(row: dict[str, Any]) -> list[list[Any]]:
    return [list(row.get("farmer") or ["PASS"])] + [list(a) for a in (row.get("hands") or [])]


def census(arlene_path: Path) -> dict[str, Any]:
    """Upper-bound raw-route census for current CARRYBANK sink availability."""
    arlene = _load_arlene(Path(arlene_path))
    branches = sorted(turn for turn, _feature, _threshold, _target in arlene.DECISIONS)
    raw: list[dict[str, Any]] = []
    safe: list[dict[str, Any]] = []

    for route_id, route in sorted(arlene.routes().items()):
        for step, row in enumerate(route[:-1]):
            if step % 24 == 23:
                continue
            market = (row.get("market") or [])[: arlene.MAX_ORDERS]
            if not any(
                order and order[0] == "BUY_PRODUCT"
                and order[1] in ("WHEAT", "FERTILIZER") and int(order[2]) > 0
                for order in market
            ):
                continue

            end_of_day = step + (23 - step % 24)
            future_branch = min(
                (turn - 1 for turn in branches if turn > step), default=len(route) - 1)
            end = min(end_of_day, future_branch, len(route) - 1)
            current = _actors(row)

            for actor_index, current_action in enumerate(current):
                if not current_action or current_action[0] != "PASS":
                    continue
                future: list[list[Any]] = []
                for future_step in range(step + 1, end + 1):
                    future_actors = _actors(route[future_step])
                    if actor_index >= len(future_actors):
                        break
                    future.append(future_actors[actor_index])
                if not any(a and a[0] in ("FEED", "FERTILIZE") for a in future):
                    continue

                candidate = {"route_id": route_id, "step": step, "actor_index": actor_index}
                raw.append(candidate)
                decision = admit_carrybank_pickup(
                    current_unit_action=current_action,
                    adjacent_to_shed=True,
                    shed={"WHEAT": 50, "FERTILIZER": 50},
                    shed_capacity=100,
                    projected_shed_inflow_units=1,
                    current_inventory={},
                    future_unit_actions=future,
                    turns_remaining=len(future),
                )
                if decision is not None:
                    safe.append(dict(candidate, item=decision.item, quantity=decision.quantity))

    per_route: dict[str, int] = {}
    for row in raw:
        per_route[row["route_id"]] = per_route.get(row["route_id"], 0) + 1
    route_steps = sorted({(row["route_id"], row["step"]) for row in raw})
    return {
        "schema": "titan-v4-carrybank-current-route-census-v1",
        "arlene_git_blob": EXPECTED_ARLENE_BLOB,
        "assumptions": {
            "shed_adjacent": True,
            "positive_capacity_pressure": True,
            "available_stock": {"WHEAT": 50, "FERTILIZER": 50},
            "current_inventory": {},
            "horizon": "same day and strictly before next route branch checkpoint",
        },
        "raw_structural_actor_candidates": len(raw),
        "raw_structural_route_steps": len(route_steps),
        "raw_by_route": dict(sorted(per_route.items())),
        "corrected_safe_candidates": len(safe),
        "safe_candidates": safe,
        "disposition": (
            "NEEDS_STICKY_OBLIGATION_NO_RAW_ROUTE_ADMISSION" if not safe
            else "REVIEW_SAFE_CANDIDATES"
        ),
    }


def main() -> None:
    here = Path(__file__).resolve().parent
    lab = here.parents[4]
    report = census(lab / "reference/next-panel/vendor/arlene.py")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

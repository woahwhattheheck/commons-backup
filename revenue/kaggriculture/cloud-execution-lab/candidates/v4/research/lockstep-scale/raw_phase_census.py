"""Deterministic natural-reach census for the lockstep raw-phase certificate.

The census authenticates the canonical R01 tape bank and router source before
using either.  Tape bytes are read once, Git-blob checked, then the *same bytes*
are compiled to obtain the data-only ``load_tapes`` function.  Router bytes are
read once, Git-blob checked, and structurally parsed for literal route constants;
they are never imported or executed.

Output is research evidence only.  It does not mutate actions or authorize a
runtime policy.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

TAPE_GIT_BLOB = "a43289b9cc5e34a2481fddf652762a7d92f427ef"
ROUTER_GIT_BLOB = "35541da59f23a161105245c98841acda4bb376f9"
BUYABLE_PRODUCTS = frozenset(("WHEAT", "FERTILIZER"))


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _snapshot(path: Path, expected: str) -> bytes:
    data = Path(path).read_bytes()
    actual = git_blob(data)
    if actual != expected:
        raise ValueError(f"source pin mismatch for {path}: {actual} != {expected}")
    return data


def load_tapes_snapshot(path: Path) -> list:
    data = _snapshot(path, TAPE_GIT_BLOB)
    namespace: dict[str, Any] = {"__name__": "titan_raw_phase_tapes"}
    exec(compile(data, str(path), "exec"), namespace, namespace)
    loader = namespace.get("load_tapes")
    if not callable(loader):
        raise ValueError("authenticated tape source has no callable load_tapes")
    tapes = loader()
    if type(tapes) is not list or len(tapes) != 13:
        raise ValueError("expected exactly 13 tapes")
    if any(type(tape) is not list or len(tape) != 719 for tape in tapes):
        raise ValueError("expected exactly 719 actions per tape")
    return tapes


def router_contract_from_bytes(data: bytes) -> dict[str, Any]:
    tree = ast.parse(data.decode("utf-8"))
    wanted = {"ROUTE_STEP", "FINAL_PLAN_STEP", "LAST_STEP", "MAX_ORDERS", "SHOP_PLANS"}
    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in wanted:
            try:
                values[target.id] = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError) as exc:
                raise ValueError(f"router constant {target.id} is not literal") from exc
    if set(values) != wanted:
        raise ValueError(f"router literal contract incomplete: {sorted(set(wanted) - set(values))}")
    for key in ("ROUTE_STEP", "FINAL_PLAN_STEP", "LAST_STEP", "MAX_ORDERS"):
        if type(values[key]) is not int:
            raise ValueError(f"{key} must be a plain integer")
    if values["ROUTE_STEP"] != 144 or values["FINAL_PLAN_STEP"] != 648:
        raise ValueError("unexpected R01 route splice boundaries")
    if values["LAST_STEP"] != 718 or values["MAX_ORDERS"] != 10:
        raise ValueError("unexpected R01 horizon or market cap")
    shop_plans = values["SHOP_PLANS"]
    if type(shop_plans) is not dict:
        raise ValueError("SHOP_PLANS must be a literal dictionary")
    plans = {0}
    for key, value in shop_plans.items():
        if (type(key) is not tuple or len(key) != 2 or
                any(type(part) is not str for part in key) or
                type(value) is not int or not 0 <= value < 13):
            raise ValueError("malformed SHOP_PLANS entry")
        plans.add(value)
    values["REACHABLE_MIDGAME_PLANS"] = tuple(sorted(plans))
    return values


def load_router_contract(path: Path) -> dict[str, Any]:
    data = _snapshot(path, ROUTER_GIT_BLOB)
    return router_contract_from_bytes(data)


def _noop(row: Any) -> bool:
    return row is None or (type(row) is list and (not row or row == ["PASS"]))


def _buy(row: Any) -> tuple[str, int] | None:
    if type(row) is not list or len(row) != 3 or row[0] != "BUY_PRODUCT":
        return None
    item, quantity = row[1], row[2]
    if type(item) is not str or item not in BUYABLE_PRODUCTS:
        return None
    if type(quantity) is not int or quantity <= 0:
        return None
    return item, quantity


def action_candidates(action: Any, cap: int) -> list[dict[str, Any]]:
    if type(action) is not dict:
        return []
    rows = action.get("market")
    if type(rows) is not list:
        return []
    stop = min(len(rows), cap)
    out: list[dict[str, Any]] = []
    for source in range(stop):
        parsed = _buy(rows[source])
        if parsed is None:
            continue
        item, quantity = parsed
        for target in (source - 1, source + 1):
            if not (0 <= target < stop) or not _noop(rows[target]):
                continue
            out.append({
                "source_slot": source,
                "target_slot": target,
                "direction": "advance_one_slot" if target < source else "delay_one_slot",
                "item": item,
                "quantity": quantity,
            })
    return out


def census_tapes(tapes: list, contract: dict[str, Any]) -> dict[str, Any]:
    if type(tapes) is not list or len(tapes) != 13 or any(
        type(tape) is not list or len(tape) != 719 for tape in tapes
    ):
        raise ValueError("expected canonical 13x719 tape shape")
    route_step = contract["ROUTE_STEP"]
    final_step = contract["FINAL_PLAN_STEP"]
    last_step = contract["LAST_STEP"]
    cap = contract["MAX_ORDERS"]
    selected_plans = tuple(contract["REACHABLE_MIDGAME_PLANS"])
    if not selected_plans or any(type(p) is not int or not 0 <= p < 13 for p in selected_plans):
        raise ValueError("invalid reachable plan set")

    # De-duplicate shared prefix/final-plan coordinates while retaining exactly
    # which selected route plans can realize each authored coordinate.
    found: dict[tuple, dict[str, Any]] = {}
    effective_cells = 0
    for selected in selected_plans:
        for step in range(last_step):  # step 718 is replaced by liquidate().
            if step < route_step:
                tape_plan = 0
            elif step < final_step:
                tape_plan = selected
            else:
                tape_plan = 2
            effective_cells += 1
            for candidate in action_candidates(tapes[tape_plan][step], cap):
                key = (
                    tape_plan,
                    step,
                    candidate["source_slot"],
                    candidate["target_slot"],
                    candidate["direction"],
                    candidate["item"],
                    candidate["quantity"],
                )
                row = found.get(key)
                if row is None:
                    row = {
                        "tape_plan": tape_plan,
                        "step": step,
                        **candidate,
                        "selected_plans": [],
                    }
                    found[key] = row
                row["selected_plans"].append(selected)

    candidates = sorted(
        found.values(),
        key=lambda row: (row["step"], row["tape_plan"], row["source_slot"], row["target_slot"]),
    )
    by_item: dict[str, int] = {}
    by_direction: dict[str, int] = {}
    for row in candidates:
        by_item[row["item"]] = by_item.get(row["item"], 0) + 1
        by_direction[row["direction"]] = by_direction.get(row["direction"], 0) + 1
    return {
        "schema": "titan.v4.lockstep-raw-phase-census.v1",
        "policy_authorized": False,
        "current_native_reach_authority": False,
        "candidate_surface": "authored_r01_tape_pre_transforms",
        "tape_git_blob": TAPE_GIT_BLOB,
        "router_git_blob": ROUTER_GIT_BLOB,
        "route_step": route_step,
        "final_plan_step": final_step,
        "last_step": last_step,
        "excluded_final_liquidation_step": last_step,
        "max_orders": cap,
        "reachable_midgame_plans": list(selected_plans),
        "effective_route_cells_examined": effective_cells,
        "unique_candidate_coordinates": len(candidates),
        "by_item": dict(sorted(by_item.items())),
        "by_direction": dict(sorted(by_direction.items())),
        "candidates": candidates,
    }


def build_report(tapes_path: Path, router_path: Path) -> dict[str, Any]:
    tapes = load_tapes_snapshot(tapes_path)
    contract = load_router_contract(router_path)
    return census_tapes(tapes, contract)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tapes", type=Path, required=True)
    parser.add_argument("--router", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.tapes, args.router)
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

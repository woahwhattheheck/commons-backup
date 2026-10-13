#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""ASTRA-GANDER source-bound Day-0 goose/fertilizer opening oracle.

This module does NOT promote a gameplay default.  It answers the narrower
mechanical question raised by the "Goose Printer" build demand:

1. can a goose placed on day 0 expose fertilizer at the day-0 refresh before
   its first egg yield?
2. is the literal 10-goose / 20-action opener executable?
3. what is the strongest *constructively executable* all-goose day-0 frontier
   under standard configuration?
4. what does the first full keep-alive fertilizer cycle do to liquid cash?

The official engine file is Git-blob pinned.  The reduced scheduler/economics
below only models source-proved operations needed by this theorem.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

EXPECTED_ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"

STARTING_MONEY = 3000
TURNS_PER_DAY = 24
MAX_MARKET_ORDERS = 10
GOOSE_COST = 300
FARM_HAND_COST_MULT = 1

HERE = Path(__file__).resolve().parent
DEFAULT_ENGINE = (
    HERE.parents[3] / "reference" / "engine" / "kaggriculture.py"
    if len(HERE.parents) > 3
    else HERE / "__repository_checkout_unavailable__" / "kaggriculture.py"
)

# Relevant exact pinned-engine market constants.
MARKET = {
    "WHEAT": {
        "base": 25, "I0": 10000, "T": 400,
        "below_func": "sqrt", "below_target": 0.80,
        "above_func": "log", "above_target": 0.20,
    },
    "FERTILIZER": {
        "base": 100, "I0": 10000, "T": 200,
        "below_func": "linear", "below_target": 0.40,
        "above_func": "linear", "above_target": 0.40,
    },
}
PRICE_FLOOR = 1


class GanderError(RuntimeError):
    pass


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _subscript_key(target: ast.AST) -> str | None:
    if not isinstance(target, ast.Subscript):
        return None
    sl = target.slice
    if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
        return sl.value
    return None


def verify_engine_source(path: Path = DEFAULT_ENGINE) -> dict:
    """Fail closed unless the exact pinned official engine proves the theorem."""
    data = path.read_bytes()
    actual = git_blob_sha(data)
    if actual != EXPECTED_ENGINE_BLOB:
        raise GanderError(
            f"official engine drift: expected {EXPECTED_ENGINE_BLOB}, got {actual}"
        )
    text = data.decode("utf-8")
    tree = ast.parse(text)

    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    required = {
        "_initialize",
        "_apply_unit_action",
        "_process_market",
        "_commit_unit",
        "_daily_refresh_animals",
        "interpreter",
    }
    missing = sorted(required - functions.keys())
    if missing:
        raise GanderError(f"missing pinned functions: {missing}")

    animals = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "ANIMALS" for t in node.targets):
                animals = ast.literal_eval(node.value)
                break
    if not isinstance(animals, dict) or animals.get("GOOSE") != {
        "cost": 300,
        "structure": "COOP",
        "first_yield_day": 4,
        "interval": 1,
        "max_held": 4,
        "product": "EGG",
    }:
        raise GanderError("GOOSE source contract drift")

    refresh = functions["_daily_refresh_animals"]
    loops = [n for n in ast.walk(refresh) if isinstance(n, ast.For)]
    inner = None
    for loop in loops:
        direct_loops = [n for n in loop.body if isinstance(n, ast.For)]
        if direct_loops:
            inner = direct_loops[0]
            break
    if inner is None:
        raise GanderError("animal refresh board loop shape drift")

    fert_direct = False
    production_gate = False
    for node in inner.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if _subscript_key(target) == "fertilizer_available":
                    fert_direct = (
                        isinstance(node.value, ast.Constant) and node.value.value is True
                    )
        if isinstance(node, ast.If):
            segment = ast.get_source_segment(text, node) or ""
            if "days_since_first >= 0" in segment and '"yield_units"' in segment:
                production_gate = True
    if not fert_direct or not production_gate:
        raise GanderError("animal refresh fertilizer/yield boundary drift")

    interpreter = functions["interpreter"]
    unit_lines = []
    market_lines = []
    for node in ast.walk(interpreter):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else None
            if name == "_apply_unit_action":
                unit_lines.append(node.lineno)
            elif name == "_process_market":
                market_lines.append(node.lineno)
    if not unit_lines or not market_lines or max(unit_lines) >= min(market_lines):
        raise GanderError("unit-before-market ordering drift")

    apply_text = ast.get_source_segment(text, functions["_apply_unit_action"]) or ""
    for required_text in (
        'if op == "PICKUP"',
        'if op == "PLACE"',
        'if op == "BUILD_COOP"',
        'if op == "COLLECT_FERTILIZER"',
    ):
        if required_text not in apply_text:
            raise GanderError(f"unit action contract drift: {required_text}")

    process_text = ast.get_source_segment(text, functions["_process_market"]) or ""
    initialize_text = ast.get_source_segment(text, functions["_initialize"]) or ""
    interpreter_text = ast.get_source_segment(text, interpreter) or ""
    for needle, haystack in (
        ('"maxMarketOrdersPerTurn", 10', process_text),
        ('"startingMoney", 3000', initialize_text),
        ('"turnsPerDay", 24', interpreter_text),
    ):
        if needle not in haystack:
            raise GanderError(f"standard default drift: {needle}")

    return {
        "engine_blob": actual,
        "goose_cost": animals["GOOSE"]["cost"],
        "goose_first_yield_day": animals["GOOSE"]["first_yield_day"],
        "fertilizer_direct_after_survival": True,
        "unit_actions_before_market": True,
        "starting_money": STARTING_MONEY,
        "turns_per_day": TURNS_PER_DAY,
        "max_market_orders": MAX_MARKET_ORDERS,
    }


def fib(n: int) -> int:
    if type(n) is not int or n < 0:
        raise GanderError("fib index must be a nonnegative int")
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def hire_cost(hires: int) -> int:
    if type(hires) is not int or hires < 0:
        raise GanderError("hires must be a nonnegative int")
    return FARM_HAND_COST_MULT * sum(fib(i) for i in range(hires))


@dataclass(frozen=True)
class Action:
    step: int
    worker: int
    op: str
    arg: str | int | None = None
    x: int | None = None
    y: int | None = None


SNAKE = (
    (4, 4), (3, 4), (2, 4), (1, 4), (0, 4),
    (0, 3), (1, 3), (2, 3), (3, 3),
)
MAIN_TWO_WORKER = ((4, 4), (4, 3), (4, 2), (4, 1), (4, 0))
HAND_TWO_WORKER = ((3, 3), (2, 3), (1, 3), (0, 3))


def _move_sequence(
    worker: int, start_step: int, start: tuple[int, int], target: tuple[int, int]
) -> tuple[list[Action], int, tuple[int, int]]:
    actions: list[Action] = []
    step = start_step
    x, y = start
    tx, ty = target
    while x != tx:
        x += 1 if tx > x else -1
        actions.append(Action(step, worker, "MOVE", x=x, y=y))
        step += 1
    while y != ty:
        y += 1 if ty > y else -1
        actions.append(Action(step, worker, "MOVE", x=x, y=y))
        step += 1
    return actions, step, (x, y)


def _build_worker_route(
    worker: int,
    start: tuple[int, int],
    sites: Iterable[tuple[int, int]],
    goose_count: int,
) -> list[Action]:
    sites = tuple(sites)
    if goose_count != len(sites):
        raise GanderError("route goose/site mismatch")
    if goose_count == 0:
        return []
    actions = [Action(1, worker, "PICKUP", goose_count, x=start[0], y=start[1])]
    step = 2
    pos = start
    for site in sites:
        moves, step, pos = _move_sequence(worker, step, pos, site)
        actions.extend(moves)
        actions.append(Action(step, worker, "BUILD_COOP", x=site[0], y=site[1]))
        step += 1
        actions.append(Action(step, worker, "PLACE", "GOOSE", x=site[0], y=site[1]))
        step += 1
        pos = site
    return actions


def day0_schedule(geese: int, hires: int) -> list[Action]:
    """Construct the certified standard-config Day-0 schedule for the frontier."""
    if type(geese) is not int or geese < 0 or geese > 10:
        raise GanderError("geese out of supported frontier")
    if type(hires) is not int or hires < 0:
        raise GanderError("invalid hires")
    if geese == 0:
        return []
    if geese <= 7 and hires == 0:
        return _build_worker_route(0, (4, 4), SNAKE[:geese], geese)
    if geese in (8, 9) and hires == 1:
        hand_n = 4
        main_n = geese - hand_n
        main = _build_worker_route(0, (4, 4), MAIN_TWO_WORKER[:main_n], main_n)
        hand = _build_worker_route(1, (5, 4), HAND_TWO_WORKER[:hand_n], hand_n)
        return sorted(main + hand, key=lambda a: (a.step, a.worker))
    raise GanderError("no certified schedule for this (geese, hires) pair")


def _placed_count(actions: Iterable[Action]) -> int:
    return sum(1 for a in actions if a.op == "PLACE" and a.arg == "GOOSE")


def _max_step(actions: Iterable[Action]) -> int:
    return max((a.step for a in actions), default=0)


def day0_frontier() -> list[dict]:
    rows = []
    for geese in range(0, 11):
        row = {
            "geese": geese,
            "feasible": False,
            "hires": None,
            "cash_after_day0": None,
            "last_unit_step": None,
            "fertilizer_ready_eod0": 0,
            "reason": None,
        }
        candidates = [(0 if geese <= 7 else 1)] if geese <= 9 else [0]
        for hires in candidates:
            cash = STARTING_MONEY - geese * GOOSE_COST - hire_cost(hires)
            market_rows = hires + (1 if geese else 0)
            if cash < 0 or market_rows > MAX_MARKET_ORDERS:
                continue
            if geese == 10 and hires == 0:
                lower_bound = 1 + 2 * geese + (geese - 1)
                row["reason"] = (
                    f"single-worker lower bound {lower_bound} > 23 remaining unit steps"
                )
                continue
            try:
                actions = day0_schedule(geese, hires)
            except GanderError:
                continue
            if _placed_count(actions) != geese or _max_step(actions) > 23:
                continue
            row.update(
                feasible=True,
                hires=hires,
                cash_after_day0=cash,
                last_unit_step=_max_step(actions),
                fertilizer_ready_eod0=geese,
                reason="constructive schedule",
            )
            break
        rows.append(row)
    return rows


def _service_worker_route(
    worker: int,
    start: tuple[int, int],
    sites: Iterable[tuple[int, int]],
    wheat_count: int,
) -> list[Action]:
    sites = tuple(sites)
    if wheat_count != len(sites):
        raise GanderError("service wheat/site mismatch")
    if not sites:
        return []
    actions = [Action(25, worker, "PICKUP", wheat_count, x=start[0], y=start[1])]
    step = 26
    pos = start
    for site in sites:
        moves, step, pos = _move_sequence(worker, step, pos, site)
        actions.extend(moves)
        actions.append(Action(step, worker, "FEED", "WHEAT", x=site[0], y=site[1]))
        step += 1
        actions.append(Action(step, worker, "COLLECT_FERTILIZER", x=site[0], y=site[1]))
        step += 1
        pos = site
    moves, step, pos = _move_sequence(worker, step, pos, (4, 4))
    actions.extend(moves)
    actions.append(Action(step, worker, "DROP", x=4, y=4))
    return actions


def day1_keepalive_schedule() -> list[Action]:
    """Construct the two-worker keep-alive/service route for the 9-goose frontier."""
    main = _service_worker_route(0, (4, 4), MAIN_TWO_WORKER, 5)
    hand = _service_worker_route(1, (5, 4), HAND_TWO_WORKER, 4)
    actions = sorted(main + hand, key=lambda a: (a.step, a.worker))
    if sum(1 for a in actions if a.op == "FEED") != 9:
        raise GanderError("keep-alive FEED count drift")
    if sum(1 for a in actions if a.op == "COLLECT_FERTILIZER") != 9:
        raise GanderError("fertilizer collection count drift")
    if sum(1 for a in actions if a.op == "DROP") != 2:
        raise GanderError("service DROP count drift")
    if _max_step(actions) > 47:
        raise GanderError("service route misses day-1 EOD")
    return actions


def shape(func: str, x: float, T: float) -> float:
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    raise GanderError(f"unsupported reduced-market shape {func}")


def market_price(item: str, inventory: int) -> int:
    p = MARKET[item]
    base = p["base"]
    I0 = p["I0"]
    T = p["T"]
    if inventory < I0:
        f = p["below_func"]
        amp = p["below_target"] * base / shape(f, T, T)
        value = base + amp * shape(f, I0 - inventory, T)
    else:
        f = p["above_func"]
        amp = p["above_target"] * base / shape(f, T, T)
        value = base - amp * shape(f, inventory - I0, T)
    return max(PRICE_FLOOR, int(round(value)))


def buy_product_prices(item: str, units: int, start_inventory: int) -> list[int]:
    inv = start_inventory
    prices = []
    for _ in range(units):
        post = inv - 1
        prices.append(market_price(item, post))
        inv = post
    return prices


def sell_prices(item: str, units: int, start_inventory: int) -> list[int]:
    inv = start_inventory
    prices = []
    for _ in range(units):
        price = market_price(item, inv)
        prices.append(price)
        if price > PRICE_FLOOR:
            inv += 1
    return prices


def day1_keepalive_ledger() -> dict:
    frontier = day0_frontier()[9]
    if not frontier["feasible"] or frontier["cash_after_day0"] != 299:
        raise GanderError("day0 frontier drift")
    service = day1_keepalive_schedule()
    if _max_step(service) != 45:
        raise GanderError("day1 constructive service route drift")
    wheat = buy_product_prices("WHEAT", 9, 9999)
    fert = sell_prices("FERTILIZER", 9, 10000)
    closing = frontier["cash_after_day0"] - hire_cost(1) - sum(wheat) + sum(fert)
    return {
        "day0_geese": 9,
        "day0_hires": 1,
        "day0_cash": frontier["cash_after_day0"],
        "day1_service_hire_cost": hire_cost(1),
        "day1_last_service_step": _max_step(service),
        "day1_wheat_prices": wheat,
        "day1_wheat_cost": sum(wheat),
        "day1_fertilizer_prices": fert,
        "day1_fertilizer_gross": sum(fert),
        "day1_closing_cash": closing,
        "cash_hold_baseline": STARTING_MONEY,
        "liquid_cash_delta_vs_hold": closing - STARTING_MONEY,
        "animals_survive_eod1": True,
        "egg_units_through_eod1": 0,
    }


def report(*, verify_source: bool = True, engine: Path = DEFAULT_ENGINE) -> dict:
    source = verify_engine_source(engine) if verify_source else {
        "engine_blob": EXPECTED_ENGINE_BLOB,
        "verification": "skipped-by-caller",
    }
    frontier = day0_frontier()
    feasible = [r["geese"] for r in frontier if r["feasible"]]
    return {
        "schema": "titan-v4-goose-printer-oracle/v1",
        "source": source,
        "literal_claim": {
            "ten_geese_twenty_actions": False,
            "mechanism_day0_fertilizer": True,
            "reason": frontier[10]["reason"],
        },
        "frontier": frontier,
        "max_certified_day0_geese": max(feasible),
        "day1_keepalive": day1_keepalive_ledger(),
        "promotion_decision": "NOT_ASSESSED",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", type=Path, default=DEFAULT_ENGINE)
    ap.add_argument("--no-source-verify", action="store_true")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    payload = report(verify_source=not args.no_source_verify, engine=args.engine)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

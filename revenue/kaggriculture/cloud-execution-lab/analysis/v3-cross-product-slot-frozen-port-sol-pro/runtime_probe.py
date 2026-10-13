#!/usr/bin/env python3
"""Execute the exact copied FrozenSelected feasibility closure through TitanAgent."""
from __future__ import annotations

import argparse
import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
from typing import Any

NOW = 100
CAP = 10
BUY = ["BUY_SEED", "WHEAT", 1]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base(orders: list[list[Any]]) -> dict[str, Any]:
    return {"farmer": ["PASS"], "hands": [], "market": copy.deepcopy(orders)}


def _obs() -> dict[str, Any]:
    return {
        "step": NOW,
        "player": 0,
        "farms": [{"tiles": []}, {"tiles": []}],
        "private": {},
        "market": {
            "inventory": {"CARROT": 10000, "MILK": 10000},
            "params": None,
        },
        "town": {"unlocked_shops": []},
    }


def _farm_private() -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {
            "money": 0,
            "hires_today": 0,
            "unlocked_quadrants": ["NW"],
            "hands": [],
            "tiles": [],
        },
        {
            "shed": {"CARROT": 1, "MILK": 1},
            "inventories": [{}],
            "seeds": {},
        },
    )


def _route(current_orders: list[list[Any]], future_orders: list[list[Any]] | None = None) -> list[dict[str, Any]]:
    route = [
        {"farmer": ["PASS"], "hands": [], "market": []}
        for _ in range(NOW + 3)
    ]
    route[NOW] = _base(current_orders)
    route[NOW + 1] = _base(future_orders or [])
    return route


def _selected_item(diagnostics: dict[str, Any]) -> str | None:
    chosen = diagnostics.get("chosen")
    if not isinstance(chosen, dict):
        return None
    return chosen.get("item")


def _emitted_products(action: dict[str, Any]) -> list[str]:
    return [
        row[1]
        for row in action.get("market", [])
        if row and len(row) > 2 and row[0] == "SELL"
    ]


def run_scenario(
    *,
    agent: Any,
    module: Any,
    config: dict[str, Any],
    name: str,
    current_orders: list[list[Any]],
    planned: dict[str, list[tuple[int, int]]],
    milk_plan: tuple[tuple[int, int], ...],
    future_orders: list[list[Any]] | None = None,
) -> dict[str, Any]:
    consumer = agent.consumer
    consumer.planned = copy.deepcopy(planned)
    consumer.pending = {}
    consumer.previous = None
    consumer.observed_harvests = {}
    consumer.diagnostics = {}
    consumer.mode = "candidate"
    consumer.controller.R = [_route(current_orders, future_orders)]
    consumer.controller.cur = 0

    decisions: dict[str, bool] = {}

    def optimize_probe(*, item: str, reference: tuple[tuple[int, int], ...], capacity_ok: Any, **_kwargs: Any):
        if item == "MILK":
            plan = tuple(milk_plan)
            allowed = bool(capacity_ok(plan))
            decisions[item] = allowed
            info = {
                "item": item,
                "reference": list(reference),
                "plan": list(plan),
                "accepted": allowed,
                "acceptance_score": 1.0 if allowed else 0.0,
                "worst_relative_gain": 1.0 if allowed else 0.0,
                "forced_feasibility": False,
                "scenarios": {},
            }
            return (plan if allowed else tuple(reference)), info
        # Keep the incumbent for CARROT but deliberately make it ineligible so
        # the witness isolates the copied MILK capacity callback.
        return tuple(reference), {
            "item": item,
            "reference": list(reference),
            "plan": list(reference),
            "accepted": False,
            "acceptance_score": 0.0,
            "worst_relative_gain": 0.0,
            "forced_feasibility": False,
            "scenarios": {},
        }

    module.optimize_lot = optimize_probe
    module.post_units = lambda *_args, **_kwargs: _farm_private()
    module.event_aware_horizon = lambda *_args, **_kwargs: (
        NOW + 1,
        {
            "baseline_end": NOW + 1,
            "hard_end": NOW + 1,
            "service_dates": {},
            "unit_event": None,
            "extended": False,
        },
    )
    module.represented_shed_event = lambda *_args, **_kwargs: None
    module.product_event_dates = lambda _item, now, end, _shops, _config: [now, end]
    module.funded_minimum_now = lambda *_args, **_kwargs: (0, {"probe": name})
    module.fund_same_turn_acquisition = lambda orders, *_args, **_kwargs: (orders, None)
    consumer.observe = lambda _observation: None
    consumer.cash_reserve = lambda *_args, **_kwargs: 0
    consumer.receipt_profile = lambda *_args, **_kwargs: (lambda _plan: True)
    consumer.rival_supply = lambda *_args, **_kwargs: 0

    transform_config = dict(config)
    transform_config["maxMarketOrdersPerTurn"] = CAP
    returned = consumer.transform(_obs(), transform_config, _base(current_orders))
    emitted = _emitted_products(returned)
    decision = decisions.get("MILK")
    return {
        "name": name,
        "milk_capacity_accepted": decision,
        "chosen_item": _selected_item(consumer.diagnostics),
        "emitted_products": emitted,
        "returned_market": returned["market"],
        "planned_after": {
            item: [list(row) for row in rows]
            for item, rows in sorted(consumer.planned.items())
        },
        "detached_current_certificate": bool(
            decision is True
            and _selected_item(consumer.diagnostics) == "MILK"
            and milk_plan[0] == (NOW, 1)
            and "MILK" not in emitted
        ),
    }


def load_runtime(lab: Path) -> tuple[Any, Any, dict[str, Any]]:
    lab = lab.resolve(strict=True)
    if not (lab / "titan_runtime.py").is_file():
        raise ValueError("lab does not contain titan_runtime.py")
    os.chdir(lab)
    sys.path.insert(0, str(lab))
    import titan_runtime  # type: ignore

    config = json.loads((lab / "TITAN-CONFIG.json").read_text(encoding="utf-8"))
    if config.get("consumer") != "frozen":
        raise ValueError("package config does not select frozen consumer")
    agent = titan_runtime.TitanAgent(titan_runtime.Features(**config))
    agent._initialize()
    consumer = agent.consumer
    module = sys.modules[consumer.__class__.__module__]
    class_source = Path(inspect.getsourcefile(consumer.__class__) or "").resolve()
    scheduler_source = Path(module.scheduling.__file__).resolve()
    if class_source != (lab / "frozen_selected.py").resolve():
        raise ValueError(f"TitanAgent loaded unexpected frozen source: {class_source}")
    if scheduler_source != (lab / "scheduler.py").resolve():
        raise ValueError(f"FrozenSelected loaded unexpected scheduler: {scheduler_source}")
    if consumer.__class__.__name__ != "FrozenSelected":
        raise ValueError("TitanAgent did not construct FrozenSelected")
    return agent, module, config


def build_report(lab: Path) -> dict[str, Any]:
    agent, module, config = load_runtime(lab)
    scenarios = {
        "saturated_current": run_scenario(
            agent=agent,
            module=module,
            config=config,
            name="saturated_current",
            current_orders=[BUY[:] for _ in range(9)],
            planned={"CARROT": [(NOW, 1)]},
            milk_plan=((NOW, 1),),
        ),
        "two_free_rows": run_scenario(
            agent=agent,
            module=module,
            config=config,
            name="two_free_rows",
            current_orders=[BUY[:] for _ in range(8)],
            planned={"CARROT": [(NOW, 1)]},
            milk_plan=((NOW, 1),),
        ),
        "inherited_milk_row": run_scenario(
            agent=agent,
            module=module,
            config=config,
            name="inherited_milk_row",
            current_orders=[BUY[:] for _ in range(8)] + [["SELL", "MILK", 1]],
            planned={"CARROT": [(NOW, 1)]},
            milk_plan=((NOW, 1),),
        ),
        "overdue_future": run_scenario(
            agent=agent,
            module=module,
            config=config,
            name="overdue_future",
            current_orders=[],
            future_orders=[BUY[:] for _ in range(9)],
            planned={"CARROT": [(NOW - 1, 1)]},
            milk_plan=((NOW, 0), (NOW + 1, 1)),
        ),
    }
    helper = getattr(module.scheduling, "_planned_slot_reservations", None)
    helper_controls = None
    if callable(helper):
        helper_controls = {
            "same_item_replacement": helper(
                {"MILK": [(NOW + 1, 4)]},
                {"MILK": 1},
                "MILK",
                NOW,
                NOW + 1,
                [BUY[:] for _ in range(9)],
            ),
            "overdue_future": helper(
                {"CARROT": [(NOW - 1, 1)]},
                {"MILK": 1},
                "MILK",
                NOW,
                NOW + 1,
                [BUY[:] for _ in range(9)],
            ),
            "malformed": helper(
                {"CARROT": [(True, 1)]},
                {"CARROT": 1, "MILK": 1},
                "MILK",
                NOW,
                NOW,
                [BUY[:] for _ in range(9)],
            ),
        }
    return {
        "schema": "titan-v3-cross-product-slot-active-runtime-probe-v1",
        "consumer_config": config["consumer"],
        "runtime_class": f"{agent.__class__.__module__}.{agent.__class__.__name__}",
        "selected_class": f"{agent.consumer.__class__.__module__}.{agent.consumer.__class__.__name__}",
        "frozen_sha256": sha256_file(lab / "frozen_selected.py"),
        "scheduler_sha256": sha256_file(lab / "scheduler.py"),
        "helper_present": callable(helper),
        "helper_controls": helper_controls,
        "scenarios": scenarios,
    }


def assert_expectations(report: dict[str, Any], expected: str) -> None:
    scenarios = report["scenarios"]
    saturated = scenarios["saturated_current"]
    free = scenarios["two_free_rows"]
    inherited = scenarios["inherited_milk_row"]
    overdue = scenarios["overdue_future"]
    if report["consumer_config"] != "frozen" or not report["selected_class"].endswith(".FrozenSelected"):
        raise AssertionError("probe did not execute the selected frozen consumer")
    if free["milk_capacity_accepted"] is not True or free["chosen_item"] != "MILK":
        raise AssertionError("two-free-row control was not admitted")
    if "CARROT" not in free["emitted_products"] or "MILK" not in free["emitted_products"]:
        raise AssertionError("two-free-row control did not emit both planned products")
    if inherited["milk_capacity_accepted"] is not True or "MILK" not in inherited["emitted_products"]:
        raise AssertionError("inherited same-product row control was not preserved")
    if expected == "predecessor":
        if report["helper_present"]:
            raise AssertionError("predecessor unexpectedly exposes donor helper")
        if saturated["milk_capacity_accepted"] is not True or not saturated["detached_current_certificate"]:
            raise AssertionError("predecessor did not reproduce detached chosen MILK certificate")
        if overdue["milk_capacity_accepted"] is not True or overdue["chosen_item"] != "MILK":
            raise AssertionError("predecessor did not overbook the overdue future slot")
    elif expected == "successor":
        if not report["helper_present"]:
            raise AssertionError("successor did not load donor scheduler helper")
        if saturated["milk_capacity_accepted"] is not False or saturated["chosen_item"] is not None:
            raise AssertionError("successor did not reject saturated current collision")
        if saturated["detached_current_certificate"]:
            raise AssertionError("successor retained detached chosen certificate")
        if overdue["milk_capacity_accepted"] is not False or overdue["chosen_item"] is not None:
            raise AssertionError("successor did not reject overdue future collision")
        controls = report["helper_controls"]
        if controls != {"same_item_replacement": 0, "overdue_future": 1, "malformed": None}:
            raise AssertionError(f"helper controls drifted: {controls!r}")
    else:
        raise AssertionError(f"unknown expectation {expected!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lab", type=Path, required=True)
    parser.add_argument("--expect", choices=("predecessor", "successor"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(args.lab)
    assert_expectations(report, args.expect)
    data = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

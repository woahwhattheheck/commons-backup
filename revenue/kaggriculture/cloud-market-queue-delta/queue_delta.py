# SPDX-License-Identifier: Apache-2.0
"""Compare complete market queues; report conditional effects without choosing actions.

All inputs are explicitly POST-UNIT. Rival state/actions are scenarios supplied by
callers, never an inference of hidden stock. Only the current market is simulated.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import math
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any, Mapping

SCHEMA = "market-queue-delta-v1"


class Struct(dict):
    """Attribute access required by the existing engine, preserving shared objects."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


class BudgetExceeded(Exception):
    pass


def _delta(before: Mapping, after: Mapping) -> dict:
    """Sparse signed numeric-map change; absence and zero are equivalent quantities."""
    return {key: after.get(key, 0) - before.get(key, 0)
            for key in sorted(set(before) | set(after))
            if after.get(key, 0) != before.get(key, 0)}


def _snapshot_copy(value: Any, memo: dict | None = None) -> Any:
    """Copy ordinary observed-state containers, retaining deepcopy's graph rules.

    Exact builtins use a smaller traversal; subclasses and other objects retain
    their standard deepcopy hooks. The shared memo preserves repeated references
    and cycles, including references crossing the fast and standard paths.
    """
    kind = type(value)
    if value is None or kind is int or kind is float or kind is str or kind is bool:
        return value
    if memo is None:
        memo = {}
    identity = id(value)
    if identity in memo:
        return memo[identity]
    if kind is dict:
        result = {}
        memo[identity] = result
        for key, item in value.items():
            result[_snapshot_copy(key, memo)] = _snapshot_copy(item, memo)
        memo.setdefault(id(memo), []).append(value)
        return result
    if kind is list:
        result = []
        memo[identity] = result
        result.extend(_snapshot_copy(item, memo) for item in value)
        memo.setdefault(id(memo), []).append(value)
        return result
    return copy.deepcopy(value, memo)


def _view(farm: Mapping, private: Mapping) -> dict:
    return _snapshot_copy(dict(cash=farm["money"], hands=farm["hands"],
        hires_today=farm["hires_today"], land=farm["unlocked_quadrants"],
        shed=private["shed"], seeds=private["seeds"],
        inventories=private["inventories"]))


def _effect(before: Mapping, after: Mapping) -> dict:
    return dict(cash=after["cash"] - before["cash"],
        shed=_delta(before["shed"], after["shed"]),
        seeds=_delta(before["seeds"], after["seeds"]),
        hires=after["hires_today"] - before["hires_today"],
        added_hands=copy.deepcopy(after["hands"][len(before["hands"]):]),
        added_land=copy.deepcopy(after["land"][len(before["land"]):]),
        inventories_added=len(after["inventories"]) - len(before["inventories"]))


def _units(action: Mapping) -> tuple:
    return action.get("farmer", ["PASS"]), action.get("hands", [])


def _queue(action: Mapping, max_orders: int) -> list:
    market = action.get("market", [])
    return copy.deepcopy(market[:max_orders] if isinstance(market, list) else [])


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise BudgetExceeded("deadline")


def _validate_party(farm: Mapping, private: Mapping) -> None:
    for key in ("money", "hands", "hires_today", "unlocked_quadrants", "farmer", "tiles"):
        if key not in farm:
            raise ValueError("missing_farm_" + key)
    if not isinstance(farm["money"], (int, float)) or not math.isfinite(farm["money"]):
        raise ValueError("nonfinite_money")
    if type(farm["hires_today"]) is not int or farm["hires_today"] < 0:
        raise ValueError("invalid_hires_today")
    if not all(isinstance(farm[k], list) for k in ("hands", "farmer", "tiles", "unlocked_quadrants")):
        raise ValueError("invalid_farm_lists")
    for key in ("shed", "seeds"):
        if not isinstance(private.get(key), dict):
            raise ValueError("missing_private_" + key)
        if any(type(n) is not int or n < 0 for n in private[key].values()):
            raise ValueError("invalid_private_quantities")
    if not isinstance(private.get("inventories"), list):
        raise ValueError("missing_private_inventories")
    if len(private["inventories"]) != 1 + len(farm["hands"]):
        raise ValueError("worker_inventory_count_mismatch")
    for inventory in private["inventories"]:
        if not isinstance(inventory, dict) or any(type(n) is not int or n < 0 for n in inventory.values()):
            raise ValueError("invalid_carried_quantities")


def _simulate(mechanics: Any, seat: int, own_farm: Mapping, own_private: Mapping,
              market: Mapping, action: Mapping, scenario: Mapping,
              configuration: Mapping, max_orders: int, deadline: float | None) -> dict:
    # Every arm receives fresh objects. Within one arm, observations share the
    # SAME farm/market objects, exactly as in the original _process_market.
    farms = [None, None]
    privates = [None, None]
    farms[seat], privates[seat] = _snapshot_copy([own_farm, own_private])
    farms[1-seat], privates[1-seat] = _snapshot_copy([scenario["farm"], scenario["private"]])
    shared_market = _snapshot_copy(market)
    queues = [None, None]
    queues[seat] = _queue(action, max_orders)
    queues[1-seat] = _queue(scenario["action"], max_orders)
    state = [Struct(observation=Struct(farms=farms, market=shared_market,
                private=privates[p]), action={}) for p in (0, 1)]
    env = Struct(configuration=Struct(configuration))
    initial = [_view(farms[p], privates[p]) for p in (0, 1)]
    trace = []
    # Snapshots are detached; the previous after-state is the next before-state.
    before = initial
    for slot in range(max(map(len, queues), default=0)):
        _check_deadline(deadline)
        for p in (0, 1):
            state[p].action = {"market": [queues[p][slot]] if slot < len(queues[p]) else []}
        # Original unmodified function handles both players' paired per-unit
        # quotes, atomic operations and resource admission. One call per slot
        # exposes attribution; no price/fill/affordability reimplementation.
        mechanics._process_market(state, env)
        after = [_view(farms[p], privates[p]) for p in (0, 1)]
        trace.append(dict(slot=slot,
            own_order=copy.deepcopy(queues[seat][slot]) if slot < len(queues[seat]) else None,
            rival_order=copy.deepcopy(queues[1-seat][slot]) if slot < len(queues[1-seat]) else None,
            own=_effect(before[seat], after[seat]),
            rival=_effect(before[1-seat], after[1-seat])))
        before = after
    _check_deadline(deadline)
    final = before
    return dict(own=final[seat], rival=final[1-seat],
        own_effect=_effect(initial[seat], final[seat]),
        rival_effect=_effect(initial[1-seat], final[1-seat]),
        market=shared_market, trace=trace,
        # Full owned farm is useful for continuation consumers (e.g. land tiles).
        own_farm=farms[seat], own_private=privates[seat],
        rival_farm=farms[1-seat], rival_private=privates[1-seat])


def _compare_row(baseline: Mapping, proposed: Mapping) -> dict:
    own = proposed["own"]["cash"] - baseline["own"]["cash"]
    rival = proposed["rival"]["cash"] - baseline["rival"]["cash"]
    slots = []
    for i in range(max(len(baseline["trace"]), len(proposed["trace"]))):
        b = baseline["trace"][i] if i < len(baseline["trace"]) else None
        p = proposed["trace"][i] if i < len(proposed["trace"]) else None
        inherited = (b is not None and p is not None and
                     b["own_order"] is not None and b["own_order"] == p["own_order"])
        slots.append(dict(slot=i, baseline=b, proposed=p,
            inherited_own_order=inherited,
            inherited_execution_changed=bool(inherited and b["own"] != p["own"])))
    resources = {key: proposed["own"][key] != baseline["own"][key]
                 for key in ("hands", "hires_today", "land", "shed", "seeds", "inventories")}
    return dict(own_cash=own, rival_cash=rival, relative_cash=own-rival,
                resource_changes=resources, slots=slots)


def compare_queues(mechanics: Any, *, step: int, seat: int, own_farm: Mapping,
                   own_private: Mapping, market: Mapping, baseline_action: Mapping,
                   proposed_action: Mapping, scenarios: list[dict],
                   configuration: Mapping, max_scenarios: int = 32,
                   max_unit_steps: int = 20000, max_orders_budget: int = 128,
                   deadline: float | None = None) -> dict:
    """Compare one market stage under explicit, equally applied rival scenarios.

    Supply actual post-unit own state and scenario post-unit rival state. Both
    actions must have identical unit fields. A complete result is conditional on
    ALL supplied scenarios; it is neither a future-value nor a policy decision.
    Unknown/over-budget input returns status='unknown', never a partial ranking.
    deadline is an optional absolute time.monotonic() value, checked between slots.
    """
    report = dict(schema=SCHEMA, step=step, seat=seat, status="unknown", reason=None,
                  horizon="current_market_only", scenario_results=[], bounds=None,
                  probabilistic=False, action_selected=False)
    started = time.perf_counter()
    try:
        _check_deadline(deadline)
        if type(seat) is not int or seat not in (0, 1) or type(step) is not int or step < 0:
            raise ValueError("invalid_step_or_seat")
        if not isinstance(baseline_action, dict) or not isinstance(proposed_action, dict):
            raise ValueError("actions_must_be_mappings")
        if _units(baseline_action) != _units(proposed_action):
            raise ValueError("different_unit_actions_require_different_post_unit_states")
        if not isinstance(scenarios, list) or not scenarios:
            raise ValueError("explicit_rival_scenarios_required")
        if len(scenarios) > max_scenarios:
            raise BudgetExceeded("scenario_budget")
        n_orders = max(1, int(configuration.get("maxMarketOrdersPerTurn", 10)))
        if n_orders > max_orders_budget:
            raise BudgetExceeded("order_budget")
        _validate_party(own_farm, own_private)
        if not isinstance(market.get("inventory"), dict) or not isinstance(market.get("prices"), dict):
            raise ValueError("market_inventory_and_prices_required")
        identifiers = set()
        work = 0
        # Complete preflight before any simulation: large parsed quantities and
        # Fibonacci hire indices cannot turn a bounded comparison into a long job.
        for scenario in scenarios:
            sid = scenario["id"]
            if not isinstance(sid, str) or not sid or sid in identifiers:
                raise ValueError("scenario_ids_must_be_unique_nonempty_strings")
            identifiers.add(sid)
            if not isinstance(scenario.get("provenance"), str) or not scenario["provenance"]:
                raise ValueError("scenario_provenance_required")
            _validate_party(scenario["farm"], scenario["private"])
            if not isinstance(scenario["action"], dict):
                raise ValueError("scenario_action_required")
            for action in (baseline_action, proposed_action, scenario["action"], scenario["action"]):
                for order in _queue(action, n_orders):
                    parsed = mechanics._parse_order(order)
                    work += 1 + (max(0, parsed.get("remaining", 0)) if parsed else 0)
            work += 2 * (own_farm["hires_today"] + scenario["farm"]["hires_today"]) * n_orders
        if work > max_unit_steps:
            raise BudgetExceeded("unit_work_budget")
        report["requested_work_bound"] = work
        for scenario in scenarios:
            _check_deadline(deadline)
            baseline = _simulate(mechanics, seat, own_farm, own_private, market,
                                 baseline_action, scenario, configuration, n_orders, deadline)
            proposed = _simulate(mechanics, seat, own_farm, own_private, market,
                                 proposed_action, scenario, configuration, n_orders, deadline)
            report["scenario_results"].append(dict(id=scenario["id"],
                provenance=scenario["provenance"], baseline=baseline, proposed=proposed,
                delta=_compare_row(baseline, proposed)))
        _check_deadline(deadline)
        report["bounds"] = {key: dict(min=min(r["delta"][key] for r in report["scenario_results"]),
                                      max=max(r["delta"][key] for r in report["scenario_results"]))
                            for key in ("own_cash", "rival_cash", "relative_cash")}
        report["status"] = "complete_conditional"
    except BudgetExceeded as exc:
        report["reason"] = str(exc)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        report["reason"] = "invalid_or_incomplete_input:" + str(exc)
    except Exception as exc:
        report["reason"] = "engine_error:" + type(exc).__name__
    report["elapsed_seconds"] = time.perf_counter() - started
    return report


# Transitive definitions used by the official market. Extraction leaves function
# bodies unmodified and excludes initialization, random draws and game execution.
MARKET_DEFINITIONS = frozenset(("CROPS ANIMALS PRODUCTS MARKET_I0 PRICE_FLOOR "
    "MARKET_PARAMS HINGE_GAIN LAND_ORDER LAND_PRICES FARM_HAND_COST_MULT "
    "get _shape _quadrant_of _shed_access_tiles market_price _refresh_prices "
    "_spawn_hand _process_market _parse_order _commit_unit _fib _hire_cost "
    "_do_hire _do_buy_land").split())


def load_market_engine(path: str | Path) -> Any:
    """Load exact market definitions from a caller's existing official source."""
    path = Path(path)
    body = path.read_bytes()
    tree = ast.parse(body, filename=str(path))
    nodes = []
    found = set()
    for node in tree.body:
        names = ([node.name] if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else
                 [t.id for t in node.targets if isinstance(t, ast.Name)]
                 if isinstance(node, ast.Assign) else [])
        if set(names) & MARKET_DEFINITIONS:
            nodes.append(node)
            found.update(names)
    if MARKET_DEFINITIONS - found:
        raise ValueError("missing_engine_definitions:" + ",".join(sorted(MARKET_DEFINITIONS-found)))
    namespace = {"math": math}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    namespace["source_sha256"] = hashlib.sha256(body).hexdigest()
    return SimpleNamespace(**namespace)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-source", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is not None:
        # Compare path and filesystem identity before loading or simulating.
        # A report must not truncate its engine, input, or executing CLI source.
        for incoming in (args.engine_source, args.input, Path(__file__)):
            try:
                try:
                    output_path = args.output.resolve(strict=True)
                except FileNotFoundError:
                    output_path = args.output.resolve()
                aliases = output_path == incoming.resolve()
                if args.output.exists() and incoming.exists():
                    aliases = aliases or args.output.samefile(incoming)
            except (OSError, RuntimeError) as exc:
                parser.error("Cannot resolve report/input identity: " + type(exc).__name__)
            if aliases:
                parser.error("Report output must not alias an engine, input, or CLI source")
    mechanics = load_market_engine(args.engine_source)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = compare_queues(mechanics, **payload)
    result["engine_source_sha256"] = mechanics.source_sha256
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0 if result["status"] == "complete_conditional" else 2


if __name__ == "__main__":
    raise SystemExit(main())

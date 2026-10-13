# SPDX-License-Identifier: Apache-2.0
"""Reproducible C5 market/town phase oracle; no agent/package activation.

Loads exact reviewed source bytes, then exercises the actual official market and
consumption functions on deterministic synthetic public/private microstates.
The unused Kaggle seed import is replaced by a raising guard; no game initializer,
legacy materializer, network service, or full Kaggle environment is executed.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import itertools
import json
import random
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
SCHEMA_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
HELPER_BLOB = "d5ea1757975099409a00a32e9c7eb6d40bf51926"
SEED = 2026091105


class OracleFailure(RuntimeError):
    """An executable source contract failed (also enforced under python -O)."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OracleFailure(message)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def pinned_bytes(filename: Path, expected: str) -> bytes:
    data = filename.read_bytes()
    require(git_blob(data) == expected, f"source pin mismatch: {filename}")
    return data


def load_sources(engine_path: Path, helper_path: Path):
    """Preserve every engine function; replace only unused external seed import."""
    raw = pinned_bytes(engine_path, ENGINE_BLOB)
    pinned_bytes(engine_path.with_name("kaggriculture.json"), SCHEMA_BLOB)
    tree = ast.parse(raw, filename=str(engine_path))
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom)
               and node.module == "kaggle_environments.utils"]
    require(len(imports) == 1, "seed import topology changed")
    require([(x.name, x.asname) for x in imports[0].names]
            == [("resolve_episode_seed", None)], "unexpected external import")
    tree.body.remove(imports[0])

    def unused_seed(*args, **kwargs):
        raise OracleFailure("phase-only oracle must not invoke game initialization")

    engine = types.ModuleType("c5_pinned_engine")
    engine.__file__ = str(engine_path)
    engine.resolve_episode_seed = unused_seed
    exec(compile(tree, str(engine_path), "exec"), engine.__dict__)
    helper = types.ModuleType("c5_pinned_helper")
    helper.__file__ = str(helper_path)
    exec(compile(pinned_bytes(helper_path, HELPER_BLOB), str(helper_path), "exec"),
         helper.__dict__)
    return engine, helper


@dataclass
class World:
    label: str
    step: int = 1
    inventory: int = 10000
    shops: tuple[str, ...] = ()
    cap: int = 10
    shop_interval: int = 4
    center_interval: int = 24
    money: tuple[int, int] = (100000, 100000)
    wheat: tuple[int, int] = (4, 4)
    room: tuple[int, int] = (90, 90)
    rows: tuple[list[Any], list[Any]] = field(default_factory=lambda: ([], []))


def make_state(engine, world: World):
    require(0 <= world.step <= 717, "transition needs a subsequent actionable callback")
    require(1 <= world.shop_interval and 1 <= world.center_interval,
            "oracle cadence must lie in helper's strict supported subset")
    config = {"boardSize": 10, "maxMarketOrdersPerTurn": world.cap,
              "shedCapacity": 100, "farmHandCostMult": 1,
              "townShopSellInterval": world.shop_interval,
              "townCenterSellInterval": world.center_interval}
    market = engine._new_market()
    market["inventory"]["WHEAT"] = world.inventory
    engine._refresh_prices(market)
    farms = [engine._new_farm(10, world.money[player]) for player in (0, 1)]
    town = {"unlocked_shops": list(world.shops)}
    states = []
    for player in (0, 1):
        private = engine._new_private()
        require(0 <= world.wheat[player] <= 100 - world.room[player] <= 100,
                "bad synthetic shed occupancy")
        private["shed"]["WHEAT"] = world.wheat[player]
        private["shed"]["FERTILIZER"] = 100 - world.room[player] - world.wheat[player]
        obs = types.SimpleNamespace(step=world.step, player=player, farms=farms,
                                    market=market, town=town, private=private)
        action = {"farmer": ["PASS"], "hands": [],
                  "market": copy.deepcopy(world.rows[player])}
        states.append(types.SimpleNamespace(observation=obs, action=action))
    return states, types.SimpleNamespace(configuration=config)


def execute_phases(engine, states, env, step: int, *, instrument: bool = True):
    """Forward all calls unchanged; count successful commits, never requests."""
    events = []
    original = engine._commit_unit
    farms = states[0].observation.farms

    def observed(op, item, price, farm, private, market, shed_capacity=100):
        ok = original(op, item, price, farm, private, market, shed_capacity)
        if ok and item == "WHEAT" and op in ("BUY_PRODUCT", "SELL"):
            player = next(i for i, candidate in enumerate(farms) if candidate is farm)
            events.append({"player": player, "op": op, "price": price})
        return ok

    if instrument:
        engine._commit_unit = observed
    try:
        engine._process_market(states, env)
        after_market = states[0].observation.market["inventory"]["WHEAT"]
        engine._town_consume(env, states, step)
        after_town = states[0].observation.market["inventory"]["WHEAT"]
    finally:
        engine._commit_unit = original
    return events, after_market - after_town


def result_state(states):
    return {"market": copy.deepcopy(states[0].observation.market),
            "farms": copy.deepcopy(states[0].observation.farms),
            "private": [copy.deepcopy(s.observation.private) for s in states],
            "actions": [copy.deepcopy(s.action) for s in states]}


def evaluate(engine, helper, world: World) -> dict[str, Any]:
    states, env = make_state(engine, world)
    previous = [copy.deepcopy(s.observation) for s in states]
    rider = helper.WheatDemandRider(enabled=True)
    # The same rider deliberately alternates seats: public evidence is per-player.
    for player in (0, 1):
        action = states[player].action
        require(rider.apply(previous[player], action, env.configuration) is action,
                f"{world.label}: first sight of a seat must not relocate")
    records = copy.deepcopy(rider.players)
    snapshots = [copy.deepcopy(s.action) for s in states]
    events, town = execute_phases(engine, states, env, world.step)
    require([s.action for s in states] == snapshots, "engine action vectors mutated")
    buys = [sum(e["player"] == p and e["op"] == "BUY_PRODUCT" for e in events)
            for p in (0, 1)]
    sales = [sum(e["player"] == p and e["op"] == "SELL" for e in events)
             for p in (0, 1)]
    visible_sales = sum(e["op"] == "SELL" and e["price"] > 1 for e in events)
    invisible_sales = sum(e["op"] == "SELL" and e["price"] == 1 for e in events)
    current = states[0].observation.market["inventory"]["WHEAT"]
    require(current == world.inventory - sum(buys) + visible_sales - town,
            f"{world.label}: real engine inventory conservation failed")
    outputs = []
    for player in (0, 1):
        obs = copy.deepcopy(states[player].observation)
        obs.step = world.step + 1
        parent = {"farmer": ["PASS"], "hands": [],
                  "market": [["SELL", "WHEAT", 2]]}
        before = copy.deepcopy((obs, parent))
        lower = None
        if player in records:
            record = records[player]
            require(record["town_consume"] == town,
                    f"{world.label}: town consumption mismatch, seat {player}")
            upper = record["own_buy_upper"]
            require(upper >= buys[player], f"{world.label}: own buy upper bound undercounts")
            lower = helper._rival_wheat_buy_lower_bound(
                world.inventory, current, record["town_consume"], upper)
            require(lower == buys[1-player] + buys[player] - upper - visible_sales,
                    f"{world.label}: exact gross-flow identity failed, seat {player}")
            require(lower <= buys[1-player],
                    f"{world.label}: falsely certified rival gross buys, seat {player}")
        out = rider.apply(obs, parent, env.configuration)
        require((obs, parent) == before, f"{world.label}: helper changed evidence/parent")
        should_move = (lower is not None and lower > 0
                       and obs.market["prices"]["WHEAT"] > 1 and max(1, world.cap) >= 2)
        require((out is not parent) == should_move,
                f"{world.label}: unexpected transformation decision, seat {player}")
        if should_move:
            require(out["market"] == [[], ["SELL", "WHEAT", 2]],
                    f"{world.label}: row custody/quantity changed")
        outputs.append({"player": player, "record_valid": player in records,
                        "lower_bound": lower, "gross_rival_buys": buys[1-player],
                        "rival_net_buys": buys[1-player] - sales[1-player],
                        "relocated": should_move})
    return {"label": world.label, "inventory_before": world.inventory,
            "inventory_after": current, "town_units": town,
            "buys": buys, "sales": sales, "visible_sales": visible_sales,
            "invisible_sales": invisible_sales, "seats": outputs}


def explicit_worlds():
    yield World("own-buy-is-not-rival", rows=([["BUY_PRODUCT", "WHEAT", 3]], []))
    yield World("rival-buy-positive", rows=([], [["BUY_PRODUCT", "WHEAT", 3]]))
    yield World("town-only-duplicate-shops", step=24,
                shops=("BAKERY", "BAKERY", "PIZZA_SHOP", "YARN_STORE"))
    yield World("partial-cash-fill", money=(26, 100000),
                rows=([["BUY_PRODUCT", "WHEAT", 7]], [["BUY_PRODUCT", "WHEAT", 2]]))
    yield World("partial-capacity-fill", room=(1, 90),
                rows=([["BUY_PRODUCT", "WHEAT", 7]], [["BUY_PRODUCT", "WHEAT", 2]]))
    yield World("floor-gross-not-net", inventory=10**15,
                rows=([], [["SELL", "WHEAT", 3], ["BUY_PRODUCT", "WHEAT", 3]]))
    yield World("raw-cap-before-parsing", cap=1,
                rows=([[], ["BUY_PRODUCT", "WHEAT", 8]], [["BUY_PRODUCT", "WHEAT", 2]]))
    yield World("tuple-buy-is-inert", rows=([("BUY_PRODUCT", "WHEAT", 8)],
                                           [["BUY_PRODUCT", "WHEAT", 2]]))
    yield World("coerced-own-buy-forgets", rows=([["BUY_PRODUCT", "WHEAT", "2"]],
                                                [["BUY_PRODUCT", "WHEAT", 2]]))
    yield World("negative-inventory-valid", inventory=-3, step=24, shops=("BAKERY",),
                rows=([["SELL", "WHEAT", 1]], [["BUY_PRODUCT", "WHEAT", 3]]))
    for cap, index in itertools.product((-1, 0, 1, 2, 10), (0, 1, 9, 10, 11)):
        yield World(f"raw-boundary-{cap}-{index}", cap=cap,
                    rows=([[]] * index + [["BUY_PRODUCT", "WHEAT", 2]],
                          [["BUY_PRODUCT", "WHEAT", 3]]))
    for step, shops, intervals in itertools.product(
            (0, 1, 3, 4, 23, 24, 47, 48, 695, 696, 717),
            ((), ("BAKERY",), ("BAKERY", "BAKERY", "PIZZA_SHOP"),
             ("YARN_STORE", "PET_CAFE", "SMOOTHIE_SHOP")),
            ((4, 24), (1, 1), (3, 7))):
        yield World(f"cadence-{step}-{shops}-{intervals}", step=step, shops=shops,
                    shop_interval=intervals[0], center_interval=intervals[1])


def random_worlds(count: int, seed: int = SEED):
    rng = random.Random(seed)
    templates = [[], None, ["PASS"], ["SELL", "WHEAT", 2],
                 ["SELL", "FERTILIZER", 2], ["BUY_PRODUCT", "WHEAT", 3],
                 ["BUY_PRODUCT", "FERTILIZER", 2], ["BUY_SEED", "WHEAT", 1],
                 ["BUY_ANIMAL", "GOOSE", 1], ["HIRE"], ["BUY_LAND"],
                 ["UNKNOWN", "WHEAT", 2], ("BUY_PRODUCT", "WHEAT", 3),
                 ["BUY_PRODUCT", "WHEAT", "2"], ["BUY_PRODUCT", "WHEAT", 0]]
    shops = ("BAKERY", "PIZZA_SHOP", "BRUNCH_SPOT", "YARN_STORE",
             "ICE_CREAM_SHOP", "PET_CAFE", "SMOOTHIE_SHOP", "FARMERS_MARKET")
    for index in range(count):
        quantities = (rng.randrange(7), rng.randrange(7))
        yield World(f"seed-{seed}-{index}", step=rng.randrange(718),
                    inventory=rng.choice((-20, 0, 9600, 9999, 10000, 10001, 10400, 10**15)),
                    shops=tuple(rng.choices(shops, k=rng.randrange(9))),
                    cap=rng.choice((-2, 0, 1, 2, 3, 10)),
                    shop_interval=rng.choice((1, 3, 4)), center_interval=rng.choice((1, 7, 24)),
                    money=(rng.choice((0, 1, 25, 26, 50, 10000)),
                           rng.choice((0, 1, 25, 26, 50, 10000))),
                    wheat=quantities,
                    room=tuple(rng.choice((0, 1, 2, 100-q)) for q in quantities),
                    rows=tuple(copy.deepcopy(rng.choices(templates, k=rng.randrange(13)))
                               for _ in (0, 1)))


def paired_sale_timing(engine, helper) -> dict[str, Any]:
    """Immediate cash/margin, same private poststate; not an episode outcome.

    Each case begins with an actual prior rival BUY(1), so the signal is genuine.
    Only the unobserved NEXT rival action varies; C5 cannot know that action when
    committing its relocation. This is a falsifier for unconditional profit.
    """
    rows = []
    for inventory, quantity, player, op, slot in itertools.product(
            (9599, 9997, 9999, 10000, 10001, 10003, 10005, 10400, 12000),
            (1, 2, 3, 4), (0, 1), ("PASS", "BUY_PRODUCT", "SELL"), (0, 1, 2)):
        prior = [[], []]
        prior[1-player] = [["BUY_PRODUCT", "WHEAT", 1]]
        world = World("timing", inventory=inventory, rows=tuple(prior))
        state, env = make_state(engine, world)
        rider = helper.WheatDemandRider(enabled=True)
        first_action = state[player].action
        require(rider.apply(copy.deepcopy(state[player].observation), first_action,
                            env.configuration) is first_action, "unexpected prior relocation")
        execute_phases(engine, state, env, 1)
        for actor in state:
            actor.observation.step = 2
        parent = {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WHEAT", quantity]]}
        candidate = rider.apply(copy.deepcopy(state[player].observation), parent, env.configuration)
        require(candidate is not parent, "timing probe must engage the real C5 signal")
        rival = ([] if op == "PASS" else [[]]*slot + [[op, "WHEAT", quantity]])
        state[player].action = parent
        state[1-player].action = {"farmer": ["PASS"], "hands": [], "market": rival}
        control = copy.deepcopy(state)
        treatment = copy.deepcopy(state)
        treatment[player].action = candidate
        execute_phases(engine, control, env, 2)
        execute_phases(engine, treatment, env, 2)
        control_post = result_state(control)
        treatment_post = result_state(treatment)
        require(control_post["private"] == treatment_post["private"],
                "timing cash comparison has unequal private inventory")
        require(control_post["market"] == treatment_post["market"],
                "timing cash comparison has unequal public market")
        deltas = [treatment_post["farms"][p]["money"] - control_post["farms"][p]["money"]
                  for p in (0, 1)]
        for p in (0, 1):
            control_post["farms"][p].pop("money")
            treatment_post["farms"][p].pop("money")
        require(control_post["farms"] == treatment_post["farms"],
                "timing comparison changes noncash farm state")
        rows.append({"prior_inventory": inventory, "quantity": quantity, "player": player,
                     "next_rival_operation": op, "next_rival_raw_slot": slot,
                     "prior_rival_buy_lower_bound": rider.telemetry["last_rival_buy_lower_bound"],
                     "delta_own_cash": deltas[player], "delta_rival_cash": deltas[1-player],
                     "delta_cash_margin": deltas[player] - deltas[1-player]})
    positive = [r for r in rows if r["delta_cash_margin"] > 0]
    negative = [r for r in rows if r["delta_cash_margin"] < 0]
    require(bool(positive) and bool(negative), "two-sided timing boundary witness disappeared")
    return {"scope": "Synthetic immediate cash-margin pairs, equal private/public poststate; NOT full-game economics",
            "pairs": len(rows), "positive": len(positive), "negative": len(negative),
            "zero": len(rows)-len(positive)-len(negative),
            "minimum_delta_cash_margin": min(r["delta_cash_margin"] for r in rows),
            "maximum_delta_cash_margin": max(r["delta_cash_margin"] for r in rows),
            "negative_witness": min(negative, key=lambda r: r["delta_cash_margin"]),
            "positive_witness": max(positive, key=lambda r: r["delta_cash_margin"]),
            "rows_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "conclusion": "A real prior buy signal does not guarantee positive next-callback cash margin; keep promotion gated"}


def run(engine, helper, count: int = 2048):
    results = [evaluate(engine, helper, world)
               for world in itertools.chain(explicit_worlds(), random_worlds(count))]
    seats = [seat for result in results for seat in result["seats"]]
    floor = next(result for result in results if result["label"] == "floor-gross-not-net")
    require(floor["invisible_sales"] == 3 and floor["seats"][0]["lower_bound"] == 3
            and floor["seats"][0]["rival_net_buys"] == 0,
            "floor witness did not distinguish gross buys from net demand")
    return {"schema": "titan-v4-c5-market-transition-oracle/v1", "seed": SEED,
            "source_pins": {"engine_git_blob": ENGINE_BLOB,
                            "engine_schema_git_blob": SCHEMA_BLOB,
                            "c5_helper_git_blob": HELPER_BLOB},
            "scope": "Synthetic market/town phases and immediate cash pairs, not full games, package CI, or promotion",
            "loader": "Only unused resolve_episode_seed import replaced by a raising guard; all engine functions unchanged",
            "status": "PASS", "worlds": len(results), "seat_checks": len(seats),
            "valid_transition_records": sum(s["record_valid"] for s in seats),
            "invalid_records_fail_closed": sum(not s["record_valid"] for s in seats),
            "positive_lower_bounds": sum(s["lower_bound"] is not None and s["lower_bound"] > 0 for s in seats),
            "relocation_witnesses": sum(s["relocated"] for s in seats),
            "actual_wheat_buy_fills": sum(sum(r["buys"]) for r in results),
            "visible_wheat_sell_fills": sum(r["visible_sales"] for r in results),
            "floor_invisible_wheat_sell_fills": sum(r["invisible_sales"] for r in results),
            "violations": 0, "floor_counterexample_to_net_demand": floor,
            "paired_sale_timing": paired_sale_timing(engine, helper),
            "results_sha256": hashlib.sha256(json.dumps(results, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "promotion": "NONE: current-defaults unchanged; prior gross buys do not prove future demand or profit"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    parser.add_argument("--random-worlds", type=int, default=2048)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    require(0 <= args.random_worlds <= 100000, "random-worlds must be in [0,100000]")
    engine, helper = load_sources(args.engine.resolve(), args.helper.resolve())
    receipt = run(engine, helper, args.random_worlds)
    text = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

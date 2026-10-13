# SPDX-License-Identifier: MIT
"""Independent full-interpreter flow corpus, not an opponent-flow estimator.

Run with an extracted native package's checks/reference/engine directory.
An audit wrapper delegates every market commit to the unchanged pinned engine;
a second, uninstrumented interpreter execution must have identical full state.
Candidate input and private oracle truth are separated in each record. No agent,
feature, prediction, or sale policy is installed by this module.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
import random
import sys
import types
from typing import Any

ENGINE_PINS = {
    "kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
}


class Struct(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        self[name] = value


def default_engine_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        if parent.name == "cloud-execution-lab":
            return parent / "reference" / "engine"
    return Path("__missing_pinned_engine__")


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def load_engine(directory: Path):
    """Authenticate all upstream dependencies BEFORE compiling any source.

    Only the external seed import is replaced with a raising sentinel. Fixtures
    already contain complete initialized state and env.info['seed']; that import
    must never be used. Every upstream game function body is unchanged.
    """
    directory = Path(directory)
    raw = {name: (directory / name).read_bytes() for name in ENGINE_PINS}
    for name, data in raw.items():
        if git_blob(data) != ENGINE_PINS[name]:
            raise ValueError(f"official engine source mismatch: {name}")
    source = directory / "kaggriculture.py"
    tree = ast.parse(raw[source.name].decode("utf-8"))
    imports = [n for n in tree.body if isinstance(n, ast.ImportFrom)
               and n.module == "kaggle_environments.utils"]
    if len(imports) != 1:
        raise ValueError("official seed-import topology changed")
    replacement = ast.parse("def resolve_episode_seed(env):\n"
                            "    raise RuntimeError('fixture used initialization')\n").body[0]
    tree.body[tree.body.index(imports[0])] = replacement
    engine = types.ModuleType("flowproof_pinned_engine")
    engine.__file__ = str(source)
    exec(compile(tree, str(source), "exec"), engine.__dict__)
    return engine


def cases(random_worlds: int = 96):
    """Fixed discriminators plus deterministic mixtures; each runs both seats."""
    named = [
        dict(name="cash_zero_false_dump", own=[["BUY_PRODUCT", "WHEAT", 200]], cash=0),
        dict(name="shed_full_false_dump", own=[["BUY_PRODUCT", "WHEAT", 200]],
             stock={"MILK": 100}),
        dict(name="cash_partial", own=[["BUY_PRODUCT", "WHEAT", 200]], cash=52),
        dict(name="capacity_partial", own=[["BUY_PRODUCT", "FERTILIZER", 200]],
             stock={"MILK": 99}),
        dict(name="unsupported_buy", own=[["BUY_PRODUCT", "MILK", 200]]),
        dict(name="raw_dead_suffix", own=[[]] * 10 + [["BUY_PRODUCT", "WHEAT", 200]]),
        dict(name="blank_owns_slot", own=[[], ["BUY_PRODUCT", "WHEAT", 200]],
             cfg={"maxMarketOrdersPerTurn": 1}),
        dict(name="normalized_zero_cap", own=[[], ["BUY_PRODUCT", "WHEAT", 200]],
             cfg={"maxMarketOrdersPerTurn": 0}),
        dict(name="invalid_rows", own=[None, {}, [], ["BUY_PRODUCT", "WHEAT", False],
             ["BUY_PRODUCT", "WHEAT", "bad"], ["BUY_PRODUCT", "MILK", 200]]),
        dict(name="partial_sell_hides_rival", own=[["SELL", "WHEAT", 200]],
             stock={"WHEAT": 3}, rival=[["SELL", "WHEAT", 20]], rival_stock={"WHEAT": 20}),
        dict(name="floor_sold_not_admitted", own=[["SELL", "MILK", 50]],
             stock={"MILK": 50}, inventory={"MILK": 10077}),
        dict(name="paired_floor_crossing", own=[["SELL", "MILK", 2]], stock={"MILK": 2},
             rival=[["SELL", "MILK", 2]], rival_stock={"MILK": 2}, inventory={"MILK": 10075}),
        dict(name="buy_sell_buy", own=[["BUY_PRODUCT", "WHEAT", 30],
             ["SELL", "WHEAT", 30], ["BUY_PRODUCT", "WHEAT", 30]], cash=120),
        dict(name="unsupported_plus_rival", own=[["BUY_PRODUCT", "MILK", 200]],
             rival=[["SELL", "MILK", 20]], rival_stock={"MILK": 20}),
        dict(name="town_crosses_zero", step=0, shops=["BAKERY", "YARN_STORE", "YARN_STORE"],
             inventory={"WHEAT": 0, "WOOL": 0}),
        dict(name="negative_market_inventory", step=24, shops=["BAKERY"],
             inventory={"WHEAT": -5, "MILK": -1}),
        dict(name="eod_shop_chronology", step=71, shops=["BAKERY"],
             cfg={"townShopSellInterval": 1}),
        dict(name="eod_carry_is_not_market", step=119, stock={"WHEAT": 97},
             carried={"WHEAT": 7}, own=[["SELL", "WHEAT", 5]]),
        dict(name="unit_drop_precedes_market", stock={"WHEAT": 97}, carried={"WHEAT": 7},
             farmer=["DROP"], own=[["SELL", "WHEAT", 5]]),
        dict(name="non_product_cash_competition", cash=350, own=[["BUY_ANIMAL", "GOOSE", 1],
             ["BUY_SEED", "WHEAT", 4], ["HIRE"], ["BUY_PRODUCT", "WHEAT", 200]]),
        dict(name="floor_lifted_by_rival_buy", stock={"FERTILIZER": 8},
             own=[["SELL", "FERTILIZER", 8]], rival=[["BUY_PRODUCT", "FERTILIZER", 100]],
             inventory={"FERTILIZER": 10493}),
        dict(name="numeric_quantity_forms", own=[["BUY_PRODUCT", "WHEAT", "3"],
             ["SELL", "WHEAT", 1.9], ["BUY_PRODUCT", "FERTILIZER", True]]),
    ]
    rng = random.Random(20260912)
    products = ("WHEAT", "FERTILIZER", "MILK", "CARROT", "WOOL", "EGG")
    for index in range(random_worlds):
        item = rng.choice(products)
        stock = rng.randrange(101)
        rival_stock = rng.randrange(101)
        def queue():
            out = []
            for _ in range(rng.randrange(1, 13)):
                op = rng.choice(("BUY_PRODUCT", "SELL", "BUY_SEED", "HIRE", "blank"))
                out.append([] if op == "blank" else ["HIRE"] if op == "HIRE"
                           else [op, rng.choice((item, "WHEAT", "FERTILIZER")), rng.randrange(1, 201)])
            return out
        named.append(dict(name=f"mixed_{index:03d}", stock={item: stock},
             rival_stock={item: rival_stock}, cash=rng.choice((0, 25, 100, 500, 100_000)),
             rival_cash=rng.choice((0, 100, 100_000)), own=queue(), rival=queue(),
             step=rng.choice((0, 1, 4, 23, 24, 71, 119)),
             shops=rng.choice(([], ["BAKERY"], ["YARN_STORE", "YARN_STORE"])),
             inventory={item: rng.choice((-3, 9980, 10000, 10075, 10500))},
             cfg={"maxMarketOrdersPerTurn": rng.choice((0, 1, 3, 10))}))
    for spec in named:
        for seat in (0, 1):
            yield dict(spec, seat=seat)


def fixture(engine, spec):
    cfg = Struct({k: v.get("default") if isinstance(v, dict) else v
                  for k, v in engine.specification["configuration"].items()})
    cfg.weedSpawnChance = 0
    cfg.update(spec.get("cfg", {}))
    seat = spec["seat"]
    money = [spec.get("rival_cash", 100_000)] * 2
    money[seat] = spec.get("cash", 100_000)
    farms = [engine._new_farm(10, n) for n in money]
    market = engine._new_market()
    market["inventory"].update(spec.get("inventory", {}))
    engine._refresh_prices(market)
    town = {"unlocked_shops": list(spec.get("shops", []))}
    step = spec.get("step", 1)
    tpd = max(1, int(cfg.turnsPerDay))
    state = []
    for who in (0, 1):
        private = engine._new_private()
        private["shed"].update(spec.get("stock" if who == seat else "rival_stock", {}))
        if who == seat:
            private["inventories"][0].update(spec.get("carried", {}))
        action = {"farmer": spec.get("farmer", ["PASS"]) if who == seat else ["PASS"],
                  "hands": [], "market": copy.deepcopy(spec.get("own" if who == seat else "rival", []))}
        obs = Struct(player=who, step=step, day=step // tpd, hour=step % tpd, farms=farms,
                     private=private, market=market, town=town)
        state.append(Struct(observation=obs, action=action, status="ACTIVE", reward=0))
    return state, Struct(configuration=cfg, done=False, info={"seed": 20260912})


def run_case(engine, spec):
    """Execute both audited and pristine engine worlds, retaining exact truth."""
    state, env = fixture(engine, spec)
    pristine, penv = copy.deepcopy((state, env))
    seat, products = spec["seat"], engine.PRODUCTS
    previous = copy.deepcopy(state[seat].observation)
    submitted = copy.deepcopy(state[seat].action)
    admitted = [{p: 0 for p in products} for _ in (0, 1)]
    physical = [{"SELL": {}, "BUY_PRODUCT": {}} for _ in (0, 1)]
    town_delta = {p: 0 for p in products}
    commits = []
    original_commit, original_town = engine._commit_unit, engine._town_consume
    private_ids = {id(s.observation.private): who for who, s in enumerate(state)}

    def audited_commit(op, item, price, farm, private, market, shed_capacity=100):
        who = private_ids[id(private)]
        old = dict(market["inventory"])
        ok = original_commit(op, item, price, farm, private, market, shed_capacity)
        if ok and op in ("SELL", "BUY_PRODUCT"):
            physical[who][op][item] = physical[who][op].get(item, 0) + 1
            change = market["inventory"][item] - old[item]
            admitted[who][item] += change
            commits.append([who, op, item, price, change])
        return ok

    def audited_town(e, s, step):
        old = dict(s[0].observation.market["inventory"])
        result = original_town(e, s, step)
        for p in products:
            town_delta[p] += s[0].observation.market["inventory"][p] - old[p]
        return result

    try:
        engine._commit_unit, engine._town_consume = audited_commit, audited_town
        with redirect_stdout(io.StringIO()):
            engine.interpreter(state, env)
    finally:
        engine._commit_unit, engine._town_consume = original_commit, original_town
    with redirect_stdout(io.StringIO()):
        engine.interpreter(pristine, penv)
    if state != pristine or env != penv:
        raise ValueError("audit wrapper changed full interpreter state")
    for s in state:
        s.observation.step = previous["step"] + 1  # actual framework index advance
    current = copy.deepcopy(state[seat].observation)
    for p in products:
        observed = current["market"]["inventory"][p] - previous["market"]["inventory"][p]
        if observed != admitted[0][p] + admitted[1][p] + town_delta[p]:
            raise ValueError(f"market mass-balance failed: {p}")
    # Only this player's ordinary public+own-private observations enter the
    # candidate packet. No rival action, rival private, env seed, or audit trace.
    cfg_input = {k: v for k, v in env.configuration.items() if k != "seed"}
    record = {
        "id": f"{spec['name']}/seat{seat}",
        "input": {"previous": previous, "current": current,
                  "submitted_action": submitted, "configuration": cfg_input},
        "oracle": {"own_admitted_net": admitted[seat],
                   "opponent_admitted_net": admitted[1-seat],
                   "own_physical_fills": physical[seat],
                   "opponent_physical_fills": physical[1-seat],
                   "town_inventory_delta": town_delta,
                   "unit_commit_count": len(commits),
                   "unit_trace_sha256": hashlib.sha256(encoded(commits)).hexdigest(),
                   "full_state_sha256": hashlib.sha256(encoded(state)).hexdigest(),
                   "audit_matches_pristine": True},
    }
    return record


def build_corpus(engine, random_worlds=96):
    return [run_case(engine, spec) for spec in cases(random_worlds)]


def corpus_bytes(records):
    return b"".join(encoded(record) + b"\n" for record in records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="NEW JSONL path; never overwritten")
    parser.add_argument("--random-worlds", type=int, default=96)
    args = parser.parse_args()
    try:
        if not 0 <= args.random_worlds <= 1000:
            raise ValueError("random-worlds must be between 0 and 1000")
        if args.output.exists():
            raise FileExistsError("output already exists")
        records = build_corpus(load_engine(args.engine), args.random_worlds)
        data = corpus_bytes(records)
        with args.output.open("xb") as handle:
            handle.write(data)
        print(json.dumps({"cases": len(records), "interpreter_calls": 2*len(records),
              "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"flow corpus rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Per-product cash ledger for a continuation, for BOTH seats.

Both seats' cash rose together in two runs while margin barely moved. Calling that
shared-market inflation is a story until the money is attributed. This wraps the
engine's own commit and consumption functions during a replay and records every fill
with its item, unit price and seat, so the cash difference between an arm and its
control can be read per product rather than asserted.

Nothing here re-implements pricing: `_commit_unit`, `market_price` and `_town_consume`
are the engine's, and the wrappers only observe them.
"""

import argparse
import collections
import json
import os

import cards as cards_mod
import continuation as C
from constraints import engine


def _wrap(K, records, owners):
    """Record every committed market unit and every harvest, attributed by seat.

    The engine passes the acting seat's own farm dict into both functions and never
    names the seat, so the seat is recovered the way cloud-frontier-trace/analyze.py
    recovers it: by identity of that farm object. `owners` maps id(farm) -> seat and
    is refreshed each step, because the interpreter rebuilds the observation objects.
    """
    original_commit = K._commit_unit
    original_apply = K._apply_unit_action

    def commit(op, item, price, farm, private, market, shed_capacity=100):
        ok = original_commit(op, item, price, farm, private, market, shed_capacity)
        if ok:
            records["market"].append({"seat": owners.get(id(farm)), "op": op,
                                      "item": item, "price": float(price)})
        return ok

    def apply_unit(farm, private, idx, action, board_size, day, turns_per_day,
                   shed_capacity=100):
        before = None
        if isinstance(action, list) and action and action[0] == "HARVEST":
            pos = K._farmer_position(farm, idx)
            if pos:
                t = farm["tiles"][int(pos[1])][int(pos[0])]
                if isinstance(t, dict):
                    before = dict(t)
        result = original_apply(farm, private, idx, action, board_size, day,
                                turns_per_day, shed_capacity)
        if before:
            units = int(before.get("yield_units", 0))
            if units > 0:
                item = before["crop"] if before.get("kind") == "PLANT" else \
                    K.ANIMALS[before["animal"]]["product"]
                records["harvest"].append({"seat": owners.get(id(farm)),
                                           "item": item, "units": units})
        return result

    K._commit_unit = commit
    K._apply_unit_action = apply_unit
    return (original_commit, original_apply)


def _unwrap(K, originals):
    K._commit_unit, K._apply_unit_action = originals


def run(seed, seat, prefix_actions, warmup_spec, opponent_spec, cont_spec, from_step,
        control=False):
    """Replay an arm and return its per-product ledger for both seats."""
    K = engine()
    records = {"market": [], "harvest": []}
    owners = {}
    originals = _wrap(K, records, owners)
    try:
        warm, warm_id = C.load_agent(warmup_spec)
        opp, opp_id = C.load_agent(opponent_spec)
        cont, cont_id = C.load_agent(cont_spec)
        env = cards_mod.make_env(seed)
        env.reset(2)
        used = 0
        while not env.done:
            cfg = env.configuration
            obs = env.state[seat].observation
            step = int(obs["day"]) * int(cfg["turnsPerDay"]) + int(obs["hour"])
            if step < from_step:
                mine = warm(obs, cfg)
            elif control:
                mine = cont(obs, cfg)
            elif used < len(prefix_actions):
                mine = prefix_actions[used]
                used += 1
            else:
                mine = cont(obs, cfg)
            actions = [None, None]
            actions[seat] = mine
            actions[1 - seat] = opp(env.state[1 - seat].observation, cfg)
            # Refresh the owner map: the interpreter mutates the farm dicts in place
            # for a step, so their identities are stable within it.
            owners.clear()
            for s_i, f in enumerate(env.state[0].observation.farms):
                owners[id(f)] = s_i
            env.step(actions)
        farms = env.state[0].observation.farms
        result = {
            "seed": seed, "seat": seat, "from_step": from_step, "control": bool(control),
            "model_turns_applied": used,
            "final_cash": float(farms[seat]["money"]),
            "opponent_cash": float(farms[1 - seat]["money"]),
            "margin": float(farms[seat]["money"]) - float(farms[1 - seat]["money"]),
            "warmup": warm_id, "opponent": opp_id, "continuation": cont_id,
        }
    finally:
        _unwrap(K, originals)

    def per_seat():
        books = {}
        for s_i in (0, 1):
            sold = collections.Counter(); sold_coins = collections.Counter()
            bought = collections.Counter(); bought_coins = collections.Counter()
            for r in records["market"]:
                if r["seat"] != s_i:
                    continue
                if r["op"] == "SELL":
                    sold[r["item"]] += 1
                    sold_coins[r["item"]] += r["price"]
                else:
                    bought[r["item"]] += 1
                    bought_coins[r["item"]] += r["price"]
            harvested = collections.Counter()
            for r in records["harvest"]:
                if r["seat"] == s_i:
                    harvested[r["item"]] += r["units"]
            books[s_i] = {
                "sold_units": dict(sold),
                "sold_coins": {k: round(v) for k, v in sold_coins.items()},
                "bought_units": dict(bought),
                "bought_coins": {k: round(v) for k, v in bought_coins.items()},
                "harvested_units": dict(harvested),
                "gross_sales": round(sum(sold_coins.values())),
                "gross_spend": round(sum(bought_coins.values())),
            }
        return books

    books = per_seat()
    unattributed = sum(1 for r in records["market"] if r["seat"] is None) + \
        sum(1 for r in records["harvest"] if r["seat"] is None)
    result["ledger"] = {"mine": books[seat], "opponent": books[1 - seat],
                        "unattributed_events": unattributed}
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", default=[])
    ap.add_argument("--warmup", default="../cloud-market/main.py::agent")
    ap.add_argument("--opponent", default="../cloud-market/main.py::agent")
    ap.add_argument("--continuation", default="../cloud-market/main.py::agent")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = []
    control_done = set()
    for path in a.run:
        d = json.load(open(path))
        prefix = [{"farmer": t["action"]["farmer"], "hands": t["action"]["hands"],
                   "market": t["action"]["market"]} for t in d.get("turns", [])]
        r = run(d["seed"], d["seat"], prefix, a.warmup, a.opponent, a.continuation,
                d["from_step"])
        r["label"] = os.path.basename(path)
        out.append(r)
        key = (d["seed"], d["seat"], d["from_step"])
        if key not in control_done:
            control_done.add(key)
            c = run(d["seed"], d["seat"], [], a.warmup, a.opponent, a.continuation,
                    d["from_step"], control=True)
            c["label"] = "control"
            out.append(c)
    for r in out:
        print(json.dumps(r, sort_keys=True))
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(out, fh, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()

"""Where does the cap+SELL composition lose the money? Read the receipts.

T08's held panel isolates one failing pair: seed 9780119, seat 0, versus Arlene.
Composed 58,066-58,103 loses 37; frozen SELL 58,178-58,141 wins 37; paired margin
-74. Its published day-boundary banks already narrow the cause without any replay:
the two arms differ on exactly five days, and each cap gain is followed by a loss.

    day 18  +2      day 19  -2      cancels exactly
    day 26  +120    day 27  -263    over-cancels by 143
    day 29  +31

If this were only timing -- the same units sold a day earlier -- day 26 and day 27
would cancel like 18 and 19 do. They do not, so 143 of own cash is destroyed
rather than moved.

This replays ONLY that game, for both arms, with the engine's own market commit
wrapped so every executed order is attributed to a seat with its unit price, and
with the seat's shed and carried stock sampled each turn. It answers which of the
three candidates does the damage:

  physical harvest plan     the extra cargo displaces base harvests or deposits,
                            so fewer units reach the shed at all
  arrival capacity envelope the composition reserves capacity the scheduler then
                            declines to sell into, so fewer units are SOLD
  SELL choice               the same units are sold for less, or different products

The arms are T08's own published modules, imported and run unmodified.
"""

import argparse
import copy
import importlib.util
import json
import os
import sys

import cards as cards_mod
import route_cards

T08 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "cloud-titan-composition")


def load_arm(name):
    """Import one of T08's published arms by path. Read-only; never edited."""
    path = os.path.join(T08, "arms", f"{name}.py")
    spec = importlib.util.spec_from_file_location(f"t08_{name}",
                                                  os.path.realpath(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.agent


def run(seed, seat, arm_name, opponent="arlene"):
    from kaggle_environments.envs.kaggriculture import kaggriculture as K
    import arlene_arm
    A, _ = route_cards.load_arlene()
    opp, _ = arlene_arm.make_opponent(opponent, A)
    agent = load_arm(arm_name)

    orders, owners = [], {}
    orig_commit, orig_market = K._commit_unit, K._process_market
    day_now = {"step": 0}

    def commit(op, item, price, farm, private, market, shed_capacity=100):
        ok = orig_commit(op, item, price, farm, private, market, shed_capacity)
        if ok:
            orders.append({"step": day_now["step"], "day": day_now["step"] // 24,
                           "seat": owners.get(id(farm)), "op": op, "item": item,
                           "price": float(price)})
        return ok

    def process_market(state, env_):
        owners.clear()
        for s_i, f in enumerate(state[0].observation.farms):
            owners[id(f)] = s_i
        return orig_market(state, env_)

    K._commit_unit, K._process_market = commit, process_market
    env = cards_mod.make_env(seed)
    env.reset(2)
    stock = []
    try:
        while not env.done:
            acts = [None, None]
            obs0 = env.state[seat].observation
            step = int(obs0["day"]) * 24 + int(obs0["hour"])
            day_now["step"] = step
            priv = obs0["private"]
            farm = obs0["farms"][seat]
            held = 0
            for row in farm["tiles"]:
                for t in row:
                    if isinstance(t, dict) and t.get("animal") is not None:
                        held += int(t.get("yield_units", 0))
            stock.append({
                "step": step, "day": step // 24,
                "shed": {k: int(v) for k, v in (priv.get("shed") or {}).items() if v},
                "shed_used": sum(int(v) for v in (priv.get("shed") or {}).values()),
                "carried": sum(int(n) for inv in (priv.get("inventories") or [])
                               for n in inv.values()),
                "held_on_animals": held,
                "cash": float(farm["money"]),
            })
            for i in range(2):
                obs = env.state[i].observation
                acts[i] = (agent(obs, env.configuration) if i == seat
                           else opp(obs, env.configuration))
            env.step(acts)
    finally:
        K._commit_unit, K._process_market = orig_commit, orig_market
    farms = env.state[0].observation.farms
    return {"arm": arm_name, "seed": seed, "seat": seat, "opponent": opponent,
            "own_cash": float(farms[seat]["money"]),
            "rival_cash": float(farms[1 - seat]["money"]),
            "orders": orders, "stock": stock}


def day_report(res, seat, day):
    o = [r for r in res["orders"] if r["seat"] == seat and r["day"] == day]
    sells = [r for r in o if r["op"] == "SELL"]
    buys = [r for r in o if r["op"] != "SELL"]
    by = {}
    for r in sells:
        e = by.setdefault(r["item"], {"units": 0, "cash": 0.0})
        e["units"] += 1
        e["cash"] += r["price"]
    return {"sell_units": len(sells),
            "sell_cash": round(sum(r["price"] for r in sells), 1),
            "buy_units": len(buys),
            "buy_cash": round(sum(r["price"] for r in buys), 1),
            "by_product": {k: {"units": v["units"], "cash": round(v["cash"], 1),
                               "avg": round(v["cash"] / v["units"], 2)}
                           for k, v in sorted(by.items())}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=9780119)
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--opponent", default="arlene")
    ap.add_argument("--arms", nargs="+", default=["sell", "carrot_cap_sell_conserved"])
    ap.add_argument("--days", type=int, nargs="+", default=[18, 19, 26, 27, 29])
    ap.add_argument("--out", default="results/interaction-probe.json")
    a = ap.parse_args()
    res = {}
    for arm in a.arms:
        r = run(a.seed, a.seat, arm, a.opponent)
        res[arm] = r
        print(f"{arm:30s} own {r['own_cash']:9.0f}  rival {r['rival_cash']:9.0f}",
              flush=True)
    base, comp = a.arms[0], a.arms[-1]
    print(f"\nseed {a.seed} seat {a.seat} vs {a.opponent}: "
          f"{comp} minus {base}, own-seat receipts by day")
    print(f"{'day':>4} | {'units':>16} | {'sale cash':>19} | {'buys':>15}")
    for d in a.days:
        x, y = day_report(res[base], a.seat, d), day_report(res[comp], a.seat, d)
        print(f"{d:4d} | {x['sell_units']:6d} -> {y['sell_units']:6d} "
              f"({y['sell_units'] - x['sell_units']:+3d}) | "
              f"{x['sell_cash']:8.0f} -> {y['sell_cash']:8.0f} "
              f"({y['sell_cash'] - x['sell_cash']:+6.0f}) | "
              f"{x['buy_cash']:6.0f} -> {y['buy_cash']:6.0f}")
        prods = set(x["by_product"]) | set(y["by_product"])
        for p in sorted(prods):
            xa = x["by_product"].get(p, {"units": 0, "cash": 0.0, "avg": 0})
            ya = y["by_product"].get(p, {"units": 0, "cash": 0.0, "avg": 0})
            if xa != ya:
                print(f"       {p:12s} units {xa['units']:4d} -> {ya['units']:4d}"
                      f"   cash {xa['cash']:8.0f} -> {ya['cash']:8.0f}"
                      f"   avg price {xa['avg']:7.2f} -> {ya['avg']:7.2f}")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(res, open(a.out, "w"), default=str)


if __name__ == "__main__":
    main()

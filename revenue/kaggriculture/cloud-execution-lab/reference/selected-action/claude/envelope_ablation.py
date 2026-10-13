"""Fixed-state ablation: does the capacity ENVELOPE change when SELL liquidates?

Equal total units over a game rules out a throughput loss. It does not rule out
the envelope changing WHEN the optimizer chooses to sell, which is the mechanism
the per-day receipts could not separate. This separates it directly.

Everything is held fixed and taken from a retained observation: the observed
state, the physical producer (the same committed cap errand and the same selected
unit actions), the optimizer itself, and the opponent assumption. The ONLY thing
that varies is the capacity envelope handed to the optimizer:

  (a) coarse      the immediate reserve: visible held animal yield plus carried
                  stock subtracted from capacity now. T08's 8W/2T/2L branch.
  (b) dated       the committed whole-lot envelope, each possible deposit
                  protected at its earliest physical date and phase, which for a
                  one-way errand is this day's close, after market.
  (c) none        no extra reservation. Diagnostic floor, not a proposal.

For each choice this records what the optimizer scheduled, what the pinned
interpreter actually paid for it, which constraint bound, and what the shed
admitted. No game is re-run: the saved decision answers the question.

The states are development-seed observations (9810001, seat 0) retained in
fixtures/cap-midgame-errand.json. The consumed held loss at 9780119 is not used
as validation here.
"""

import argparse
import copy
import importlib.util
import json
import os
import sys

T08 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "cloud-titan-composition")


def load_t08():
    """Import T08's adapters unmodified, with their own vendor path."""
    for p in (os.path.join(T08, "vendor", "sell"), T08):
        rp = os.path.realpath(p)
        if rp not in sys.path:
            sys.path.insert(0, rp)
    import sell_adapter
    import conserved_sell_adapter
    return sell_adapter, conserved_sell_adapter


def coarse_reserve(obs, seat):
    """The immediate envelope: everything visibly unbanked, reserved right now."""
    from kaggle_environments.envs.kaggriculture import kaggriculture as K
    farm, priv = obs["farms"][seat], obs["private"]
    total = sum(int(n) for inv in (priv.get("inventories") or [])
                for n in inv.values())
    for row in farm["tiles"]:
        for t in row:
            if isinstance(t, dict) and t.get("animal") is not None:
                total += max(0, int(t.get("yield_units", 0)))
    return total


def market_only(obs, cfg, seat, action):
    """Run the pinned market phase alone on this fixed state.

    The opponent is given the engine's default PASS. That is a declared
    counterfactual, identical across all three arms, so it cannot favour one.
    """
    from kaggle_environments.envs.kaggriculture import kaggriculture as K
    from kaggle_environments.utils import structify
    other = 1 - seat
    a = copy.deepcopy(dict(obs))
    b = copy.deepcopy(dict(obs))
    b["player"] = other
    b["private"] = {"shed": {}, "inventories": [{}], "seeds": {}}
    b["farms"] = a["farms"]
    states = [None, None]
    states[seat] = {"observation": a, "action": copy.deepcopy(action),
                    "status": "ACTIVE", "reward": 0.0}
    states[other] = {"observation": b,
                     "action": {"farmer": ["PASS"], "hands": [], "market": []},
                     "status": "ACTIVE", "reward": 0.0}
    st = structify(states)
    env = structify({"configuration": dict(cfg), "done": False, "info": {"seed": 0}})
    before_cash = float(a["farms"][seat]["money"])
    before_shed = dict(a["private"].get("shed") or {})
    K._process_market(st, env)
    farms = st[0].observation.farms
    priv = st[seat].observation.private
    after_shed = {k: int(v) for k, v in (priv.get("shed") or {}).items() if v}
    return {
        "cash_receipts": round(float(farms[seat]["money"]) - before_cash, 1),
        "shed_before": {k: int(v) for k, v in before_shed.items() if v},
        "shed_after": after_shed,
        "shed_used_after": sum(after_shed.values()),
        "admitted": {k: after_shed.get(k, 0) - int(before_shed.get(k, 0))
                     for k in set(after_shed) | set(before_shed)
                     if after_shed.get(k, 0) != int(before_shed.get(k, 0))},
    }


def sells(action):
    return [o for o in (action.get("market") or [])
            if o and o[0] == "SELL"]


def run_frame(frame, cfg, seat, base_owner_factory):
    sell_adapter, conserved = load_t08()
    obs = frame["observation"]
    selected = frame["selected_action"]
    reserve = coarse_reserve(obs, seat)
    arms = {}
    for name in ("none", "coarse", "dated"):
        owner = base_owner_factory()
        if name == "dated":
            tx = conserved.DatedSelectedActionSell(owner)
            kw = {}
        else:
            tx = sell_adapter.SelectedActionSell(owner)
            kw = {"extra_capacity_reserve": reserve if name == "coarse" else 0}
        try:
            out = tx.transform(obs, cfg, copy.deepcopy(selected), **kw)
        except Exception as exc:
            arms[name] = {"error": f"{type(exc).__name__}: {exc}"}
            continue
        eng = market_only(obs, cfg, seat, out)
        arms[name] = {
            "reserve_units": reserve if name == "coarse" else 0,
            "scheduled_sales": [list(o) for o in sells(out)],
            "scheduled_units": sum(int(o[2]) for o in sells(out) if len(o) > 2),
            "orders_total": len(out.get("market") or []),
            "engine_receipts": eng["cash_receipts"],
            "shed_admitted": eng["admitted"],
            "shed_used_after": eng["shed_used_after"],
            "diagnostics": {k: v for k, v in
                            (getattr(tx, "diagnostics", {}) or {}).items()},
            "unit_actions_unchanged": (out.get("farmer") == selected.get("farmer")
                                       and out.get("hands") == selected.get("hands")),
        }
    return arms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", default="fixtures/cap-midgame-errand.json")
    ap.add_argument("--out", default="results/envelope-ablation.json")
    a = ap.parse_args()
    import route_cards
    A, _ = route_cards.load_arlene()
    fx = json.load(open(a.fixture))
    seat = fx["seat"]
    cfg = {"turnsPerDay": 24, "episodeSteps": 720, "shedCapacity": 100,
           "boardSize": 10, "maxMarketOrdersPerTurn": 10, "farmHandCostMult": 1}
    rows = []
    for frame in fx["frames"]:
        if frame.get("tracked_row") is None:
            continue
        arms = run_frame(frame, cfg, seat, lambda: A.Agent())
        rows.append({"step": frame["step"], "day": frame["day"],
                     "hour": frame["hour"],
                     "tracked": frame["tracked_row"], "arms": arms})
        r = frame["tracked_row"]
        print(f"step {frame['step']} d{frame['day']}h{frame['hour']:02d}  errand "
              f"{r['status']} {r['units_total']}u total / {r['units_incremental']}u "
              f"incremental, arrival {r['arrival_step']}")
        for name in ("none", "coarse", "dated"):
            v = arms[name]
            if "error" in v:
                print(f"    {name:7s} ERROR {v['error']}")
                continue
            print(f"    {name:7s} reserve {v['reserve_units']:3d}  "
                  f"scheduled {v['scheduled_units']:3d}u in {len(v['scheduled_sales'])} "
                  f"order(s)  engine receipts {v['engine_receipts']:9.1f}  "
                  f"shed after {v['shed_used_after']:3d}  "
                  f"units unchanged={v['unit_actions_unchanged']}")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"fixture": a.fixture, "seed": fx["seed"], "seat": seat,
               "config": cfg, "rows": rows}, open(a.out, "w"), indent=1, default=str)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()

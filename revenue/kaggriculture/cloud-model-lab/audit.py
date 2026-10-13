"""Contract audit: run a candidate through real games and count engine-visible waste.

Every defect counted here is defined by the pinned engine, not by an opinion about
play. A turn's ops are replayed against the pre-turn state with the engine's own
`_apply_unit_action`, and the daily/terminal losses are read off the engine's own
gates:

  no_op_unit_ops     ops the engine silently ignored -- the unit's turn was spent
  plant_blocks       PLANT requests dropped by the atomic joint seed budget
  market_dropped     orders past maxMarketOrdersPerTurn, silently discarded
  plants_weeded      plants at consecutive_unwatered >= 2 entering the daily refresh
  overflow_discarded carried units above shed room at the end-of-day drop
  terminal_unsold    shed units still held at the last decision -- worth 0, the
                     terminal reward is cash only

These are pure waste: fixing one cannot lower the score, because each is an action
the engine threw away or a unit the engine deleted.
"""

import argparse
import copy
import json
import os

import cards as cards_mod
import constraints
from constraints import engine


def _agent_from(spec):
    """'path.py::name' or a built-in engine agent name."""
    if "::" not in spec:
        return spec, spec
    path, name = spec.split("::", 1)
    import importlib.util
    mod_name = os.path.splitext(os.path.basename(path))[0] + "_cand"
    sp = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    return getattr(mod, name), f"{os.path.basename(path)}::{name}"


def audit_episode(seed, agent_spec, opponent="starter", seat=0):
    K = engine()
    agent, label = _agent_from(agent_spec)
    opp, _ = _agent_from(opponent)
    env = cards_mod.make_env(seed)
    players = [agent, opp] if seat == 0 else [opp, agent]
    env.run(players)
    cfg = dict(env.configuration)
    tpd = int(cfg.get("turnsPerDay", 24))
    cap = int(cfg.get("shedCapacity", 100))
    board = int(cfg.get("boardSize", 10))
    max_orders = int(cfg.get("maxMarketOrdersPerTurn", 10))

    m = {"no_op_unit_ops": 0, "unit_ops": 0, "plant_blocks": 0, "market_dropped": 0,
         "plants_weeded": 0, "overflow_discarded": 0, "terminal_unsold": 0,
         "turns": 0, "pass_ops": 0}
    no_op_by_op = {}
    op_total = {}
    for i, step in enumerate(env.steps):
        s = step[seat]
        if s["status"] != "ACTIVE":
            continue
        obs = s["observation"]
        action = s["action"] if isinstance(s["action"], dict) else {}
        if not obs.get("farms"):
            continue
        m["turns"] += 1
        day = int(obs["day"])
        farm, priv = obs["farms"][seat], obs["private"]

        units = [action.get("farmer", ["PASS"])] + list(action.get("hands", []) or [])
        demand = {}
        for idx, act in enumerate(units):
            if not isinstance(act, list) or not act:
                continue
            m["unit_ops"] += 1
            if act[0] == "PASS":
                m["pass_ops"] += 1
                continue
            if len(act) >= 2 and act[0] == "PLANT":
                demand[act[1]] = demand.get(act[1], 0) + 1
            f2, p2 = copy.deepcopy(farm), copy.deepcopy(priv)
            before = (copy.deepcopy(f2), copy.deepcopy(p2))
            try:
                K._apply_unit_action(f2, p2, idx, list(act), board, day, tpd, cap)
            except Exception:
                pass
            op_total[act[0]] = op_total.get(act[0], 0) + 1
            if (f2, p2) == before:
                m["no_op_unit_ops"] += 1
                no_op_by_op[act[0]] = no_op_by_op.get(act[0], 0) + 1
        seeds = priv.get("seeds", {})
        for crop, n in demand.items():
            if n > seeds.get(crop, 0):
                m["plant_blocks"] += n

        orders = action.get("market", []) or []
        if len(orders) > max_orders:
            m["market_dropped"] += len(orders) - max_orders

        # End-of-day losses, evaluated exactly where the engine evaluates them.
        if (int(obs.get("step", i)) + 1) % tpd == 0:
            for row in farm["tiles"]:
                for tile in row:
                    if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                        u = tile.get("consecutive_unwatered", 0) + (0 if tile.get("watered_today") else 1)
                        if u >= 2:
                            m["plants_weeded"] += 1
            carried = sum(sum(inv.values()) for inv in priv.get("inventories", []))
            room = max(0, cap - sum(priv.get("shed", {}).values()))
            if carried > room:
                m["overflow_discarded"] += carried - room

    last = env.steps[-1][seat]["observation"]
    if last.get("private"):
        m["terminal_unsold"] = int(sum(last["private"].get("shed", {}).values()))
    m["final_money"] = float(env.steps[-1][seat]["reward"] or
                             env.steps[-1][0]["observation"]["farms"][seat]["money"])
    m["opponent_money"] = float(env.steps[-1][1 - seat]["reward"] or 0.0)
    m["margin"] = m["final_money"] - m["opponent_money"]
    m["no_op_by_op"] = dict(sorted(no_op_by_op.items(), key=lambda kv: -kv[1]))
    m["op_total"] = dict(sorted(op_total.items(), key=lambda kv: -kv[1]))
    m["seed"], m["seat"], m["agent"] = seed, seat, label
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, help="path.py::name or a built-in name")
    ap.add_argument("--opponent", default="starter")
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--seats", default="0,1")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rows = []
    for seed in [int(s) for s in a.seeds.split(",")]:
        for seat in [int(s) for s in a.seats.split(",")]:
            r = audit_episode(seed, a.agent, a.opponent, seat)
            rows.append(r)
            print(f"seed{r['seed']} seat{r['seat']} money={r['final_money']:.0f} "
                  f"margin={r['margin']:+.0f} | no_op={r['no_op_unit_ops']}/{r['unit_ops']} "
                  f"pass={r['pass_ops']} weeded={r['plants_weeded']} "
                  f"plant_blocks={r['plant_blocks']} overflow={r['overflow_discarded']} "
                  f"unsold={r['terminal_unsold']} dropped_orders={r['market_dropped']}")
    if rows:
        n = len(rows)
        agg = {k: sum(r[k] for r in rows) / n for k in
               ("final_money", "margin", "no_op_unit_ops", "unit_ops", "pass_ops",
                "plants_weeded", "plant_blocks", "overflow_discarded",
                "terminal_unsold", "market_dropped")}
        print("\nmean over %d games: " % n + " ".join(f"{k}={v:.1f}" for k, v in agg.items()))
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w") as fh:
            json.dump(rows, fh, indent=1)


if __name__ == "__main__":
    main()

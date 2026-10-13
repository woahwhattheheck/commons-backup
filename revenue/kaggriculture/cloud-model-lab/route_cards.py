"""Economically active decision cards taken from real Arlene trajectories.

Arlene (vendor/arlene.py, sha 1dc166ae..., Apache-2.0, notices in
../cloud-frontier-policy/next-panel/) replays long route tapes and already carries
its own predicate for a slot the engine will ignore -- `_noop` -- which it reuses
for exactly one purpose, turning a wasted turn spent standing on a weed into a DIG.

This harvests the rest of that idle capacity as decision cards, and only where the
capacity is economically LIVE. A card is emitted for step s and worker i when:

  1. Arlene's own `_noop` says the engine will ignore what it plays in that slot,
     AFTER Arlene's repairs -- so nothing the route depends on is displaced;
  2. the tile the worker already stands on offers an op the ENGINE will act on and
     that pays: CARE on an animal already fed today (the refresh pays care only
     when fed_today is set, kaggriculture.py 829-830), HARVEST on real yield,
     COLLECT_FERTILIZER on available fertilizer, FEED on an unfed animal with the
     worker already carrying WHEAT, WATER on the seat's own unwatered plant, PLACE
     of a carried animal onto its matching empty structure;
  3. the remaining schedule does not already cover it. Coverage is measured, not
     assumed: the same episode is played once first and every (step, tile, op) the
     route actually performs is recorded. The window is the one the engine gives
     the op -- a DAY for the ops a daily flag gates (CARE, FEED, WATER,
     COLLECT_FERTILIZER), the REST OF THE EPISODE for the ops that are durable
     (HARVEST, PLACE). Both passes are the same deterministic episode.

That is deliberately the opposite selection to the first motif round, whose CAREs
landed on unfed animals at hours 20-23 and whose WATERs the baseline performed
itself later the same day. Those measured +0 over five paired games.
"""

import argparse
import copy
import importlib.util
import json
import os

import cards as cards_mod
import constraints

ARLENE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "cloud-frontier-policy", "next-panel", "vendor",
                           "arlene.py")
ARLENE_SHA = "1dc166ae2bf0c56a44fac4482f469b8812968c4cb32459cb9860f5077897a7d4"


def load_arlene(path=ARLENE_PATH):
    """Load the exact vendored baseline; refuse a substitute."""
    import hashlib
    rp = os.path.realpath(path)
    sha = hashlib.sha256(open(rp, "rb").read()).hexdigest()
    if sha != ARLENE_SHA:
        raise SystemExit(f"arlene.py sha {sha} != pinned {ARLENE_SHA}")
    sp = importlib.util.spec_from_file_location("arlene_vendored", rp)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    return mod, {"path": rp, "sha256": sha, "label": f"arlene.py@{sha[:12]}"}


def load_agent(spec):
    import hashlib
    if "::" not in spec:
        return spec, {"kind": "builtin", "spec": spec, "label": spec}
    path, name = spec.split("::", 1)
    rp = os.path.realpath(path)
    sp = importlib.util.spec_from_file_location(
        os.path.splitext(os.path.basename(path))[0] + "_rc", rp)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    sha = hashlib.sha256(open(rp, "rb").read()).hexdigest()
    return getattr(mod, name), {"kind": "file", "spec": spec, "path": rp,
                                "sha256": sha,
                                "label": f"{os.path.basename(path)}::{name}@{sha[:12]}"}


def call(agent, obs, config):
    if isinstance(agent, str):
        from kaggle_environments.envs.kaggriculture import kaggriculture as K
        return {"starter": K.starter_agent, "random": K.random_agent,
                "pass": K.pass_agent}[agent](obs)
    try:
        return agent(obs, config)
    except TypeError:
        return agent(obs)


DAILY_OPS = ("CARE", "FEED", "WATER", "COLLECT_FERTILIZER")


def live_ops(tile, inv, x, y, board, A, day, K=None):
    """Ops the ENGINE will act on for a worker standing here, that also PAY.

    Each entry is (op, why). `why` is the economic reason, not a label: it names
    the engine rule that makes the op pay, so a card cannot be justified by
    "something changed".
    """
    out = []
    if not isinstance(tile, dict):
        return out
    if tile.get("animal") is not None:
        if tile.get("yield_units", 0) > 0:
            cap = (K.ANIMALS[tile["animal"]]["max_held"] if K else None)
            at_cap = cap is not None and int(tile["yield_units"]) >= int(cap)
            out.append((["HARVEST"],
                        f"animal holds {tile['yield_units']} unit(s) of product; the "
                        f"animal persists through HARVEST (469-472)"
                        + (f" and is AT its max_held {cap}, so further production is "
                           f"being wasted" if at_cap else
                           f" (max_held {cap})" if cap else "")))
        if tile.get("fed_today") and not tile.get("cared_today"):
            out.append((["CARE"], "animal is already fed today, so the daily refresh "
                                  "pays care on it (829-830); uncared so far"))
        if tile.get("fertilizer_available"):
            out.append((["COLLECT_FERTILIZER"], "fertilizer is standing available on "
                                                "this animal"))
        if not tile.get("fed_today") and inv.get("WHEAT", 0) > 0:
            out.append((["FEED"], "animal is unfed today and this worker already "
                                  "carries the WHEAT to feed it"))
    elif tile.get("kind") == "PLANT":
        if tile.get("yield_units", 0) > 0:
            cd = K.CROPS[tile["crop"]] if K else None
            # A non-ongoing crop is DESTROYED by HARVEST (467-468), so collecting it
            # before it has finished growing forfeits the rest. That cost is stated on
            # the card; it is not silently filtered out.
            if cd and not cd["ongoing"]:
                age = day - int(tile["planted_day"])
                room = int(cd["max_yield"]) - int(tile["yield_units"])
                mature = age >= int(cd["max_yield_day"])
                out.append((["HARVEST"],
                            f"plant holds {tile['yield_units']}/{cd['max_yield']} "
                            f"{tile['crop']}; HARVEST DESTROYS a non-ongoing crop "
                            f"(467-468). age {age}d, max_yield_day "
                            f"{cd['max_yield_day']}: "
                            + ("fully grown, nothing forfeited" if mature or room <= 0
                               else f"{room} more unit(s) would still accrue")))
            else:
                out.append((["HARVEST"],
                            f"plant holds {tile['yield_units']} unit(s); an ongoing "
                            f"crop survives HARVEST and keeps producing (467)"))
        if not tile.get("watered_today"):
            out.append((["WATER"], f"plant is unwatered today, "
                                   f"{tile.get('consecutive_unwatered', 0)} day(s) running"))
    elif tile.get("kind") in ("COOP", "PASTURE") and tile.get("animal") is None:
        for item, struct in A.ANIMALS.items():
            if struct == tile.get("kind") and inv.get(item, 0) > 0:
                out.append(([" PLACE", item, 1][0:1] + [item, 1],
                            f"an empty {struct} under a worker already carrying a "
                            f"{item}"))
    return [([op[0].strip()] + list(op[1:]), why) for op, why in out]


def coverage(seed, seat, opponent_spec, arlene_mod, max_steps=None):
    """Every (day, tile, op) the intact route actually performs, from a real run."""
    A = arlene_mod
    opp, opp_id = load_agent(opponent_spec)
    env = cards_mod.make_env(seed)
    env.reset(2)
    mine, theirs = A.Agent(), A.Agent()
    daily, durable, n = set(), set(), 0
    final = None
    while not env.done and (max_steps is None or n < max_steps):
        acts = []
        for i in range(2):
            obs = env.state[i].observation
            if i == seat:
                a = mine.act(obs)
                farm = obs["farms"][seat]
                pos = [farm["farmer"]] + list(farm.get("hands", []))
                units = [list(a["farmer"])] + [list(h) for h in a["hands"]]
                day = int(obs["day"])
                # The seat-1 observation carries no `step` key at all, so
                # obs.get("step", 0) reads 0 on EVERY seat-1 turn and no durable op
                # ever looks covered. Derive the absolute clock the way the engine
                # does, from day and hour.
                step = constraints.absolute_step(obs, env.configuration)
                for j, op in enumerate(units):
                    if j < len(pos) and op and op[0] != "PASS":
                        at = (int(pos[j][0]), int(pos[j][1]))
                        daily.add((day, at, op[0]))
                        durable.add((step, at, op[0]))
                acts.append(a)
            else:
                acts.append(theirs.act(obs) if opponent_spec == "arlene"
                            else call(opp, obs, env.configuration))
        env.step(acts)
        n += 1
        final = env.state[0].observation.farms
    return {"daily": daily, "durable": durable}, {"cash": float(final[seat]["money"]),
                  "opponent_cash": float(final[1 - seat]["money"]),
                  "opponent": opp_id, "steps": n}


def harvest(seed, seat, opponent_spec, max_steps=None, limit=None):
    from kaggle_environments.envs.kaggriculture import kaggriculture as K
    A, arl_id = load_arlene()
    covered, base = coverage(seed, seat, opponent_spec, A, max_steps)
    opp, _ = load_agent(opponent_spec)
    env = cards_mod.make_env(seed)
    env.reset(2)
    mine, theirs = A.Agent(), A.Agent()
    out, n = [], 0
    while not env.done and (max_steps is None or n < max_steps):
        acts = []
        for i in range(2):
            obs = env.state[i].observation
            if i == seat:
                a = mine.act(obs)
                farm = obs["farms"][seat]
                priv = obs["private"]
                tiles = farm["tiles"]
                board = len(tiles)
                seeds = priv.get("seeds") or {}
                invs = priv.get("inventories") or []
                pos = [farm["farmer"]] + list(farm.get("hands", []))
                units = [list(a["farmer"])] + [list(h) for h in a["hands"]]
                day = int(obs["day"])
                step = constraints.absolute_step(obs, env.configuration)
                idle, opps = [], []
                for j, op in enumerate(units):
                    if j >= len(pos):
                        continue
                    x, y = int(pos[j][0]), int(pos[j][1])
                    inv = invs[j] if j < len(invs) else {}
                    if not (0 <= x < board and 0 <= y < board):
                        continue
                    tile = tiles[y][x]
                    if not A._noop(op, tile, inv, seeds, x, y, board):
                        continue          # the route is using this slot
                    idle.append(j)
                    for cand, why in live_ops(tile, inv, x, y, board, A, day, K):
                        op0 = cand[0]
                        if op0 in DAILY_OPS:
                            if (day, (x, y), op0) in covered["daily"]:
                                continue          # the route does it later today
                        elif any(st > step and t == (x, y) and o == op0
                                 for st, t, o in covered["durable"]):
                            continue              # the route does it later, ever
                        opps.append({"unit": j, "at": [x, y], "op": cand,
                                     "why": why, "tile": copy.deepcopy(tile),
                                     "window": ("day" if op0 in DAILY_OPS
                                                else "rest of episode")})
                if opps and (limit is None or len(out) < limit):
                    out.append({
                        "seed": seed, "seat": seat, "step": step,
                        "day": day, "hour": int(obs["hour"]),
                        "observation": copy.deepcopy(dict(obs)),
                        "configuration": dict(env.configuration),
                        "arlene_action": copy.deepcopy(a),
                        "idle_units": idle, "opportunities": opps,
                        "arlene": arl_id,
                    })
                acts.append(a)
            else:
                acts.append(theirs.act(obs) if opponent_spec == "arlene"
                            else call(opp, obs, env.configuration))
        env.step(acts)
        n += 1
    return out, base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--opponent", default="arlene")
    ap.add_argument("--max-steps", type=int, default=None)
    ap.add_argument("--limit-per-seed", type=int, default=None)
    ap.add_argument("--out", default="results/route-cards.json")
    a = ap.parse_args()
    allc, meta = [], {}
    for seed in a.seeds:
        got, base = harvest(seed, a.seat, a.opponent, a.max_steps, a.limit_per_seed)
        allc.extend(got)
        meta[str(seed)] = dict(base, cards=len(got))
        n_op = sum(len(c["opportunities"]) for c in got)
        print(f"seed {seed} seat {a.seat}: {len(got)} card(s), {n_op} live opportunit"
              f"{'y' if n_op == 1 else 'ies'}; intact Arlene cash {base['cash']:.0f} "
              f"vs {base['opponent_cash']:.0f}", flush=True)
    from collections import Counter
    c = Counter(o["op"][0] for card in allc for o in card["opportunities"])
    print("\nuncovered live ops by kind:", dict(c))
    hours = Counter(card["hour"] for card in allc)
    print("cards by hour:", dict(sorted(hours.items())))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"meta": meta, "cards": allc}, open(a.out, "w"), default=str)
    print(f"wrote {len(allc)} cards to {a.out}")


if __name__ == "__main__":
    main()

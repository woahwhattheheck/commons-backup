"""What is an empty structure actually worth to fill? Priced by realised continuation.

The worker lane over Arlene is exhausted and the reason is measured: its idle
workers are idle because the board holds nothing to collect. The largest
inefficiency still visible in the trace is on the other side of that -- seed
9600029 finishes with NINE structures the route built and never stocked, at 70,334
own cash against 132,726 on 9600011. Zero animals are ever stranded, so this is
not an install failure: the route simply never buys animals for them.

Whether that is a mistake or a correct capital judgement is answerable, not
arguable. At the first turn where a structure stands empty and the seat can afford
the animal, this buys ONE animal, has a worker collect and install it, and plays
the rest of the game out against the same opponent. The control is the same game
with the purchase declined. Everything else is intact Arlene.

This PRICES the decision; it does not implement an investment policy. The buy is a
single one-off injection at an observed state, the animal choice is whatever the
structure takes, and the result is own cash and own-minus-rival margin at the end.
"""

import argparse
import json
import os

import cards as cards_mod
import native_motifs as NM
import route_cards
import run_cards


class OneBuy:
    """Intact Arlene, plus a single animal purchase and install at `at_step`.

    The market order is appended to Arlene's own orders for that one turn, so its
    ten-slot budget and every other order are untouched. Installation uses the same
    position-safe rule as the worker lane: only a worker whose tape op is a literal
    PASS is moved, and it is returned to its starting tile.
    """

    def __init__(self, A, at_step=None, animal=None, enable=True):
        self.A = A
        self.agent = A.Agent()
        self.at_step = at_step
        self.animal = animal
        self.enable = enable
        self.K = NM.engine()
        self.log = []
        self.bought = None
        self.installed = False
        self.plan = None

    def _empty_structures(self, farm):
        out = []
        for y, row in enumerate(farm["tiles"]):
            for x, t in enumerate(row):
                if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE") \
                        and t.get("animal") is None:
                    out.append((x, y, t["kind"]))
        return out

    def act(self, obs):
        import arlene_plan
        base = self.agent.act(obs)
        if not self.enable:
            return base
        step = int(obs["day"]) * 24 + int(obs["hour"])
        seat = int(obs.get("player", 0))
        farm, priv = obs["farms"][seat], obs["private"]
        board = len(farm["tiles"])
        empties = self._empty_structures(farm)

        # one purchase, at the requested step, if a structure is standing empty
        if self.bought is None and empties and (self.at_step is None
                                                or step >= self.at_step):
            want = self.animal
            kinds = {k for _x, _y, k in empties}
            options = [a for a, d in self.K.ANIMALS.items() if d["structure"] in kinds]
            if want not in options:
                want = min(options, key=lambda a: self.K.ANIMALS[a]["cost"]) \
                    if options else None
            if want and float(farm["money"]) >= self.K.ANIMALS[want]["cost"] \
                    and len(base.get("market") or []) < 10:
                out = dict(base)
                out["market"] = list(base.get("market") or []) + \
                    [["BUY_ANIMAL", want, 1]]
                self.bought = {"step": step, "animal": want,
                               "cost": self.K.ANIMALS[want]["cost"],
                               "cash_before": float(farm["money"]),
                               "empty_structures": len(empties)}
                self.log.append(dict(self.bought, event="buy"))
                return out

        # then install it, moving only a worker the tape plays literal PASS for
        if self.bought and not self.installed:
            shed = priv.get("shed") or {}
            invs = priv.get("inventories") or []
            an = self.bought["animal"]
            struct = self.K.ANIMALS[an]["structure"]
            spots = [(x, y) for x, y, k in empties if k == struct]
            if not spots:
                return base
            units = [list(base["farmer"])] + [list(h) for h in base["hands"]]
            pos = [farm["farmer"]] + list(farm.get("hands", []))
            tail = units[len(pos):]
            units = units[:len(pos)]
            for i in range(len(units)):
                if arlene_plan.tape_op(self.agent, step, i) not in (None, ["PASS"]):
                    continue
                x, y = int(pos[i][0]), int(pos[i][1])
                inv = invs[i] if i < len(invs) else {}
                carrying = inv.get(an, 0) > 0
                if self.plan is None:
                    self.plan = {"unit": i, "home": (x, y), "phase":
                                 "carry" if carrying else "fetch"}
                if self.plan["unit"] != i:
                    continue
                if self.plan["phase"] == "fetch":
                    if shed.get(an, 0) <= 0:
                        return base                # not delivered to the shed yet
                    dep = min(run_cards.depot_tiles(board),
                              key=lambda p: run_cards._dist((x, y), p))
                    if (x, y) == dep:
                        op = ["PICKUP", an, 1]
                        self.plan["phase"] = "carry"
                    else:
                        op = [arlene_plan.step_toward((x, y), dep)]
                elif self.plan["phase"] == "carry":
                    tgt = min(spots, key=lambda p: run_cards._dist((x, y), p))
                    mv = arlene_plan.step_toward((x, y), tgt)
                    op = ["PLACE", an, 1] if mv is None else [mv]
                else:
                    op = [arlene_plan.step_toward((x, y), self.plan["home"])]
                    if op == [None]:
                        self.plan = None
                        return base
                trial = list(units)
                trial[i] = op
                cfg = {"boardSize": board, "turnsPerDay": 24,
                       "shedCapacity": self.A.SHED_CAP}
                sim = {"farms": obs["farms"], "private": priv, "day": int(obs["day"])}
                b = NM.simulate(self.K, sim, cfg, seat, units)
                a2 = NM.simulate(self.K, sim, cfg, seat, trial)
                if a2["slots"][i]["kind"] == "none":
                    return base
                if any((a2["slots"][j]["kind"], a2["slots"][j]["pos"],
                        a2["slots"][j]["carry"], a2["slots"][j]["tile"]) !=
                       (b["slots"][j]["kind"], b["slots"][j]["pos"],
                        b["slots"][j]["carry"], b["slots"][j]["tile"])
                       for j in range(len(units)) if j != i):
                    return base
                if a2["slots"][i]["kind"] == "installed_animal":
                    self.installed = True
                    self.log.append({"event": "installed", "step": step,
                                     "unit": i, "at": a2["slots"][i]["pos"]})
                    self.plan = {"unit": i, "home": self.plan["home"],
                                 "phase": "back"}
                units[i] = op
                out = dict(base)
                out["farmer"] = units[0]
                out["hands"] = units[1:] + tail
                return out
        return base

    def report(self):
        return {"bought": self.bought, "installed": self.installed,
                "events": self.log}


def game(seed, seat, opponent_spec, A, enable, at_step, animal):
    # Opponent resolution lives in arlene_arm (it knows the vendored parents), so
    # both scorers face exactly the same opponents.
    import arlene_arm
    opp, opp_id = arlene_arm.make_opponent(opponent_spec, A)
    env = cards_mod.make_env(seed)
    env.reset(2)
    me = OneBuy(A, at_step=at_step, animal=animal, enable=enable)
    while not env.done:
        acts = [None, None]
        for i in range(2):
            obs = env.state[i].observation
            acts[i] = me.act(obs) if i == seat else opp(obs, env.configuration)
        env.step(acts)
    farms = env.state[0].observation.farms
    own = float(farms[seat]["money"])
    rival = float(farms[1 - seat]["money"])
    return {"own_cash": own, "rival_cash": rival, "margin": own - rival,
            "arm": "one-buy" if enable else "control", "at_step": at_step,
            "animal": animal, "opponent": opp_id, **me.report()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--seats", type=int, nargs="+", default=[0])
    ap.add_argument("--opponents", nargs="+", default=["arlene"])
    ap.add_argument("--at-steps", type=int, nargs="+", default=[240, 360, 480])
    ap.add_argument("--animal", default=None)
    ap.add_argument("--out", default="results/structure-value.json")
    a = ap.parse_args()
    A, arl_id = route_cards.load_arlene()
    rows = []
    for seed in a.seeds:
        for seat in a.seats:
            for opp in a.opponents:
                c = game(seed, seat, opp, A, False, None, None)
                rows.append(dict(c, seed=seed, seat=seat))
                print(f"seed {seed} seat {seat} vs {opp:7s} control own "
                      f"{c['own_cash']:9.0f} margin {c['margin']:+9.0f}", flush=True)
                for st in a.at_steps:
                    r = game(seed, seat, opp, A, True, st, a.animal)
                    rows.append(dict(r, seed=seed, seat=seat))
                    b = r["bought"]
                    print(f"   buy@{st:4d}: "
                          + (f"{b['animal']} ${b['cost']} at step {b['step']} "
                             f"({b['empty_structures']} empty), installed="
                             f"{r['installed']}  " if b else "no purchase made  ")
                          + f"own {r['own_cash']:9.0f} "
                          f"({r['own_cash'] - c['own_cash']:+8.0f})  margin "
                          f"{r['margin']:+9.0f} "
                          f"({r['margin'] - c['margin']:+8.0f})", flush=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"arlene": arl_id, "rows": rows}, open(a.out, "w"), indent=1,
              default=str)


if __name__ == "__main__":
    main()

"""Paired panel over whole callables, with frozen SELL as the control.

`arlene_arm.py` compares a cap overlay against intact Arlene. This compares whole
agents against the SELECTED DEFAULT -- T08's frozen SELL -- which is the only
control that answers "should this replace what is shipping".

Arms are imported unmodified from their owners' paths. Nothing here edits another
lane's file; the committed-envelope arm is this lab's own subclass over T08's
unmodified dated adapter.
"""

import argparse
import importlib.util
import json
import os
import sys
import time

import cards as cards_mod

T08 = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "cloud-titan-composition"))


def load_arm(name):
    """`sell` and `carrot_cap_sell_conserved` come from T08's arms; `committed`
    is this lab's additive subclass."""
    if name == "committed":
        import committed_envelope
        return lambda: committed_envelope.CommittedCapSell().act
    path = os.path.join(T08, "arms", f"{name}.py")
    def factory():
        for p in (os.path.join(T08, "vendor", "sell"), T08):
            if p not in sys.path:
                sys.path.insert(0, p)
        spec = importlib.util.spec_from_file_location(
            f"t08_{name}_{time.time_ns()}", os.path.realpath(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod.agent
    return factory


def normalise(obs, seat):
    """Supply the absolute clock and seat the engine leaves off seat 1."""
    o = dict(obs)
    if o.get("step") is None:
        o["step"] = int(o["day"]) * 24 + int(o["hour"])
    o.setdefault("player", seat)
    return o


def game(seed, seat, opponent, arm_factory):
    import arlene_arm
    import route_cards
    A, _ = route_cards.load_arlene()
    opp, opp_id = arlene_arm.make_opponent(opponent, A)
    me = arm_factory()
    env = cards_mod.make_env(seed)
    env.reset(2)
    worst, n = 0.0, 0
    while not env.done:
        acts = [None, None]
        for i in range(2):
            obs = env.state[i].observation
            if i == seat:
                # The engine omits `step` from a seat-1 observation; the frozen
                # scheduler and T08's arrival contract both index it directly, so
                # a seat-1 game raises KeyError before any policy runs. Normalised
                # here in the HARNESS, exactly as Arlene does internally, so no
                # policy under test is modified.
                o = normalise(obs, i)
                t = time.perf_counter()
                acts[i] = me(o, env.configuration)
                worst = max(worst, time.perf_counter() - t)
            else:
                acts[i] = opp(obs, env.configuration)
        env.step(acts)
        n += 1
    farms = env.state[0].observation.farms
    own = float(farms[seat]["money"])
    rival = float(farms[1 - seat]["money"])
    return {"seed": seed, "seat": seat, "opponent": opponent,
            "own_cash": own, "rival_cash": rival, "margin": own - rival,
            "turns": n, "worst_action_s": round(worst, 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--seats", type=int, nargs="+", default=[0, 1])
    ap.add_argument("--opponents", nargs="+", default=["arlene", "apex"])
    ap.add_argument("--arms", nargs="+",
                    default=["sell", "carrot_cap_sell_conserved", "committed"])
    ap.add_argument("--control", default="sell")
    ap.add_argument("--out", default="results/sell-arm.json")
    a = ap.parse_args()
    fac = {n: load_arm(n) for n in set(a.arms) | {a.control}}
    rows = []
    for seed in a.seeds:
        for seat in a.seats:
            for opp in a.opponents:
                base = game(seed, seat, opp, fac[a.control])
                rows.append(dict(base, arm=a.control))
                line = (f"seed {seed} seat {seat} vs {opp:7s}  "
                        f"{a.control} own {base['own_cash']:9.0f} "
                        f"margin {base['margin']:+9.0f}")
                for arm in a.arms:
                    if arm == a.control:
                        continue
                    r = game(seed, seat, opp, fac[arm])
                    rows.append(dict(r, arm=arm))
                    line += (f" | {arm} own {r['own_cash']:9.0f} "
                             f"margin {r['margin']:+9.0f} "
                             f"(d_own {r['own_cash'] - base['own_cash']:+7.0f} "
                             f"d_margin {r['margin'] - base['margin']:+7.0f})")
                print(line, flush=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"control": a.control, "arms": a.arms, "rows": rows},
              open(a.out, "w"), indent=1, default=str)

    def wtl(m):
        return "W" if m > 0 else ("L" if m < 0 else "T")
    print("\n=== W/T/L against the selected default ===")
    ctrl = {(r["seed"], r["seat"], r["opponent"]): r
            for r in rows if r["arm"] == a.control}
    for arm in [a.control] + [x for x in a.arms if x != a.control]:
        rs = [r for r in rows if r["arm"] == arm]
        v = [wtl(r["margin"]) for r in rs]
        flips = sum(1 for r in rs
                    if wtl(r["margin"]) != wtl(ctrl[(r["seed"], r["seat"],
                                                     r["opponent"])]["margin"]))
        d = [r["own_cash"] - ctrl[(r["seed"], r["seat"], r["opponent"])]["own_cash"]
             for r in rs]
        print(f"  {arm:28s} {v.count('W')}/{v.count('T')}/{v.count('L')}  "
              f"flips vs control {flips:2d}  mean d_own "
              f"{sum(d) / len(d):+8.1f}  worst action "
              f"{max(r['worst_action_s'] for r in rs) * 1000:6.1f}ms")


if __name__ == "__main__":
    main()

"""Realised continuation value of Arlene's own route-tail choices.

Arlene switches route tails at three checkpoints, each a hand-set threshold on one
observable feature (arlene.py DECISIONS):

    turn 226   shop_YARN_STORE >= 1     -> YARN
    turn 360   px_CARROT       >= 42    -> YARN_CARROT
    turn 433   inv_MILK        >= 10067 -> MILK_GLUT

A switch is only ever onto a tail identical to the current one so far
(`_switch_ok`), so prefix compatibility is the baseline's own invariant and this
changes nothing else about the agent: same tapes, same repairs, same market logic.

The idle-slot lane measured out at zero -- Arlene leaves a slot free because
nothing on that tile is worth doing, and any fill either spends a resource or
reorders the shared price curve. A tail choice is the opposite kind of lever: one
decision that swaps a whole route suffix.

This measures what each choice is actually WORTH by playing the rest of the game
out both ways, in the official interpreter, against a real opponent -- realised
continuation value, not a proxy. It reports own cash and own-minus-rival margin
separately and records the feature value the threshold reads, so a wrong threshold
shows up as a decision whose realised value has the opposite sign.
"""

import argparse
import json
import os

import cards as cards_mod
import route_cards


def play(seed, seat, opponent_spec, A, force=None):
    """One full game. `force` = (turn, tail_hash) applies that switch at that turn,
    through the baseline's own `_switch_ok`; (turn, "STAY") suppresses whatever
    switch that one checkpoint would take; None plays Arlene exactly."""
    import arlene_arm
    opp, opp_id = arlene_arm.make_opponent(opponent_spec, A)
    env = cards_mod.make_env(seed)
    env.reset(2)
    mine = A.Agent()
    applied, feature = None, None
    while not env.done:
        acts = [None, None]
        for i in range(2):
            obs = env.state[i].observation
            if i == seat:
                if force is not None:
                    turn, target = force
                    step = int(obs["day"]) * 24 + int(obs["hour"])
                    if step == turn:
                        feat = next((f for (t, f, _thr, _tg) in A.DECISIONS
                                     if t == turn), None)
                        feature = A._feature(obs, feat) if feat else None
                        if target == "STAY":
                            # Suppress ONLY this checkpoint, for ONE action
                            # evaluation. Calling act twice let the agent reapply
                            # the switch on the second call, which is the opposite
                            # of what this arm is measuring; removing the single
                            # DECISIONS entry for the duration of one call leaves
                            # every other checkpoint and the opponent untouched.
                            kept = A.DECISIONS
                            A.DECISIONS = tuple(d for d in kept if d[0] != turn)
                            try:
                                before_cur = mine.cur
                                acts[i] = mine.act(obs)
                            finally:
                                A.DECISIONS = kept
                            applied = ("switch suppressed"
                                       if mine.cur == before_cur else "reapplied")
                        elif target != mine.cur and mine._switch_ok(target, turn):
                            mine.cur = target
                            applied = True
                        elif target == mine.cur:
                            applied = "already on it"
                        else:
                            applied = "prefix-incompatible"
                if acts[i] is None:
                    acts[i] = mine.act(obs)
            else:
                acts[i] = opp(obs, env.configuration)
        env.step(acts)
    farms = env.state[0].observation.farms
    own = float(farms[seat]["money"])
    rival = float(farms[1 - seat]["money"])
    return {"own_cash": own, "rival_cash": rival, "margin": own - rival,
            "forced": force, "applied": applied, "feature_value": feature,
            "final_tail": mine.cur, "opponent": opp_id}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--seats", type=int, nargs="+", default=[0, 1])
    ap.add_argument("--opponents", nargs="+", default=["arlene", "apex"])
    ap.add_argument("--out", default="results/tail-choice.json")
    a = ap.parse_args()
    A, arl_id = route_cards.load_arlene()
    names = {A.MAIN: "MAIN", A.YARN: "YARN", A.YARN_CARROT: "YARN_CARROT",
             A.MILK_GLUT: "MILK_GLUT"}
    rows = []
    for seed in a.seeds:
        for seat in a.seats:
            for opp in a.opponents:
                base = play(seed, seat, opp, A)
                rows.append(dict(base, seed=seed, seat=seat, arm="arlene as shipped",
                                 checkpoint=None, tail=names.get(base["final_tail"])))
                print(f"seed {seed} seat {seat} vs {opp:7s}  as-shipped own "
                      f"{base['own_cash']:9.0f} margin {base['margin']:+9.0f} "
                      f"tail {names.get(base['final_tail'])}", flush=True)
                trials = [(turn, target) for (turn, _f, _t, target) in A.DECISIONS]
                trials += [(turn, "STAY") for (turn, _f, _t, _g) in A.DECISIONS]
                for (turn, target) in trials:
                    feat, thr = next(((f, t) for (tn, f, t, _g) in A.DECISIONS
                                      if tn == turn), (None, None))
                    r = play(seed, seat, opp, A, force=(turn, target))
                    rows.append(dict(r, seed=seed, seat=seat,
                                     arm=f"force {names.get(target, target)} @{turn}",
                                     checkpoint=turn, feature=feat,
                                     threshold=thr,
                                     tail=names.get(r["final_tail"])))
                    print(f"      force {names.get(target, target):11s} @{turn:4d} "
                          f"({feat}={r['feature_value']} thr {thr}, "
                          f"{r['applied']}): own {r['own_cash']:9.0f} "
                          f"({r['own_cash'] - base['own_cash']:+8.0f})  margin "
                          f"{r['margin']:+9.0f} "
                          f"({r['margin'] - base['margin']:+8.0f})", flush=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump({"arlene": arl_id, "rows": rows}, open(a.out, "w"), indent=1,
              default=str)


if __name__ == "__main__":
    main()

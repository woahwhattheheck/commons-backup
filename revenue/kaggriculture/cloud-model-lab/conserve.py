"""Compatibility and conservation, measured on real games before any panel.

T13's `SeedBudget` documents its own precondition: the bound is derived from the
INTACT Arlene/SELL route tape, and it must not be stacked with an overlay that
adds PLANT requests or rewrites routes. This checks that precondition on the
actual composition rather than asserting it, and checks that the two switches
write to disjoint parts of the emitted action.

Checks, per turn of a full game:

  1  exactly one parent decision
  2  the cap overlay changes no PLANT request (multiset over all units, against
     the parent's OWN returned action, not the tape -- Arlene substitutes DIG on
     a weed tile itself and that substitution must stay attributed to Arlene)
  3  the parent's route table `R` is never mutated, so the budget's suffix bound
     and Arlene's own `_switch_ok` prefix comparisons still read the frozen tape
  4  the seed budget only ever touches BUY_SEED slots, never increases one, and
     preserves market slot count and index order
  5  the SELL execution and the seed budget never write the SAME market slot on
     the SAME turn (an aggregate index overlap across a whole game is not a
     conflict -- slot 1 can be a SELL on one turn and a BUY_SEED on another)

Run: python -B conserve.py --seeds 9890001 --seats 0 1 --opponents arlene apex
"""

import argparse
import copy
import json
import os

import cards as cards_mod
import seed_committed_2x2 as X


def plants(action):
    out = {}
    for a in [action.get("farmer") or ["PASS"], *(action.get("hands") or [])]:
        if a and a[0] == "PLANT" and len(a) > 1:
            out[a[1]] = out.get(a[1], 0) + 1
    return out


def units(action):
    return [list(action.get("farmer") or ["PASS"])] + [list(a) for a in
                                                       (action.get("hands") or [])]


def route_fingerprint(agent):
    return {name: hash(json.dumps(route, sort_keys=True, default=str))
            for name, route in agent.R.items()}


class Trace:
    def __init__(self):
        self.turns = 0
        self.fail = []
        self.parent_call_hist = {}
        self.overlay_unit_edits = 0
        self.sell_slots = set()
        self.budget_slots = set()
        self.budget_edits = 0
        self.budget_reductions = []
        self.same_turn_overlap = []
        self.route0 = None

    def note(self, name, ok, detail):
        if not ok:
            self.fail.append((name, detail))

    def record(self, obs, base, selected, pre_budget, final, calls, parent):
        if base is None:          # bare arm: the parent IS the selected action
            base = selected
        self.turns += 1
        step = int(obs["step"])
        self.parent_call_hist[calls] = self.parent_call_hist.get(calls, 0) + 1
        self.note("one parent decision per turn", calls == 1, f"step {step}: {calls}")

        # 2. PLANT demand conservation across the production overlay.
        pb, ps = plants(base), plants(selected)
        self.note("cap overlay conserves PLANT demand", pb == ps,
                  f"step {step}: parent {pb} -> selected {ps}")
        ub, us = units(base), units(selected)
        self.overlay_unit_edits += sum(1 for i in range(min(len(ub), len(us)))
                                       if ub[i] != us[i])

        # 3. the tape is read-only.
        fp = route_fingerprint(parent)
        if self.route0 is None:
            self.route0 = fp
        else:
            self.note("parent route table R is not mutated", fp == self.route0,
                      f"step {step}")

        # 4/5. market write sets.
        sel_m = list(selected.get("market") or [])
        pre_m = list(pre_budget.get("market") or [])
        fin_m = list(final.get("market") or [])
        turn_sell, turn_budget = set(), set()
        for i in range(max(len(sel_m), len(pre_m))):
            a = sel_m[i] if i < len(sel_m) else None
            b = pre_m[i] if i < len(pre_m) else None
            if a != b:
                self.sell_slots.add(i)
                turn_sell.add(i)
        self.note("seed budget preserves market slot count",
                  len(fin_m) == len(pre_m), f"step {step}: {len(pre_m)}->{len(fin_m)}")
        for i in range(min(len(pre_m), len(fin_m))):
            a, b = pre_m[i], fin_m[i]
            if a == b:
                continue
            self.budget_slots.add(i)
            turn_budget.add(i)
            self.budget_edits += 1
            ok = bool(a) and a[0] == "BUY_SEED" and (
                not b or (b[0] == "BUY_SEED" and b[1] == a[1]
                          and 0 <= int(b[2]) < int(a[2])))
            self.note("seed budget only reduces a BUY_SEED in place", ok,
                      f"step {step} slot {i}: {a} -> {b}")
            if ok:
                self.budget_reductions.append(
                    dict(step=step, slot=i, crop=a[1], requested=int(a[2]),
                         retained=int(b[2]) if b else 0,
                         sell_touched_this_slot_this_turn=i in turn_sell))
        both = sorted(turn_sell & turn_budget)
        if both:
            self.same_turn_overlap.append(dict(step=step, slots=both))
        self.note("SELL and seed budget never write the same slot on the same turn",
                  not both, f"step {step}: slots {both}")

    def report(self):
        return dict(turns=self.turns,
                    aggregate_index_overlap=sorted(self.sell_slots & self.budget_slots),
                    same_turn_overlap=self.same_turn_overlap,
                    parent_calls_per_turn=self.parent_call_hist,
                    overlay_unit_edits=self.overlay_unit_edits,
                    sell_written_slots=sorted(self.sell_slots),
                    budget_written_slots=sorted(self.budget_slots),
                    budget_edits=self.budget_edits,
                    budget_reductions=self.budget_reductions,
                    failures=self.fail[:20], failure_count=len(self.fail))


def game(seed, seat, opponent, arm_name):
    import arlene_arm
    import route_cards
    A, _ = route_cards.load_arlene()
    opp, _ = arlene_arm.make_opponent(opponent, A)
    tr = Trace()
    me = X.make(arm_name, trace=tr)
    env = cards_mod.make_env(seed)
    env.reset(2)
    while not env.done:
        acts = [None, None]
        for i in range(2):
            obs = env.state[i].observation
            acts[i] = (me.act(X.normalise(obs, i), env.configuration)
                       if i == seat else opp(obs, env.configuration))
        env.step(acts)
    farms = env.state[0].observation.farms
    rep = tr.report()
    rep.update(seed=seed, seat=seat, opponent=opponent, arm=arm_name,
               own_cash=float(farms[seat]["money"]),
               rival_cash=float(farms[1 - seat]["money"]))
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[9890001])
    ap.add_argument("--seats", type=int, nargs="+", default=[0, 1])
    ap.add_argument("--opponents", nargs="+", default=["arlene", "apex"])
    ap.add_argument("--arm", default="combined")
    ap.add_argument("--out", default="results/conserve-2x2.json")
    a = ap.parse_args()
    rows, bad = [], 0
    for seed in a.seeds:
        for seat in a.seats:
            for opp in a.opponents:
                r = game(seed, seat, opp, a.arm)
                rows.append(r)
                bad += r["failure_count"]
                print(f"seed {seed} seat {seat} vs {opp:7s} turns {r['turns']:3d} "
                      f"parent/turn {r['parent_calls_per_turn']} "
                      f"overlay unit edits {r['overlay_unit_edits']:4d} "
                      f"SELL slots {r['sell_written_slots']} "
                      f"budget slots {r['budget_written_slots']} "
                      f"budget edits {r['budget_edits']:3d} "
                      f"same-turn overlap {len(r['same_turn_overlap']):2d} "
                      f"FAIL {r['failure_count']}", flush=True)
                for name, detail in r["failures"][:5]:
                    print(f"    ! {name}: {detail}")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(rows, open(a.out, "w"), indent=1, default=str)
    print(f"\n{'ALL CHECKS PASS' if not bad else str(bad) + ' CHECK FAILURES'} "
          f"over {len(rows)} game(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

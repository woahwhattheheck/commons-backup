"""How much production does the MEASURED SEAT lose to the animal output cap?

Attribution is explicit. `_end_of_day` runs the animal refresh once per farm, so a
wrapper on the refresh alone sees both players and can report only a board total,
which is a figure about neither of them. The owner map is built from the state the
interpreter holds, and every event carries the seat it belongs to.

`_daily_refresh_animals` writes `yield_units = min(max_held, yield + base + bonus)`
(kaggriculture.py 827), so a unit produced on a day the animal is already at its
cap is silently discarded. That is a recurring loss no "the route harvests it
eventually" test can see: the units are gone before any later harvest reaches
them.

This measures it directly by wrapping the engine's own refresh and comparing what
each animal would have accrued against what the cap let it keep. It also records
which tiles lose, and when, so a card set can be aimed at the animals that
actually overflow instead of at whatever happens to be unharvested.
"""

import argparse
import json
import os
from collections import Counter

import cards as cards_mod
import route_cards


def measure(seed, seat, opponent_spec):
    from kaggle_environments.envs.kaggriculture import kaggriculture as K
    A, arl_id = route_cards.load_arlene()
    import arlene_arm
    opp, opp_id = arlene_arm.make_opponent(opponent_spec, A)
    env = cards_mod.make_env(seed)
    env.reset(2)
    me = A.Agent()
    losses = []
    owners = {}
    orig = K._daily_refresh_animals
    orig_eod = K._end_of_day

    # `_end_of_day` calls the refresh once per farm, so the wrapper below sees both
    # players' animals and cannot tell them apart on its own. The owner map is
    # built here, from the state the interpreter is actually holding, exactly as
    # the market ledger does it.
    def end_of_day(state, env_, day):
        owners.clear()
        for s_i, f in enumerate(state[0].observation.farms):
            owners[id(f)] = s_i
        return orig_eod(state, env_, day)

    def refresh(farm, day):
        seat_of = owners.get(id(farm))
        board = len(farm["tiles"])
        before = {}
        for y in range(board):
            for x in range(board):
                t = farm["tiles"][y][x]
                if isinstance(t, dict) and "animal" in t:
                    before[(x, y)] = (t["animal"], int(t.get("yield_units", 0)),
                                      bool(t.get("fed_today")),
                                      int(t.get("pending_care_bonus", 0) or 0),
                                      int(t.get("placed_day", day)))
        orig(farm, day)
        for (x, y), (an, y0, fed, bonus, placed) in before.items():
            a = K.ANIMALS[an]
            since = (day + 1) - placed - a["first_yield_day"]
            if since < 0 or since % a["interval"] != 0:
                continue                       # not a production day
            base = 1 + (bonus if fed else 0)
            kept = min(a["max_held"], y0 + base)
            lost = (y0 + base) - kept
            if lost > 0:
                losses.append({"day": day, "seat": seat_of, "at": [x, y],
                               "animal": an,
                               "product": a["product"], "yield_before": y0,
                               "max_held": a["max_held"], "would_add": base,
                               "lost": lost})
    K._daily_refresh_animals = refresh
    K._end_of_day = end_of_day
    try:
        while not env.done:
            acts = [None, None]
            for i in range(2):
                obs = env.state[i].observation
                acts[i] = me.act(obs) if i == seat else opp(obs, env.configuration)
            env.step(acts)
    finally:
        K._daily_refresh_animals = orig
        K._end_of_day = orig_eod
    farms = env.state[0].observation.farms
    prices = env.state[0].observation.market["prices"]
    own = float(farms[seat]["money"])
    # Split by seat. A total over both farms is not a figure about either player,
    # and the measured seat's own recoverable loss is smaller still: an event whose
    # `yield_before` is below `max_held` overflows on an accumulated care bonus, and
    # no earlier harvest can recover that.
    def summarise(rows):
        bp = Counter()
        for r in rows:
            bp[r["product"]] += r["lost"]
        return {"units": sum(r["lost"] for r in rows), "events": len(rows),
                "by_product": dict(bp),
                "value_at_final_prices": round(
                    sum(n * float(prices.get(p, 0)) for p, n in bp.items()), 1),
                "tiles": Counter(tuple(r["at"]) for r in rows).most_common(6)}
    mine = [r for r in losses if r["seat"] == seat]
    theirs_rows = [r for r in losses if r["seat"] == (1 - seat)]
    unattributed = [r for r in losses if r["seat"] is None]
    recoverable = [r for r in mine
                   if r["yield_before"] >= r["max_held"]]
    return {"seed": seed, "seat": seat, "opponent": opp_id, "arlene": arl_id,
            "own_cash": own, "rival_cash": float(farms[1 - seat]["money"]),
            "measured_seat": summarise(mine),
            "opponent_seat": summarise(theirs_rows),
            "unattributed_events": len(unattributed),
            # the subset an earlier harvest could actually have taken
            "measured_seat_recoverable": summarise(recoverable),
            "both_farms_total_units": sum(r["lost"] for r in losses),
            "losses": losses}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--seats", type=int, nargs="+", default=[0])
    ap.add_argument("--opponents", nargs="+", default=["arlene"])
    ap.add_argument("--out", default="results/cap-loss.json")
    a = ap.parse_args()
    rows = []
    for seed in a.seeds:
        for seat in a.seats:
            for opp in a.opponents:
                r = measure(seed, seat, opp)
                rows.append(r)
                m, o, rec = (r["measured_seat"], r["opponent_seat"],
                             r["measured_seat_recoverable"])
                print(f"seed {seed} seat {seat} vs {opp:7s}: own {r['own_cash']:9.0f}",
                      flush=True)
                print(f"    measured seat {m['units']:3d} unit(s) over "
                      f"{m['events']} refreshes {m['by_product']}, "
                      f"~{m['value_at_final_prices']:.0f} at final prices", flush=True)
                print(f"    of which an earlier HARVEST could have taken: "
                      f"{rec['units']:3d} unit(s) over {rec['events']} refreshes "
                      f"{rec['by_product']}, ~{rec['value_at_final_prices']:.0f}",
                      flush=True)
                print(f"    opponent seat {o['units']:3d} unit(s) "
                      f"(recorded, not this seat's opportunity); unattributed "
                      f"{r['unattributed_events']}", flush=True)
                if m["tiles"]:
                    print(f"    measured-seat worst tiles: {m['tiles']}", flush=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(rows, open(a.out, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()

"""Record the engine's end-of-day RNG path, per arm.

`_end_of_day` (kaggriculture.py 860-891) builds one `random.Random((seed*1_000_003)
^ day)` per day and then, BEFORE the shop draw, calls `rng.random()` once for every
EMPTY tile of farm 0 and then every empty tile of farm 1 (`_spawn_weeds`, 836-840).
The shop unlock is the next draw off that same stream.

So the number of empty tiles is a policy variable that moves the stream position:
two arms on the SAME seed that build, plant or dig differently get different weed
layouts and a different shop-unlock sequence from that day on. Any cash difference
between such arms is therefore not attributable to one cause on its own -- and in
particular a shared-market price effect cannot be asserted without showing the two
arms shared a market path.

This records the path instead of assuming it: per day, per farm, the empty-tile
count that was drawn against, the weeds that spawned, the running draw offset, and
the shop the town unlocked. Two recordings diff directly.
"""

import argparse
import json
import os

import cards as cards_mod
import continuation as CONT


class PathRecorder:
    """Wraps the engine's own end-of-day; records, never substitutes."""

    def __init__(self):
        self.rows = []
        self._day = None
        self._K = None
        self._spawn = None
        self._eod = None

    def __enter__(self):
        from kaggle_environments.envs.kaggriculture import kaggriculture as K
        self._K = K
        self._spawn, self._eod = K._spawn_weeds, K._end_of_day
        rec = self

        def spawn_weeds(farm, board_size, weed_chance, rng):
            empty = sum(1 for row in farm["tiles"] for t in row if t is None)
            before = sum(1 for row in farm["tiles"] for t in row
                         if isinstance(t, dict) and t.get("kind") == "WEED")
            rec._spawn(farm, board_size, weed_chance, rng)
            after = sum(1 for row in farm["tiles"] for t in row
                        if isinstance(t, dict) and t.get("kind") == "WEED")
            rec.rows.append({"day": rec._day, "farm": len(
                [r for r in rec.rows if r["day"] == rec._day]),
                "empty_tiles_drawn": empty, "weeds_spawned": after - before})

        def end_of_day(state, env, day):
            rec._day = int(day)
            town = state[0].observation.town
            before = list(town.get("unlocked_shops") or [])
            rec._eod(state, env, day)
            after = list(town.get("unlocked_shops") or [])
            new = after[len(before):]
            for r in rec.rows:
                if r["day"] == rec._day and "shop_unlocked" not in r:
                    r["shop_unlocked"] = new[0] if new else None
        K._spawn_weeds = spawn_weeds
        K._end_of_day = end_of_day
        return self

    def __exit__(self, *exc):
        self._K._spawn_weeds = self._spawn
        self._K._end_of_day = self._eod
        return False

    def path(self):
        """Per day: the draw offset each farm was measured at, and the shop drawn."""
        by_day = {}
        for r in self.rows:
            d = by_day.setdefault(r["day"], {"day": r["day"], "farms": [],
                                             "shop_unlocked": r.get("shop_unlocked")})
            d["farms"].append({"empty_tiles_drawn": r["empty_tiles_drawn"],
                               "weeds_spawned": r["weeds_spawned"]})
        out = []
        for d in sorted(by_day.values(), key=lambda x: x["day"]):
            d["draws_before_shop"] = sum(f["empty_tiles_drawn"] for f in d["farms"])
            out.append(d)
        return out


def from_trace(trace_path, cont_spec, control=False, warmup=None, opponent=None):
    d = json.load(open(trace_path))
    prefix = [{"farmer": t["action"]["farmer"], "hands": t["action"]["hands"],
               "market": t["action"]["market"]} for t in d.get("turns", [])]
    warm = warmup or d.get("warmup_spec") or d["warmup"]
    opp = opponent or d.get("opponent_spec") or d["opponent"]
    with PathRecorder() as rec:
        m = CONT.play_out(d["seed"], d["seat"], prefix, warm, opp, cont_spec,
                          d["from_step"], control=control)
    return {"label": ("control" if control else os.path.basename(trace_path)),
            "seed": d["seed"], "final_cash": m["final_cash"],
            "opponent_cash": m.get("opponent_cash"), "margin": m["margin"],
            "path": rec.path()}


def diff(a, b):
    """Where the two arms' market paths part company, and on which day."""
    out = []
    for x, y in zip(a["path"], b["path"]):
        same_draws = x["draws_before_shop"] == y["draws_before_shop"]
        same_shop = x["shop_unlocked"] == y["shop_unlocked"]
        if not (same_draws and same_shop):
            out.append({"day": x["day"],
                        "draws": [x["draws_before_shop"], y["draws_before_shop"]],
                        "shop": [x["shop_unlocked"], y["shop_unlocked"]]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", default=[])
    ap.add_argument("--continuation", default="../cloud-market/main.py::agent")
    ap.add_argument("--control-from", default=None,
                    help="also record the matched control using this run's boundary")
    ap.add_argument("--out", default="results/market-path.json")
    a = ap.parse_args()
    rows = [from_trace(p, a.continuation) for p in a.run]
    if a.control_from:
        rows.append(from_trace(a.control_from, a.continuation, control=True))
    for r in rows:
        shops = [d["shop_unlocked"] for d in r["path"] if d["shop_unlocked"]]
        print(f"{r['label'][:42]:42s} cash={r['final_cash']:9.0f} "
              f"margin={r['margin']:+9.0f} shops={shops}")
    print()
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            d = diff(rows[i], rows[j])
            first = d[0]["day"] if d else None
            print(f"{rows[i]['label'][:30]:30s} vs {rows[j]['label'][:30]:30s}  "
                  f"paths diverge on {len(d)} day(s)"
                  + (f", first day {first}: draws {d[0]['draws']} shop {d[0]['shop']}"
                     if d else " -- identical market path"))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(rows, open(a.out, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()

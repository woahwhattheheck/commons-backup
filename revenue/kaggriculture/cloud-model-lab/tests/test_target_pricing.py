"""Regression for the target-pricing lookup.

Two things are asserted here, and the second is the one that matters:

  1. On a REAL observed yield-bearing state, candidate targets come back
     non-empty and priced through the exact interface
     `market_price(item, inventory, params)`.
  2. When the pricing API is absent, that surfaces as a DIAGNOSTIC. Silence is
     the failure mode: an absent price must never be indistinguishable from
     "there is no opportunity here".

Run: python -B tests/test_target_pricing.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cards
import native_motifs as NM
import route_cards
import run_cards

FAIL = []


def check(name, cond, detail=""):
    ok = bool(cond)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAIL.append(name)


def observed_yield_state():
    """A real turn from a real Arlene game in which an animal is holding yield.

    Not a constructed tile: the point of the regression is that the instrument
    works on the states it is actually asked about.
    """
    A, _ = route_cards.load_arlene()
    env = cards.make_env(9600011)
    env.reset(2)
    mine, theirs = A.Agent(), A.Agent()
    while not env.done:
        obs = env.state[0].observation
        held = sum(int(t.get("yield_units", 0))
                   for row in obs["farms"][0]["tiles"] for t in row
                   if isinstance(t, dict) and t.get("animal") is not None)
        if held > 0:
            return {k: v for k, v in obs.items()}, dict(env.configuration), held
        env.step([mine.act(obs), theirs.act(env.state[1].observation)])
    return None, None, 0


def main():
    obs, cfg, held = observed_yield_state()
    check("found a real observed state with animal yield on the board",
          obs is not None and held > 0, f"{held} unit(s) held")
    if obs is None:
        return 1
    K = NM.engine()
    board = len(obs["farms"][0]["tiles"])

    from kaggle_environments.envs.kaggriculture import kaggriculture as R
    check("the bundle provides the pricing API, so a hosted archive needs no "
          "evaluator package at runtime", hasattr(K, "market_price"),
          f"{K.__name__}.market_price")
    quotes = [(item, inv) for item in R.PRODUCTS
              for inv in (0, 1, 7, 50, 133, 400, 1000, 5000)]
    off = [(i, n) for i, n in quotes
           if abs(K.market_price(i, n, None) - R.market_price(i, n, None)) > 1e-9]
    check(f"bundled market_price matches the engine over {len(quotes)} quotes",
          not off, str(off[:3]))

    tg = run_cards.reachable_targets(obs, 0, (0, 0), K, board,
                                     obs["market"]["prices"])
    check("candidate targets are NON-EMPTY on that state", len(tg) > 0,
          f"{len(tg)} target(s)")
    priced = [t for t in tg if t.get("value_now") is not None]
    check("every returned target carries a price", len(priced) == len(tg),
          f"{len(priced)}/{len(tg)}")
    check("prices are positive", all(t["value_now"] > 0 for t in tg),
          str(sorted({round(t["value_now"], 1) for t in tg})[:4]))

    # the exact interface, against the engine's own quote for the same inputs
    market = obs["market"]
    a = next(t for t in tg if t["op"][0] == "HARVEST")
    inv0 = int(dict(market.get("inventory") or {}).get(a["product"], 0))
    expect = round(sum(float(R.market_price(a["product"], inv0 + k,
                                            market.get("params")))
                       for k in range(int(a["units"]))), 1)
    check("the price equals market_price(item, inventory, params) summed per unit",
          abs(a["value_now"] - expect) < 1e-6, f"{a['value_now']} vs {expect}")

    # a missing API must be LOUD. Every provider is removed, since the resolver
    # now falls back from the caller's module to the bundle to the engine; leaving
    # any one in place would not exercise the path at all.
    import engine_pin
    saved = (R.market_price, engine_pin.market_price)
    try:
        del R.market_price
        del engine_pin.market_price
        raised = None
        try:
            run_cards.reachable_targets(obs, 0, (0, 0), engine_pin, board,
                                        obs["market"]["prices"])
        except Exception as exc:
            raised = f"{type(exc).__name__}: {exc}"
        check("with NO provider offering the API the call raises a diagnostic "
              "instead of returning an empty target list",
              raised is not None, raised or "returned quietly")
    finally:
        R.market_price, engine_pin.market_price = saved

    tg2 = run_cards.reachable_targets(obs, 0, (0, 0), K, board,
                                      obs["market"]["prices"])
    check("pricing is restored afterwards", len(tg2) == len(tg))
    print(f"\n{'ALL PASS' if not FAIL else str(len(FAIL)) + ' FAILED: ' + ', '.join(FAIL)}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())

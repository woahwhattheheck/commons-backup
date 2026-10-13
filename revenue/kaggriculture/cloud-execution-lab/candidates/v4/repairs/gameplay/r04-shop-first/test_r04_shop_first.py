# SPDX-License-Identifier: Apache-2.0
"""Unit tests for r04_shop_first.  No engine, no network, no I/O."""
import copy
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from r04_shop_first import (
    CONFIG_KEY,
    SHOP_PRIORITY,
    SHOP_RESERVE,
    SHOP_LIVENESS_STEPS,
    ShopLedger,
    filter_market_orders,
)

ON = {CONFIG_KEY: True}
OFF = {CONFIG_KEY: False}


def obs(step, shed):
    return {"step": step, "private": {"shed": dict(shed)}}


def live_ledger(step=500):
    lg = ShopLedger()
    lg.note_step(step, {"WOOL": 30}, {"WOOL": 6}, {}, 2952.0)
    return lg


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print("ok -", name)


# --- config gating -------------------------------------------------------
a = {"market": [["SELL", "WOOL", 100]]}
o = obs(500, {"WOOL": 100})
check("off-missing-key-passthrough", filter_market_orders(a, o, {}, live_ledger()) is a)
check("off-false-passthrough", filter_market_orders(a, o, OFF, live_ledger()) is a)
check("off-truthy-non-true-passthrough", filter_market_orders(a, o, {CONFIG_KEY: 1}, live_ledger()) is a)
check("off-bad-cfg-passthrough", filter_market_orders(a, o, None, live_ledger()) is a)

# --- ledger gating --------------------------------------------------------
check("on-no-ledger-passthrough", filter_market_orders(a, o, ON, None) is a)
check("on-wrong-ledger-type-passthrough", filter_market_orders(a, o, ON, object()) is a)
fresh = ShopLedger()
check("on-never-ticked-passthrough", filter_market_orders(a, o, ON, fresh) is fresh or filter_market_orders(a, o, ON, fresh) is a)
stale = ShopLedger()
stale.note_step(100, {"WOOL": 30}, {"WOOL": 6}, {}, 100.0)
check("on-stale-tick-passthrough", filter_market_orders(a, o, ON, stale) is a)

# --- malformed inputs ------------------------------------------------------
lg = live_ledger()
check("bad-action-passthrough", filter_market_orders(None, o, ON, lg) is None)
check("bad-market-passthrough", filter_market_orders({"market": "x"}, o, ON, lg)["market"] == "x")
check("missing-shed-passthrough", filter_market_orders(a, {"step": 1}, ON, lg) is a)
check("missing-step-passthrough", filter_market_orders(a, {"private": {"shed": {}}}, ON, lg) is a)
check("negative-step-passthrough", filter_market_orders(a, obs(-1, {}), ON, lg) is a)

# --- reserve capping --------------------------------------------------------
lg = live_ledger(500)
a2 = {"market": [["SELL", "WOOL", 100]]}
r = filter_market_orders(a2, obs(500, {"WOOL": 30}), ON, lg)
check("wool-capped-to-overflow", r["market"] == [["SELL", "WOOL", 6]])
check("input-not-mutated", a2["market"] == [["SELL", "WOOL", 100]])

r = filter_market_orders({"market": [["SELL", "WOOL", 10]]}, obs(500, {"WOOL": 20}), ON, lg)
check("under-reserve-sells-nothing", r["market"] == [["SELL", "WOOL", 0]])

r = filter_market_orders(
    {"market": [["SELL", "WOOL", 10], ["SELL", "WOOL", 10]]},
    obs(500, {"WOOL": 30}), ON, lg)
check("multi-row-allocation", r["market"] == [["SELL", "WOOL", 6], ["SELL", "WOOL", 0]])

r = filter_market_orders(
    {"market": [["SELL", "WHEAT", 50], ["BUY_LAND"], ["SELL", "WOOL", 50]]},
    obs(500, {"WOOL": 30, "WHEAT": 60}), ON, lg)
check("mixed-rows", r["market"] == [["SELL", "WHEAT", 50], ["BUY_LAND"], ["SELL", "WOOL", 6]])

r = filter_market_orders(
    {"market": [["SELL", "WOOL", 0], ["SELL", "WOOL", -5]]},
    obs(500, {"WOOL": 30}), ON, lg)
check("zero-negative-untouched", r["market"] == [["SELL", "WOOL", 0], ["SELL", "WOOL", -5]])

r = filter_market_orders({"market": [["SELL", "WOOL", 5]]}, obs(500, {"WOOL": 100}), ON, lg)
check("no-cap-needed-returns-identical", r["market"] == [["SELL", "WOOL", 5]])

# every shop product has a reserve and priority covers all nine
check("nine-products", len(SHOP_PRIORITY) == 9 and set(SHOP_PRIORITY) == set(SHOP_RESERVE))
check("priority-order", SHOP_PRIORITY[:3] == ("WOOL", "STRAWBERRY", "MELON"))

# --- ledger tick detection ---------------------------------------------------
lg = ShopLedger()
t = lg.note_step(200, {"WOOL": 30}, {"WOOL": 6}, {}, 2952.0)
check("tick-detected", t is True and lg.ticks_seen == 1 and lg.last_tick_step == 200)
check("live-inside-window", lg.shop_live(200 + SHOP_LIVENESS_STEPS) is True)
check("dead-outside-window", lg.shop_live(200 + SHOP_LIVENESS_STEPS + 1) is False)
check("dead-before-tick", lg.shop_live(199) is False)

lg2 = ShopLedger()
t = lg2.note_step(200, {"WOOL": 30}, {"WOOL": 6}, {"WOOL": 24}, 2952.0)
check("explained-drop-no-tick", t is False and lg2.ticks_seen == 0)

lg3 = ShopLedger()
t = lg3.note_step(200, {"WOOL": 30}, {"WOOL": 6}, {}, 0.0)
check("drop-without-money-no-tick", t is False)

lg4 = ShopLedger()
t = lg4.note_step(200, {"WOOL": 30}, {"WOOL": 40}, {}, 100.0)
check("shed-increase-no-tick", t is False)

for bad in [("x", {}, {}, {}, 1.0), (1, [], {}, {}, 1.0), (1, {}, {}, {}, float("nan"))]:
    try:
        ShopLedger().note_step(*bad)
        raise SystemExit("expected ValueError for %r" % (bad,))
    except ValueError:
        pass
check("ledger-input-validation", True)

snap = lg.snapshot()
check("snapshot", snap == {"ticks_seen": 1, "last_tick_step": 200})

print("ALL TESTS PASSED")

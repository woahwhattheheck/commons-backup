# SPDX-License-Identifier: Apache-2.0
"""O02 E20 hire guard and shop-arbitrage absorption weight."""
from __future__ import annotations
import os
from copy import deepcopy

def hire_guard_enabled():
    return os.environ.get("TITAN_E20_HIRE_GUARD", "0") in ("1", "true", "True")

def shop_arb_enabled():
    return os.environ.get("TITAN_SHOP_ARB", "0") in ("1", "true", "True")

def unserved_tiles(farm):
    n = 0
    for row in farm.get("tiles") or []:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            kind = tile.get("kind")
            if kind == "PLANT" and not tile.get("watered_today"):
                n += 1
            elif kind in ("COOP", "PASTURE") or "animal" in tile:
                if not tile.get("watered_today", True):
                    n += 1
    return n

def apply_hire_guard(obs, action):
    report = {"enabled": hire_guard_enabled(), "reason": "NO_OP", "changed": False}
    if not hire_guard_enabled():
        return action, report
    step = int(obs.get("step", 0))
    if step >= 718:
        report["reason"] = "NO_EDIT_TERMINAL_STEP_718"
        return action, report
    farm = obs["farms"][int(obs["player"])]
    hires_today = int(farm.get("hires_today") or 0)
    if hires_today < 3:
        report["reason"] = "HIRES_TODAY_LT_3"
        return action, report
    if unserved_tiles(farm) >= 3:
        report["reason"] = "UNSERVED_GE_3"
        return action, report
    market = list(action.get("market") or [])
    hire_idx = [i for i, o in enumerate(market) if o and o[0] == "HIRE"]
    if not hire_idx:
        report["reason"] = "NO_HIRE"
        return action, report
    if hires_today == 0:
        report["reason"] = "FIRST_HIRE_OF_DAY"
        return action, report
    out = deepcopy(action)
    m = list(out["market"])
    m[hire_idx[-1]] = []
    out["market"] = m
    report.update(changed=True, reason="E20_DROP_HIRE")
    return out, report

def shop_weight(item, shops, mechanics_shops):
    if not shop_arb_enabled():
        return 1.0
    for shop in shops or []:
        products = mechanics_shops.get(shop, ())
        if item in products:
            return 1.5
    return 1.0

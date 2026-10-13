# SPDX-License-Identifier: Apache-2.0
"""O01 public-state rival archetype edits. Off unless TITAN_RIVAL_MODEL=1."""
from __future__ import annotations
import os
from copy import deepcopy

TERMINAL = 718

def enabled():
    return os.environ.get("TITAN_RIVAL_MODEL", "0") in ("1", "true", "True")

def classify(obs, prev_prices):
    step = int(obs.get("step", 0))
    player = int(obs["player"])
    rival = obs["farms"][1 - player]
    unlocked = list(rival.get("unlocked_quadrants") or [])
    prices = dict((obs.get("market") or {}).get("prices") or {})
    if step <= 144 and len(unlocked) > 1:
        return "EARLY_EXPANDER", prices
    if prev_prices:
        for item, px in prices.items():
            try:
                if float(prev_prices.get(item, px)) - float(px) >= 15.0:
                    return "AGGRESSIVE_MARKET_DUMPER", prices
            except (TypeError, ValueError):
                continue
    return "NO_ARCHETYPE", prices

def apply_rival_model(obs, action, prev_prices=None):
    report = {"enabled": enabled(), "archetype": "NO_ARCHETYPE", "reason": "NO_ARCHETYPE", "changed": False}
    if not enabled():
        return action, report
    step = int(obs.get("step", 0))
    if step >= TERMINAL:
        report["reason"] = "NO_EDIT_TERMINAL_STEP_718"
        return action, report
    arch, prices = classify(obs, prev_prices)
    report["archetype"] = arch
    out = deepcopy(action)
    market = list(out.get("market") or [])
    player = int(obs["player"])
    farm = obs["farms"][player]
    if arch == "EARLY_EXPANDER":
        own_u = list(farm.get("unlocked_quadrants") or [])
        if "NE" not in own_u and float(farm.get("money", 0)) >= 1000:
            if not any(o and o[0] == "BUY_LAND" for o in market):
                market = [["BUY_LAND"]] + market
                out["market"] = market
                report.update(reason="EARLY_EXPANDER_BUY_LAND", changed=True)
                return out, report
        report["reason"] = "EARLY_EXPANDER_NO_EDIT"
        return out, report
    if arch == "AGGRESSIVE_MARKET_DUMPER":
        dropped = []
        new_m = []
        for o in market:
            if o and o[0] == "SELL" and len(o) > 1:
                item = o[1]
                try:
                    if prev_prices and float(prev_prices.get(item, prices.get(item, 0))) - float(prices.get(item, 0)) >= 15.0:
                        new_m.append([])
                        dropped.append(item)
                        continue
                except (TypeError, ValueError):
                    pass
            new_m.append(o)
        if dropped:
            out["market"] = new_m
            report.update(reason="DUMP_DROP_" + ",".join(dropped), changed=True)
            return out, report
        report["reason"] = "DUMPER_NO_MATCHING_SELL"
        return out, report
    report["reason"] = "NO_ARCHETYPE"
    return out, report

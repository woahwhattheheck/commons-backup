# SPDX-License-Identifier: Apache-2.0
"""E11 defer SELL when public price dumped and absorption still covers remaining steps."""
from __future__ import annotations
import os
from copy import deepcopy

def enabled():
    return os.environ.get("TITAN_E11_RIVAL_SELL", "0") in ("1", "true", "True")

def apply_e11(obs, action, price_history, config=None, absorption_fn=None):
    report = {"enabled": enabled(), "reason": "NO_OP_FLAT_MARKET", "changed": False, "deferred": []}
    if not enabled():
        return action, report
    cfg = dict(config or {})
    step = int(obs.get("step", 0))
    last = int(cfg.get("episodeSteps", 720)) - 2
    if step >= 718 or step >= last:
        report["reason"] = "NO_OP_TERMINAL_STEP"
        return action, report
    drop = float(cfg.get("rival_dump_price_drop", 15.0))
    look = int(cfg.get("rival_dump_lookback_steps", 8))
    prices = dict((obs.get("market") or {}).get("prices") or {})
    hist = list(price_history or [])
    window = [h for h in hist if step - h[0] <= look]
    dumped = set()
    for item, px in prices.items():
        for ts, snap in window:
            old = snap.get(item)
            if old is None:
                continue
            try:
                if float(old) - float(px) > drop:
                    dumped.add(item)
                    break
            except (TypeError, ValueError):
                continue
    if not dumped:
        report["reason"] = "NO_OP_FLAT_MARKET"
        return action, report
    shops = (obs.get("town") or {}).get("unlocked_shops") or []
    steps_left = max(0, last - step)
    out = deepcopy(action)
    market = []
    deferred = []
    for o in list(out.get("market") or []):
        if o and o[0] == "SELL" and len(o) > 1 and o[1] in dumped:
            item = o[1]
            absorb = 0
            if absorption_fn is not None:
                try:
                    absorb = float(absorption_fn(item, step, shops, cfg))
                except Exception:
                    absorb = 0
            if absorb * steps_left > 1:
                market.append([])
                deferred.append(item)
                continue
        market.append(o)
    out["market"] = market
    if deferred:
        report.update(changed=True, deferred=deferred, reason="RIVAL_DUMP_DEFER_" + ",".join(sorted(set(deferred))))
    else:
        report["reason"] = "NO_OP_FLAT_MARKET"
    return out, report

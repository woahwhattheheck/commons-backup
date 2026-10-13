# SPDX-License-Identifier: Apache-2.0
"""V4 EXEC-PACE-2: slope-adaptive sale-window advance skip (r04_exec_adaptive).

EXEC-PACE-2 lane (2026-09-11). Measured +$377/game mean over 16 hardened
gate cells (16/16 positive, none negative; VERDICT UNRESOLVED under the $5,000
significance floor). Ported to the V4 base tree as a default-OFF stacked key.

Mechanism: tracks a trailing 25-step observed-price history per saleable good
(WOOL/MILK/STRAWBERRY/MELON/EGG/CARROT/TOMATO). When the trailing slope exceeds
+$0.03/step the good's market is momentum-rising (shop drains outpacing
supply); pulling that good's tape-planned sales forward through the sale
window sells into LOWER prices and destroys the drain benefit, so the advance
is skipped for the good and its tape sales execute at their later due steps.
Flat/falling markets keep the window's dump-early behavior (optimal in glut
regimes). The skip happens inside reserve_sales() BEFORE debt recording, so
un-advanced units simply stay planned at their tape steps -- no E1-style debt
leak.

The enable flag lives in r04_full_router (EXEC_ADAPTIVE, set by install());
this module carries only observation state and the slope test. When the flag
is off the router never calls rising(), and note_prices() only records
history -- the action path is byte-identical to the pre-lane route.

State is per-game: observation of a step <= the last recorded step resets the
histories (new game in a reused worker process), fixing the cross-game state
leak that caused a -157k catastrophic failure in the drain-candidate gate.
Every entry point fails closed and never raises. Python standard library only.
"""

from __future__ import annotations

SLOPE_THRESHOLD = 0.03   # $/step over the trailing window to count as "rising"
HIST_WINDOW = 25         # trailing steps of observed price history
GOODS = ("WOOL", "MILK", "STRAWBERRY", "MELON", "EGG", "CARROT", "TOMATO")

_phist = {}        # good -> list of recent observed prices
_last_step = [-1]  # last step prices were recorded for


def reset():
    """Clear recorded state (for tests)."""
    _phist.clear()
    _last_step[0] = -1


def note_prices(observation):
    """Record this step's observed market prices. Never raises.

    Idempotent per step; a step <= the last recorded step means a new game in
    a reused process, so histories are reset first. Malformed input is a no-op.
    """
    try:
        try:
            step = int(observation["step"])
        except Exception:
            return
        if step <= _last_step[0]:
            _phist.clear()
        _last_step[0] = step
        prices = (observation.get("market") or {}).get("prices") or {}
        for good in GOODS:
            try:
                px = float(prices.get(good, 0) or 0)
            except Exception:
                continue
            hist = _phist.setdefault(good, [])
            hist.append(px)
            if len(hist) > HIST_WINDOW:
                del hist[0]
    except Exception:
        return


def rising(good):
    """True when the good's trailing price slope counts as rising. Never raises.

    Returns False until a full HIST_WINDOW of prices has been recorded.
    """
    try:
        hist = _phist.get(good) or []
        if len(hist) < HIST_WINDOW:
            return False
        slope = (hist[-1] - hist[0]) / (len(hist) - 1)
        return slope > SLOPE_THRESHOLD
    except Exception:
        return False


def slope(good):
    """Trailing slope $/step, or None if history is incomplete. Telemetry only."""
    try:
        hist = _phist.get(good) or []
        if len(hist) < HIST_WINDOW:
            return None
        return (hist[-1] - hist[0]) / (len(hist) - 1)
    except Exception:
        return None

# SPDX-License-Identifier: Apache-2.0
"""V4 key: direction-conditional execution pacing (r04_exec_pace).

Microstructure lane (2026-09-11). Measured +$63/game mean over 16 hardened
gate cells (signs 14+/0-/2=; GATED-PASS, STACKED under stack-and-ship).
Ported from the v3.1 candidate tree
(`~/workspace/build/arb-v4/microstructure/tree-v31exec/`, gate `gate-exec1/`)
onto the V4 base tree as a default-OFF stacked key.

Mechanism: tracks a trailing 25-step observed-price history per drainable good
(WOOL/MILK/STRAWBERRY/MELON). When the trailing slope exceeds +$0.03/step the
good's market is momentum-rising (shop drains outpacing supply): dumping the
sale window's advanced quantity in one step walks the price down for no
reason, so per-step advanced/flush sales for that good are capped at
drain-absorbing levels (WOOL 3, MILK 3, STRAWBERRY 4, MELON 6), spreading the
same units across drain ticks to harvest the recovery between chunks. When the
market is flat/falling the window keeps its dump-early behavior (optimal in
glut regimes). Direction-conditional, so it is safe in both regimes.

The caps are applied inside reserve_sales() BEFORE debt recording: un-advanced
units simply stay planned at their tape steps -- leak-free by construction (no
E1-style debt leak; E1 capped rows after debts were booked, which
debt-cancelled the remainder into the terminal liquidation). The evening flush
applies the same caps. Pacing stops at END_STEP (690) so the endgame flush
finishes unimpeded.

The enable flag lives in r04_full_router (R04_EXEC_PACE, set by
install(exec_pace=...)); this module carries only observation state, the slope
test, and the caps. When the flag is off the router's seam short-circuits
before calling cap_for(); note_prices() only records history -- the action
path is byte-identical to the unkeyed route.

State is per-game: a strictly backward step means a new/reordered game and
resets histories first. An exact same-step call is an idempotent retry and
leaves the previously recorded sample/history untouched. Every entry point
fails closed and never raises. Python standard library only.
"""

from __future__ import annotations

SLOPE_THRESHOLD = 0.03   # $/step over the trailing window to count as "rising"
HIST_WINDOW = 25         # trailing steps of observed price history
END_STEP = 690           # stop pacing near the endgame; let the flush finish
CAPS = {"WOOL": 3, "MILK": 3, "STRAWBERRY": 4, "MELON": 6}

_phist = {}        # good -> list of recent observed prices
_last_step = [-1]  # last step prices were recorded for


def reset():
    """Clear recorded state (for tests)."""
    _phist.clear()
    _last_step[0] = -1


def note_prices(observation):
    """Record this step's observed market prices. Never raises.

    Exact same-step retries are idempotent and do not double-count or erase the
    trailing window. A strictly backward step means a new/reordered game, so
    histories reset before recording the new sample. Malformed input is a no-op.
    """
    try:
        try:
            step = int(observation["step"])
        except Exception:
            return
        if step < _last_step[0]:
            _phist.clear()
        elif step == _last_step[0]:
            return
        _last_step[0] = step
        prices = (observation.get("market") or {}).get("prices") or {}
        for good in CAPS:
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


def cap_for(good):
    """Per-step advance/flush sale cap for a rising good, else None. Never raises."""
    try:
        if good in CAPS and rising(good):
            return CAPS[good]
        return None
    except Exception:
        return None

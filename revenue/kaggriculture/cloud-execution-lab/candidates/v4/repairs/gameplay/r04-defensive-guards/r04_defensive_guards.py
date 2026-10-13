# SPDX-License-Identifier: Apache-2.0
"""TITAN V4 defensive last-mile guards (r04_defensive_guards).

Standalone, stdlib-only mechanism module for the R04_DEFENSIVE_GUARDS key.
Three fail-closed guards applied after all lane wrappers via
_apply_defensive_guards (identity when nothing needs fixing):

 1. _sanitize_numeric_args: clamps non-finite/out-of-range numeric args
    (engine int() on inf/nan kills the whole interpreter step).
 2. _guard_plant_overdemand: caps per-crop PLANT at seeds held (engine drops
    ALL of a turn's PLANTs for a crop when total exceeds seeds).
 3. _guard_eod_autodrop: on the last step of a day, prepends cheapest-first
    SELL rows for projected shed overflow so the EOD auto-drop destroys
    nothing.

Key wiring: R04_DEFENSIVE_GUARDS in r04_full_router.py (default False),
install(defensive_guards=...), titan_runtime.Features.r04_defensive_guards,
TITAN-CONFIG.json "r04_defensive_guards".

Engine constants mirrored from r04_full_router.py (same values):
TURNS_PER_DAY = 24, SHED_CAPACITY = 100.
"""
from __future__ import annotations

TURNS_PER_DAY = 24
SHED_CAPACITY = 100
# The EOD guard body (carried over byte-identical from the tree) reads the
# tree's underscore-prefixed shed constant; keep the same name and value here.
_SHED_CAPACITY = 100  # matches the shedCapacity config this tree ships with.

def _guard_plant_overdemand(observation, action):
    """Cap per-crop PLANT requests at available seeds (defensive).

    The engine's atomic PLANT rule drops ALL of a turn's PLANT requests for a
    crop to PASS when their total exceeds the seeds held -- even the ones that
    could have succeeded. This guard trims the excess to explicit PASS before
    the action reaches the engine, keeping the earliest units (farmer first,
    then hands in index order). Returns the action unchanged (same object) when
    no crop is overdemanded. Fail-closed: any malformed input returns the
    action untouched.
    """
    try:
        if not isinstance(action, dict) or not isinstance(observation, dict):
            return action
        private = observation.get("private")
        if not isinstance(private, dict):
            return action
        seeds = private.get("seeds") or {}
        if not isinstance(seeds, dict):
            return action
        farmer = action.get("farmer")
        hands = action.get("hands") or []

        def _plant_crop(cmd):
            if isinstance(cmd, list) and len(cmd) >= 2 and cmd[0] == "PLANT":
                return cmd[1]
            return None

        # (crop, slot) in unit priority order; slot None = farmer.
        requests = []
        fc = _plant_crop(farmer)
        if fc is not None:
            requests.append((fc, None))
        for i, cmd in enumerate(hands):
            c = _plant_crop(cmd)
            if c is not None:
                requests.append((c, i))
        if not requests:
            return action
        counts = {}
        for crop, _ in requests:
            counts[crop] = counts.get(crop, 0) + 1
        caps = {}
        over = False
        for crop, n in counts.items():
            try:
                cap = int(seeds.get(crop, 0))
            except (TypeError, ValueError):
                return action
            if cap < 0:
                cap = 0
            caps[crop] = cap
            if n > cap:
                over = True
        if not over:
            return action
        kept = {}
        trim = set()
        for crop, slot in requests:
            k = kept.get(crop, 0)
            if k < caps[crop]:
                kept[crop] = k + 1
            else:
                trim.add(("farmer",) if slot is None else ("hands", slot))
        out = dict(action)
        out["farmer"] = ["PASS"] if ("farmer",) in trim else farmer
        new_hands = list(hands)
        for i in range(len(new_hands)):
            if ("hands", i) in trim:
                new_hands[i] = ["PASS"]
        out["hands"] = new_hands
        return out
    except Exception:
        return action


_QTY_ARG_OPS = ("PICKUP", "PLACE")
_MARKET_QTY_OPS = ("BUY_SEED", "BUY_PRODUCT", "BUY_ANIMAL", "SELL")
# int() raises TypeError/ValueError on garbage, OverflowError on inf.
_INT_ERRORS = (TypeError, ValueError, OverflowError)


def _sanitize_numeric_args(action):
    """Coerce or drop non-int-coercible numeric args on commands (defensive).

    Two engine crash vectors:
    - Unit commands: the PICKUP/PLACE paths call bare int(action[2]); any
      non-coercible qty ("abc", inf, ...) raises and kills the entire
      interpreter step for both players.
    - Market rows: _parse_order catches TypeError/ValueError around int() but
      NOT OverflowError, so a SELL with inf qty crashes the same way.
    Here: int-coercible qtys are normalized to int; anything else drops the
    unit command to PASS / replaces the market row with ["PASS"] (a no-op row
    that preserves max_orders slot positions exactly). Returns the action
    unchanged (same object) when nothing needs fixing. Fail-closed on
    malformed input.
    """
    try:
        if not isinstance(action, dict):
            return action
        changed = False

        def _fix_unit(cmd):
            if not (isinstance(cmd, list) and len(cmd) >= 3
                    and cmd[0] in _QTY_ARG_OPS):
                return cmd
            try:
                n = int(cmd[2])
            except _INT_ERRORS:
                return ["PASS"]
            if type(cmd[2]) is int:
                return cmd
            return [cmd[0], cmd[1], n] + list(cmd[3:])

        def _fix_market_row(row):
            if not (isinstance(row, list) and len(row) >= 3
                    and row[0] in _MARKET_QTY_OPS):
                return row
            try:
                n = int(row[2])
            except OverflowError:
                # The one _parse_order doesn't catch: no-op row keeps slot
                # positions under max_orders identical.
                return ["PASS"]
            except (TypeError, ValueError):
                # Engine rejects these safely; leave them for it.
                return row
            if type(row[2]) is int:
                return row
            return [row[0], row[1], n] + list(row[3:])

        farmer = action.get("farmer")
        new_farmer = _fix_unit(farmer)
        hands = action.get("hands")
        new_hands = None
        if isinstance(hands, list):
            new_hands = [_fix_unit(c) for c in hands]
        market = action.get("market")
        new_market = None
        if isinstance(market, list):
            new_market = [_fix_market_row(r) for r in market]
        if new_farmer is not farmer:
            changed = True
        if new_hands is not None and (
                len(new_hands) != len(hands)
                or any(n is not o for n, o in zip(new_hands, hands))):
            changed = True
        if new_market is not None and (
                len(new_market) != len(market)
                or any(n is not o for n, o in zip(new_market, market))):
            changed = True
        if not changed:
            return action
        out = dict(action)
        out["farmer"] = new_farmer
        if new_hands is not None:
            out["hands"] = new_hands
        if new_market is not None:
            out["market"] = new_market
        return out
    except Exception:
        return action


def _guard_eod_autodrop(observation, action):
    """Free shed room before EOD so the auto-drop destroys nothing (defensive).

    At every EOD the engine drops all carried inventories into the shed up to
    capacity and silently DISCARDS the overflow. SELL takes from the shed
    (engine _commit_unit), so on the last step of a day, if the projected
    post-market total (shed + carried - scheduled SELLs + scheduled BUYs)
    exceeds capacity, prepend SELL rows for the excess from the shed,
    cheapest first -- the EOD drop then refills the shed with carried goods
    instead of destroying them. Existing SELL rows for the same item are
    merged (qty bumped) to avoid max_orders slot pressure. Prepending keeps
    the rescue inside max_orders; displaced router rows are deferred sales,
    never destroyed goods. Identity (same object) when there is no overflow.
    """
    try:
        if not isinstance(action, dict):
            return action
        step = int(observation.get("step", -1))
        if step % TURNS_PER_DAY != TURNS_PER_DAY - 1:
            return action
        player = int(observation.get("player", 0))
        private = observation.get("private") or {}
        shed = private.get("shed") or {}
        shed_goods = {k: v for k, v in shed.items()
                      if isinstance(v, int) and v > 0}
        shed_total = sum(shed_goods.values())
        carried_total = 0
        for inv in private.get("inventories", []) or []:
            if not isinstance(inv, dict):
                continue
            for n in inv.values():
                if isinstance(n, int) and n > 0:
                    carried_total += n
        # Market phase runs before EOD: SELLs free shed room, BUY_PRODUCT /
        # BUY_ANIMAL consume it (they land in the shed). Seeds don't.
        market = action.get("market") or []
        sell_scheduled = 0
        buy_scheduled = 0
        for o in market:
            if not (isinstance(o, list) and len(o) >= 3):
                continue
            try:
                q = int(o[2])
            except _INT_ERRORS:
                continue
            if q <= 0:
                continue
            if o[0] == "SELL":
                sell_scheduled += q
            elif o[0] in ("BUY_PRODUCT", "BUY_ANIMAL"):
                buy_scheduled += q
        excess = (shed_total - sell_scheduled + buy_scheduled
                  + carried_total - _SHED_CAPACITY)
        if excess <= 0:
            return action
        prices = (observation.get("market") or {}).get("prices", {}) or {}
        lots = sorted(
            ((prices.get(item, 0), item, n) for item, n in shed_goods.items()
             if isinstance(prices.get(item, 0), (int, float))
             and prices.get(item, 0) > 0),
            key=lambda t: (t[0], t[1]),
        )
        rows = [list(o) for o in market]
        new_rows = []
        merged = False
        for _, item, n in lots:
            if excess <= 0:
                break
            sell_n = min(n, excess)
            for o in rows:
                if isinstance(o, list) and o[:2] == ["SELL", item]:
                    try:
                        o[2] = int(o[2]) + sell_n
                    except _INT_ERRORS:
                        continue
                    merged = True
                    break
            else:
                new_rows.append(["SELL", item, sell_n])
            excess -= sell_n
        if not new_rows and not merged:
            return action
        out = dict(action)
        out["market"] = new_rows + rows
        return out
    except Exception:
        return action


def _apply_defensive_guards(observation, action):
    """Defensive last-mile guards: engine footguns that silently nuke a turn.

    All three are identity (same object) when nothing needs fixing.
    NOTE (2026-09-11): a CARE cap-waste guard was built, gated, and REMOVED:
    the tape issues CARE 5k+/game as choreography (incl. deliberate over-bank
    and care-before-feed sequencing); redirecting its CAREs desyncs the tape
    and measured dM -3976 (range -5874..-2393, 8/8 cells negative) vs noguard.
    A blanket "CARE while unfed -> PASS" is likewise wrong: CARE sets
    cared_today even unfed, and a later same-day FEED still banks at EOD.
    """
    action = _sanitize_numeric_args(action)
    action = _guard_plant_overdemand(observation, action)
    return _guard_eod_autodrop(observation, action)

# SPDX-License-Identifier: Apache-2.0
"""Read-only public-information timing over a supplied route commitment boundary.

The route boundary belongs to the caller's existing structural inspector. This
module neither compares route programs nor invokes a controller or policy. It
reports shop-reveal times, never future shop identities or economic feasibility.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any


def _count(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def future_shop_reveals(now: int, *, shop_count: int, turns_per_day: int = 24,
                        unlock_interval_days: int = 3, max_instances: int = 8,
                        decision_count: int = 719) -> tuple[int, ...]:
    """Return strictly future, action-ready reveal times within the game.

    The pinned engine draws after the last action of each unlock day. That draw
    is public at the NEXT decision. The caller supplies the current instance
    count, including duplicate shops. No seed or future draw is consumed.
    """
    now = _count(now, "now")
    shop_count = _count(shop_count, "shop_count")
    max_instances = _count(max_instances, "max_instances")
    tpd = _count(turns_per_day, "turns_per_day", 1)
    interval = _count(unlock_interval_days, "unlock_interval_days", 1)
    count = _count(decision_count, "decision_count", 1)
    period = tpd * interval
    first = (now // period + 1) * period
    remaining = max(0, max_instances - shop_count)
    available = max(0, (count - 1 - first) // period + 1)
    return tuple(first + i * period for i in range(min(remaining, available)))


def information_window(*, now: int, last_compatible_decision: int | None,
                       compatible_now: bool | None, shop_count: int,
                       configuration: Mapping[str, Any] | None = None,
                       max_shop_instances: int = 8) -> dict[str, Any]:
    """Compare an existing inclusive route deadline with public reveal times.

    `last_compatible_decision` and `compatible_now` come from the same current
    route inspection. None means unavailable information, not permission to
    switch. True means only that the next reveal fits that structural window;
    worker state, funding, future prices, and expected profit remain unchecked.
    """
    if configuration is not None and not isinstance(configuration, Mapping):
        raise ValueError("configuration must be a mapping or None")
    cfg = {} if configuration is None else configuration
    now = _count(now, "now")
    if last_compatible_decision is not None:
        _count(last_compatible_decision, "last_compatible_decision")
    if compatible_now is not None and type(compatible_now) is not bool:
        raise ValueError("compatible_now must be True, False, or None")
    decisions = _count(cfg.get("episodeSteps", 720), "episodeSteps", 2) - 1
    if (compatible_now is True and
            (now >= decisions or (last_compatible_decision is not None and now > last_compatible_decision))):
        raise ValueError("positive current compatibility contradicts the supplied decision window")
    reveals = future_shop_reveals(
        now, shop_count=shop_count,
        turns_per_day=cfg.get("turnsPerDay", 24),
        unlock_interval_days=cfg.get("townShopUnlockInterval", 3),
        max_instances=max_shop_instances, decision_count=decisions)
    next_reveal = reveals[0] if reveals else None
    can_wait = None
    if next_reveal is not None:
        if compatible_now is False:
            can_wait = False
        elif compatible_now is True and last_compatible_decision is not None:
            can_wait = next_reveal <= last_compatible_decision
    available = None
    if compatible_now is False:
        available = []
    elif compatible_now is True and last_compatible_decision is not None:
        available = [s for s in reveals if s <= last_compatible_decision]
    return {"schema": "route-information-window-v1", "now": now,
            "last_compatible_decision": last_compatible_decision,
            "compatible_now": compatible_now, "decision_count": decisions,
            "future_reveal_decisions": list(reveals),
            "next_reveal_decision": next_reveal,
            "next_reveal_delay": None if next_reveal is None else next_reveal-now,
            "can_wait_for_next_reveal": can_wait,
            "reveals_while_compatible": available,
            "shop_identity": "unknown",
            "semantics": "public_timing_with_supplied_structural_boundary_not_economic_feasibility"}


def from_commitment(boundary: Mapping[str, Any], *, shop_count: int,
                    configuration: Mapping[str, Any] | None = None,
                    max_shop_instances: int = 8) -> dict[str, Any]:
    """Consume BRIDGE's inspect_commitment result, without inspecting routes again."""
    if not isinstance(boundary, Mapping):
        raise ValueError("boundary must be the current inspection mapping")
    cfg = {} if configuration is None else configuration
    if not isinstance(cfg, Mapping):
        raise ValueError("configuration must be a mapping or None")
    stop = _count(boundary["decision_stop"], "decision_stop", 1)
    if stop != _count(cfg.get("episodeSteps", 720), "episodeSteps", 2) - 1:
        raise ValueError("inspection and public clock must cover the same decision range")
    compatible = None
    if boundary.get("same_object") is True:
        compatible = False
    elif boundary.get("predicate_agrees") is not False:
        if boundary.get("structural_choice_now") is False:
            compatible = False
        elif (boundary.get("same_object") is False
              and boundary.get("structural_choice_now") is True
              and boundary.get("controller_accepts_now") is True
              and boundary.get("predicate_agrees") is True):
            compatible = True
    result = information_window(now=boundary["now"],
        last_compatible_decision=boundary.get("last_equal_prefix_checkpoint"),
        compatible_now=compatible, shop_count=shop_count, configuration=cfg,
        max_shop_instances=max_shop_instances)
    result["boundary_source"] = {key: boundary.get(key) for key in
        ("current_route", "target_route", "current_sha256", "target_sha256", "predicate_agrees")}
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now", required=True, type=int)
    parser.add_argument("--last-compatible-decision", type=int)
    parser.add_argument("--compatible-now", choices=("true", "false", "unknown"), default="unknown")
    parser.add_argument("--shop-count", required=True, type=int)
    parser.add_argument("--configuration", help="Optional current configuration JSON")
    args = parser.parse_args(argv)
    try:
        cfg = None
        if args.configuration:
            with open(args.configuration, encoding="utf-8") as handle:
                cfg = json.load(handle)
        result = information_window(now=args.now, last_compatible_decision=args.last_compatible_decision,
                                    compatible_now={"true": True, "false": False, "unknown": None}[args.compatible_now],
                                    shop_count=args.shop_count, configuration=cfg)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

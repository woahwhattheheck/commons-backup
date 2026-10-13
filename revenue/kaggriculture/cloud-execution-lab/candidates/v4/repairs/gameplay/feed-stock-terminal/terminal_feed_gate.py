# SPDX-License-Identifier: Apache-2.0
"""Inactive admission experiment for the existing native feed-stock consumer.

Call only after protect_feed_stock, with the SAME completed unit snapshot and
route. This does not execute a route, change units, create a production key, or
install itself. On unsupported inputs it returns the delegate's exact objects.
A supported override restores the exact pre-feed-guard selected action.

The proof is deliberately local: last-refresh survival and production, not
future adaptive-policy equivalence. Whole-agent economics remain a separate gate.
"""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any

STRUCTURES = {"COW": "PASTURE", "SHEEP": "PASTURE", "GOOSE": "COOP"}
STANDARD = {"boardSize": 10, "turnsPerDay": 24, "episodeSteps": 720,
            "shedCapacity": 100, "maxMarketOrdersPerTurn": 10}


def _integer(value: Any, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _only_wheat_reduction(selected: Mapping, proposed: Mapping) -> bool:
    if set(selected) != set(proposed):
        return False
    if any(selected[k] != proposed[k] for k in selected if k != "market"):
        return False
    before, after = selected.get("market"), proposed.get("market")
    if not isinstance(before, list) or not isinstance(after, list) or len(before) != len(after):
        return False
    changed = False
    for slot, (old, new) in enumerate(zip(before, after)):
        if old == new:
            continue
        if (slot >= 10 or not isinstance(old, list) or len(old) != 3
                or old[:2] != ["SELL", "WHEAT"]
                or not _integer(old[2], 1, 10**9)):
            return False
        if new != [] and not (isinstance(new, list) and len(new) == 3
                and new[:2] == ["SELL", "WHEAT"]
                and _integer(new[2], 0, old[2])):
            return False
        changed = True
    return changed


def admit_terminal_feed_override(observation: Mapping, configuration: Mapping,
                                 selected: Mapping, proposed: Mapping,
                                 report: Mapping, post_farm: Mapping,
                                 route: list) -> tuple[Mapping, Mapping]:
    """Undo an existing reserve only when every protected feed has no tail payoff.

    Preconditions: standard final full production day; an authentic, changed,
    certified native feed proposal; complete valid animal records; zero previous
    missed feeds and zero pending/current care; no future CARE in this day.
    Mixed useful/useless obligations are left to the delegate, without partial
    reallocation. Rejection preserves proposed/report identity and all inputs.
    """
    try:
        if not all(isinstance(v, Mapping) for v in (
                observation, configuration, selected, proposed, report, post_farm)):
            return proposed, report
        now = observation.get("step")
        if not _integer(now, 672, 694):
            return proposed, report
        if any(type(configuration.get(k, default)) is not int
               or configuration.get(k, default) != default
               for k, default in STANDARD.items()):
            return proposed, report
        farms = observation.get("farms")
        if (not isinstance(farms, list) or len(farms) != 2
                or not _integer(observation.get("player"), 0, 1)):
            return proposed, report
        if (report.get("changed") is not True or report.get("certified") is not True
                or report.get("reason") != "reserve_reachable_feed"
                or not _integer(report.get("withheld_units"), 1, 2)
                or not _only_wheat_reduction(selected, proposed)):
            return proposed, report
        window = report.get("window")
        if (not isinstance(window, Mapping) or window.get("crosses_reset") is not False
                or type(window.get("through_step")) is not int
                or window["through_step"] != 695):
            return proposed, report
        obligations = window.get("obligations")
        if not isinstance(obligations, list) or not obligations:
            return proposed, report
        tiles = post_farm.get("tiles")
        if (not isinstance(tiles, list) or len(tiles) != 10
                or any(not isinstance(row, list) or len(row) != 10 for row in tiles)):
            return proposed, report
        targets = set()
        for obligation in obligations:
            if (not isinstance(obligation, Mapping)
                    or not _integer(obligation.get("required_acquisition"), 1, 100)):
                return proposed, report
            feeds = obligation.get("feeds")
            if not isinstance(feeds, list) or not feeds:
                return proposed, report
            for feed in feeds:
                if not isinstance(feed, Mapping) or not _integer(feed.get("step"), now + 1, 695):
                    return proposed, report
                pos = feed.get("position")
                if (not isinstance(pos, (list, tuple)) or len(pos) != 2
                        or any(not _integer(v, 0, 9) for v in pos)):
                    return proposed, report
                x, y = pos
                animal = feed.get("animal")
                tile = tiles[y][x]
                if (animal not in STRUCTURES or not isinstance(tile, Mapping)
                        or tile.get("kind") != STRUCTURES[animal]
                        or tile.get("animal") != animal
                        or tile.get("fed_today") is not False
                        or not _integer(tile.get("consecutive_unfed"), 0, 0)
                        or not _integer(tile.get("pending_care_bonus"), 0, 0)
                        or tile.get("cared_today") is not False):
                    return proposed, report
                targets.add((x, y, animal))
        if not isinstance(route, list) or len(route) < 696:
            return proposed, report
        # CARE anywhere is a conservative veto. Do not invent a second movement
        # simulator just to accept more cases; the native guard owns reachability.
        for row in route[now + 1:696]:
            if not isinstance(row, Mapping) or not isinstance(row.get("hands", []), list):
                return proposed, report
            for action in [row.get("farmer", ["PASS"]), *row.get("hands", [])]:
                if not isinstance(action, list) or not action or action[0] == "CARE":
                    return proposed, report
        return selected, {
            "changed": False, "certified": False,
            "reason": "terminal_feed_no_survival_or_care_payoff",
            "future_cash_gain_measured": False,
            "terminal_feed_gate": {
                "step": now, "last_refresh_step": 695, "last_recorded_step": 718,
                "released_withheld_units": report["withheld_units"],
                "targets": [list(t) for t in sorted(targets)],
                "fixed_route_mechanism_only": True,
                "adaptive_policy_economics_proven": False,
            },
            "baseline_feed_report": report,
        }
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, OverflowError):
        return proposed, report

# SPDX-License-Identifier: Apache-2.0
"""P06: frequency-weighted placement score for new empty production sites.

The current producer owns service calendars, quantities and route continuation.
This helper consumes only caller-supplied counts of already-planned service legs
and ranks currently empty, already-unlocked sites. It never evicts or clears an
existing tile, never treats LOCKED as a movement obstacle, and never invents
future shops, weeds, purchases or worker state.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


def _integer(value, name, low=0, high=1_000_000):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high}")
    return value


def _position(value, name="position"):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must be an x,y pair")
    x, y = value
    if type(x) is not int or type(y) is not int:
        raise ValueError(f"{name} coordinates must be integers")
    return x, y


class _ReservedSites(frozenset):
    """Marker for a reservation set already validated by this module."""


def _reserved_sites(reserved):
    if isinstance(reserved, _ReservedSites):
        return reserved
    try:
        return _ReservedSites(_position(site, "reserved site") for site in reserved)
    except TypeError as exc:
        raise ValueError("reserved must be an iterable of x,y pairs") from exc


def distance(a, b):
    ax, ay = _position(a, "a")
    bx, by = _position(b, "b")
    return abs(ax - bx) + abs(ay - by)


def quadrant(pos, board):
    x, y = _position(pos)
    half = board // 2
    return ("N" if y < half else "S") + ("W" if x < half else "E")


@dataclass(frozen=True)
class ServiceCalendar:
    """Counts of plan-owned travel legs involving the candidate site.

    `home_to_site`: planned service starts whose preceding daily anchor is home.
    `shed_to_site`: planned input pickups already represented by the plan.
    `site_to_shed`: planned product/fertilizer deliveries already represented.
    `site_to_home`: explicit represented returns to the daily home anchor.

    These are counts, not inferred profitability or new service policy.
    """
    home_to_site: int = 0
    shed_to_site: int = 0
    site_to_shed: int = 0
    site_to_home: int = 0

    def __post_init__(self):
        for name in ("home_to_site", "shed_to_site", "site_to_shed", "site_to_home"):
            _integer(getattr(self, name), name)

    @property
    def total_legs(self):
        return self.home_to_site + self.shed_to_site + self.site_to_shed + self.site_to_home


def calendar_from_service_counts(*, water=0, care=0, feed=0, harvest=0,
                                 collect_fertilizer=0, explicit_home_returns=0):
    """Translate already-planned service-event counts to conservative travel legs.

    This is deliberately not a policy generator. The caller must obtain counts
    from its current commitment calendar. WATER/CARE/HARVEST/COLLECT require
    reaching the site; FEED additionally represents a shed pickup -> site leg;
    HARVEST/COLLECT represent site -> shed delivery.
    """
    values = {
        "water": water, "care": care, "feed": feed, "harvest": harvest,
        "collect_fertilizer": collect_fertilizer,
        "explicit_home_returns": explicit_home_returns,
    }
    for name, value in values.items():
        _integer(value, name)
    return ServiceCalendar(
        home_to_site=water + care + harvest + collect_fertilizer,
        shed_to_site=feed,
        site_to_shed=harvest + collect_fertilizer,
        site_to_home=explicit_home_returns,
    )


@dataclass(frozen=True)
class SiteScore:
    site: tuple
    total_travel: int
    home_distance: int
    shed_distance: int
    calendar: ServiceCalendar

    def as_dict(self):
        return {
            "site": list(self.site),
            "total_travel": self.total_travel,
            "home_distance": self.home_distance,
            "shed_distance": self.shed_distance,
            "calendar": {
                "home_to_site": self.calendar.home_to_site,
                "shed_to_site": self.calendar.shed_to_site,
                "site_to_shed": self.calendar.site_to_shed,
                "site_to_home": self.calendar.site_to_home,
            },
        }


def site_available(farm, site, *, board, reserved=()):
    """Only current None tiles in observed unlocked quadrants are placeable."""
    x, y = _position(site, "site")
    if not (0 <= x < board and 0 <= y < board):
        return False, "out_of_bounds"
    tiles = farm.get("tiles")
    if not isinstance(tiles, list) or y >= len(tiles) or not isinstance(tiles[y], list) or x >= len(tiles[y]):
        return False, "tile_map_unobserved"
    if (x, y) in _reserved_sites(reserved):
        return False, "reserved"
    tile = tiles[y][x]
    if tile == "LOCKED":
        return False, "locked_not_productively_usable"
    if tile is not None:
        return False, "occupied_no_eviction"
    unlocked = farm.get("unlocked_quadrants", [])
    if not isinstance(unlocked, list) or quadrant((x, y), board) not in unlocked:
        return False, "quadrant_not_unlocked"
    return True, "available"


def score_site(mechanics, farm, site, calendar, configuration=None, *, reserved=()):
    """Score one available site from actual plan-owned service leg counts."""
    if not isinstance(calendar, ServiceCalendar):
        raise TypeError("calendar must be ServiceCalendar")
    config = dict(configuration or {})
    board = _integer(config.get("boardSize", len(farm.get("tiles", []))), "boardSize", 2, 100)
    site = _position(site, "site")
    reserved = _reserved_sites(reserved)
    available, reason = site_available(farm, site, board=board, reserved=reserved)
    if not available:
        return None, {"scored": False, "reason": reason, "site": list(site)}
    if calendar.total_legs <= 0:
        return None, {"scored": False, "reason": "no_planned_service_legs", "site": list(site)}

    home = tuple(mechanics._default_spawn(board))
    shed = tuple(tuple(p) for p in mechanics._shed_access_tiles(board))
    home_distance = distance(home, site)
    shed_distance = min(distance(site, p) for p in shed)
    total = (
        calendar.home_to_site * home_distance
        + calendar.shed_to_site * shed_distance
        + calendar.site_to_shed * shed_distance
        + calendar.site_to_home * home_distance
    )
    score = SiteScore(site, total, home_distance, shed_distance, calendar)
    return score, {
        "scored": True,
        "reason": "plan_owned_service_distance",
        **score.as_dict(),
        "movement_locked_tiles_are_obstacles": False,
        "eviction_allowed": False,
    }


def rank_empty_sites(mechanics, farm, calendar, configuration=None, *, reserved=()):
    """Return deterministic ascending service-cost ranking over current empty sites."""
    config = dict(configuration or {})
    board = _integer(config.get("boardSize", len(farm.get("tiles", []))), "boardSize", 2, 100)
    reserved = _reserved_sites(reserved)
    ranked = []
    rejected = {}
    for y in range(board):
        for x in range(board):
            score, report = score_site(
                mechanics, farm, (x, y), calendar, config, reserved=reserved
            )
            if score is not None:
                ranked.append(score)
            else:
                rejected[report["reason"]] = rejected.get(report["reason"], 0) + 1
    ranked.sort(key=lambda s: (
        s.total_travel,
        s.shed_distance,
        s.home_distance,
        s.site[1],
        s.site[0],
    ))
    return ranked, {
        "scored": bool(ranked),
        "reason": "ranked_current_empty_sites" if ranked else "no_available_scored_site",
        "candidate_count": len(ranked),
        "rejected": rejected,
        "best": None if not ranked else ranked[0].as_dict(),
        "scope": "current empty unlocked tiles; caller-owned service counts; Manhattan lower-bound travel only",
    }


def compare_existing_site(mechanics, farm, current_site, calendar, configuration=None, *, reserved=()):
    """Diagnostic only: compare current site to empty candidates without evicting it."""
    if not isinstance(calendar, ServiceCalendar):
        raise TypeError("calendar must be ServiceCalendar")
    config = dict(configuration or {})
    tiles = farm.get("tiles")
    if "boardSize" in config:
        board = _integer(config["boardSize"], "boardSize", 2, 100)
    else:
        if not isinstance(tiles, list):
            return None, {"compared": False, "reason": "current_site_tile_map_unobserved"}
        board = _integer(len(tiles), "boardSize", 2, 100)
    x, y = _position(current_site, "current_site")
    if not (0 <= x < board and 0 <= y < board):
        return None, {"compared": False, "reason": "current_site_out_of_bounds"}
    if (
        not isinstance(tiles, list)
        or y >= len(tiles)
        or not isinstance(tiles[y], list)
        or x >= len(tiles[y])
    ):
        return None, {"compared": False, "reason": "current_site_tile_map_unobserved"}
    tile = tiles[y][x]
    if tile is None or tile == "LOCKED":
        return None, {"compared": False, "reason": "current_site_not_established_asset"}
    home = tuple(mechanics._default_spawn(board))
    shed = tuple(tuple(p) for p in mechanics._shed_access_tiles(board))
    home_distance = distance(home, current_site)
    shed_distance = min(distance(current_site, p) for p in shed)
    current_total = (
        calendar.home_to_site * home_distance
        + calendar.shed_to_site * shed_distance
        + calendar.site_to_shed * shed_distance
        + calendar.site_to_home * home_distance
    )
    ranked, report = rank_empty_sites(mechanics, farm, calendar, config, reserved=reserved)
    if not ranked:
        return None, {"compared": False, "reason": "no_empty_alternative", "current_travel": current_total}
    best = ranked[0]
    return {
        "current_site": [x, y],
        "current_travel": current_total,
        "best_empty_site": list(best.site),
        "best_empty_travel": best.total_travel,
        "potential_travel_saving": max(0, current_total - best.total_travel),
        "action": "diagnostic_only_no_eviction",
    }, {
        "compared": True,
        "reason": "existing_asset_preserved",
        "candidate_count": report["candidate_count"],
        "eviction_allowed": False,
    }

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""GANDER x STARVEORACLE: safe alternating-feed goose service.

Research-only composition inside the existing opening-expansion authority.
The constructed nine-goose GANDER frontier is executed with the exact pinned
official interpreter through the official final executable callback, step 718.

After the mandatory day-1 feed, odd days feed and even days skip through the
last real EOD (day 28). Every day collects fertilizer. From day 4 onward,
skip-feed days spend the freed FEED slot on HARVEST, so the same two-worker
geometry realizes base EGG output without two consecutive unfed refreshes.
Day 29 has no EOD refresh, so feeding there is terminal dead work; the terminal
route instead extracts FERT+EGG. CARE is deliberately absent.
"""
from __future__ import annotations

import builtins
import hashlib
import io
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Iterable

HERE = Path(__file__).resolve().parent
V4_ROOT = HERE.parents[1]
ENGINE_PATH = HERE.parents[3] / "reference" / "engine" / "kaggriculture.py"
GANDER_PATH = HERE / "goose_printer_oracle.py"
STARVE_PATH = V4_ROOT / "repairs" / "gameplay" / "dead-feed-care" / "starvation_cadence.py"

# The engine code reads the adjacent JSON specification at module execution.
# Keep the reviewed canonical display path for __file__/open interception even
# when a swap test redirects ENGINE_PATH to byte-identical temporary sources.
_ENGINE_EXEC_FILE = str(ENGINE_PATH)
_ENGINE_EXEC_METADATA_FILE = str(ENGINE_PATH.with_suffix(".json"))

PINNED_ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
PINNED_ENGINE_SHA256 = "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e"
PINNED_ENGINE_METADATA_GIT_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
PINNED_ENGINE_METADATA_SHA256 = "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867"
PINNED_ENGINE_METADATA_BYTES = 6002
PINNED_GANDER_GIT_BLOB = "38ae7715c233c74f24aacd5fe09f4d0d7a630037"
PINNED_STARVE_GIT_BLOB = "8831ff953faf033cc6d3892c6f32ccd1ee1af06c"
GOOSE_COUNT = 9
FIRST_SERVICE_DAY = 1
LAST_SERVICE_DAY = 29
LAST_EOD_DAY = 28
EPISODE_STEPS = 720
FINAL_EXECUTABLE_STEP = EPISODE_STEPS - 2
REGULAR_POST_HIRE_UNIT_SLOTS = 23
TERMINAL_POST_HIRE_UNIT_SLOTS = 22
INITIAL_WHEAT = 1000


class GanderStarveError(RuntimeError):
    pass


def _git_blob_bytes(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_bytes(data: bytes, path: Path, name: str) -> ModuleType:
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = None
    sys.modules[name] = module
    try:
        exec(compile(data, str(path), "exec"), module.__dict__)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _load_engine_bytes(data: bytes, metadata: bytes) -> ModuleType:
    """Execute authenticated engine Python with authenticated JSON metadata.

    The reviewed engine performs a module-level ``open(kaggriculture.json)``.
    Installing a module-local ``open`` binds that dependency to the captured
    immutable metadata snapshot, so neither code nor specification is reopened
    from a mutable repository pathname after authentication.
    """
    inserted: list[str] = []
    try:
        import kaggle_environments.utils  # type: ignore  # noqa: F401
    except ModuleNotFoundError:
        pkg = ModuleType("kaggle_environments")
        util = ModuleType("kaggle_environments.utils")

        def resolve_episode_seed(env):
            info = getattr(env, "info", {})
            return info.get("seed", 0) if isinstance(info, dict) else 0

        util.resolve_episode_seed = resolve_episode_seed
        pkg.utils = util
        sys.modules["kaggle_environments"] = pkg
        sys.modules["kaggle_environments.utils"] = util
        inserted = ["kaggle_environments.utils", "kaggle_environments"]

    name = f"titan_gander_starve_engine_{hashlib.sha256(data).hexdigest()[:12]}"
    module = ModuleType(name)
    module.__file__ = _ENGINE_EXEC_FILE
    module.__package__ = None
    sys.modules[name] = module

    metadata_path = str(Path(_ENGINE_EXEC_METADATA_FILE).absolute())

    def snapshot_open(file, mode="r", *args, **kwargs):
        try:
            candidate = str(Path(file).absolute())
        except (TypeError, ValueError):
            candidate = None
        if candidate == metadata_path:
            if any(flag in mode for flag in ("w", "a", "x", "+")):
                raise GanderStarveError(
                    "authenticated engine metadata snapshot is read-only"
                )
            if "b" in mode:
                return io.BytesIO(metadata)
            encoding = kwargs.get("encoding") or "utf-8"
            return io.StringIO(metadata.decode(encoding))
        return builtins.open(file, mode, *args, **kwargs)

    module.__dict__["open"] = snapshot_open
    try:
        exec(compile(data, _ENGINE_EXEC_FILE, "exec"), module.__dict__)
    except Exception:
        sys.modules.pop(name, None)
        raise
    finally:
        module.__dict__.pop("open", None)
        for inserted_name in inserted:
            sys.modules.pop(inserted_name, None)
    return module


def _direction(a: tuple[int, int], b: tuple[int, int]) -> str:
    dx, dy = b[0] - a[0], b[1] - a[1]
    table = {(1, 0): "EAST", (-1, 0): "WEST", (0, 1): "SOUTH", (0, -1): "NORTH"}
    try:
        return table[(dx, dy)]
    except KeyError as exc:
        raise GanderStarveError(f"non-adjacent route step: {a}->{b}") from exc


def _walk(a: tuple[int, int], b: tuple[int, int]) -> tuple[list[list[str]], tuple[int, int]]:
    x, y = a
    out: list[list[str]] = []
    while x != b[0]:
        nxt = (x + (1 if b[0] > x else -1), y)
        out.append([_direction((x, y), nxt)])
        x, y = nxt
    while y != b[1]:
        nxt = (x, y + (1 if b[1] > y else -1))
        out.append([_direction((x, y), nxt)])
        x, y = nxt
    return out, (x, y)


def worker_route(
    *,
    start: tuple[int, int],
    sites: Iterable[tuple[int, int]],
    feed: bool,
    harvest: bool,
) -> list[list[Any]]:
    """Materialize one daily route over the canonical GANDER site partition."""
    sites = tuple(tuple(p) for p in sites)
    if not sites:
        return []
    pos = start
    actions: list[list[Any]] = []
    if feed:
        actions.append(["PICKUP", "WHEAT", len(sites)])
    for site in sites:
        moves, pos = _walk(pos, site)
        actions.extend(moves)
        if feed:
            actions.append(["FEED"])
        actions.append(["COLLECT_FERTILIZER"])
        if harvest:
            actions.append(["HARVEST"])
    moves, pos = _walk(pos, (4, 4))
    actions.extend(moves)
    actions.append(["DROP"])
    return actions


def _canonical_sources() -> tuple[ModuleType, ModuleType, ModuleType, dict[str, Any]]:
    """Capture/authenticate every executable authority exactly once."""
    engine_metadata_path = ENGINE_PATH.with_suffix(".json")
    try:
        gander_bytes = GANDER_PATH.read_bytes()
        starve_bytes = STARVE_PATH.read_bytes()
        engine_bytes = ENGINE_PATH.read_bytes()
        engine_metadata_bytes = engine_metadata_path.read_bytes()
    except OSError as exc:
        raise GanderStarveError(f"cannot capture canonical source snapshot: {exc}") from exc

    identities: dict[str, Any] = {
        "gander_helper_git_blob": _git_blob_bytes(gander_bytes),
        "starve_helper_git_blob": _git_blob_bytes(starve_bytes),
        "engine_git_blob": _git_blob_bytes(engine_bytes),
        "engine_sha256": _sha256_bytes(engine_bytes),
        "engine_metadata_git_blob": _git_blob_bytes(engine_metadata_bytes),
        "engine_metadata_sha256": _sha256_bytes(engine_metadata_bytes),
        "engine_metadata_bytes": len(engine_metadata_bytes),
    }
    if identities["gander_helper_git_blob"] != PINNED_GANDER_GIT_BLOB:
        raise GanderStarveError(
            "GANDER helper drift: expected "
            f"{PINNED_GANDER_GIT_BLOB}, got {identities['gander_helper_git_blob']}"
        )
    if identities["starve_helper_git_blob"] != PINNED_STARVE_GIT_BLOB:
        raise GanderStarveError(
            "STARVEORACLE helper drift: expected "
            f"{PINNED_STARVE_GIT_BLOB}, got {identities['starve_helper_git_blob']}"
        )
    if identities["engine_git_blob"] != PINNED_ENGINE_GIT_BLOB:
        raise GanderStarveError(
            f"engine Git identity drift: expected {PINNED_ENGINE_GIT_BLOB}, "
            f"got {identities['engine_git_blob']}"
        )
    if identities["engine_sha256"] != PINNED_ENGINE_SHA256:
        raise GanderStarveError(
            f"engine SHA identity drift: expected {PINNED_ENGINE_SHA256}, "
            f"got {identities['engine_sha256']}"
        )
    if identities["engine_metadata_git_blob"] != PINNED_ENGINE_METADATA_GIT_BLOB:
        raise GanderStarveError(
            "engine metadata Git identity drift: expected "
            f"{PINNED_ENGINE_METADATA_GIT_BLOB}, got "
            f"{identities['engine_metadata_git_blob']}"
        )
    if identities["engine_metadata_sha256"] != PINNED_ENGINE_METADATA_SHA256:
        raise GanderStarveError(
            "engine metadata SHA identity drift: expected "
            f"{PINNED_ENGINE_METADATA_SHA256}, got "
            f"{identities['engine_metadata_sha256']}"
        )
    if identities["engine_metadata_bytes"] != PINNED_ENGINE_METADATA_BYTES:
        raise GanderStarveError(
            "engine metadata size drift: expected "
            f"{PINNED_ENGINE_METADATA_BYTES}, got {identities['engine_metadata_bytes']}"
        )

    gander = _load_bytes(gander_bytes, GANDER_PATH, "titan_v4_gander_starve_gander")
    starve = _load_bytes(starve_bytes, STARVE_PATH, "titan_v4_gander_starve_starve")
    if getattr(gander, "EXPECTED_ENGINE_BLOB", None) != PINNED_ENGINE_GIT_BLOB:
        raise GanderStarveError("GANDER engine identity drift")
    if getattr(starve, "ENGINE_GIT_BLOB", None) != PINNED_ENGINE_GIT_BLOB:
        raise GanderStarveError("STARVEORACLE engine identity drift")
    if getattr(starve, "ENGINE_SHA256", None) != PINNED_ENGINE_SHA256:
        raise GanderStarveError("STARVEORACLE engine SHA drift")

    engine = _load_engine_bytes(engine_bytes, engine_metadata_bytes)
    return gander, starve, engine, identities


def _route_contract(gander: ModuleType) -> dict[str, Any]:
    main_sites = tuple(tuple(p) for p in gander.MAIN_TWO_WORKER)
    hand_sites = tuple(tuple(p) for p in gander.HAND_TWO_WORKER)
    if len(main_sites) + len(hand_sites) != GOOSE_COUNT:
        raise GanderStarveError("GANDER site cardinality drift")
    if set(main_sites) & set(hand_sites):
        raise GanderStarveError("GANDER worker partitions overlap")

    feed_main = worker_route(start=(4, 4), sites=main_sites, feed=True, harvest=False)
    feed_hand = worker_route(start=(5, 4), sites=hand_sites, feed=True, harvest=False)
    skip_main = worker_route(start=(4, 4), sites=main_sites, feed=False, harvest=True)
    skip_hand = worker_route(start=(5, 4), sites=hand_sites, feed=False, harvest=True)
    full_main = worker_route(start=(4, 4), sites=main_sites, feed=True, harvest=True)
    full_hand = worker_route(start=(5, 4), sites=hand_sites, feed=True, harvest=True)

    authored = gander.day1_keepalive_schedule()
    authored_counts = {
        op: sum(1 for action in authored if action.op == op)
        for op in ("PICKUP", "FEED", "COLLECT_FERTILIZER", "DROP")
    }
    if authored_counts != {
        "PICKUP": 2,
        "FEED": 9,
        "COLLECT_FERTILIZER": 9,
        "DROP": 2,
    }:
        raise GanderStarveError(f"GANDER service contract drift: {authored_counts}")
    if max((action.step for action in authored), default=0) > 45:
        raise GanderStarveError("GANDER day-1 route no longer fits")
    if max(len(feed_main), len(feed_hand), len(skip_main), len(skip_hand)) > REGULAR_POST_HIRE_UNIT_SLOTS:
        raise GanderStarveError("composed route exceeds regular post-HIRE unit window")
    if max(len(skip_main), len(skip_hand)) > TERMINAL_POST_HIRE_UNIT_SLOTS:
        raise GanderStarveError("terminal extraction route exceeds final post-HIRE unit window")
    if max(len(full_main), len(full_hand)) <= REGULAR_POST_HIRE_UNIT_SLOTS:
        raise GanderStarveError("all-nine FEED+FERT+HARVEST unexpectedly fits two-worker window")

    return {
        "main_sites": main_sites,
        "hand_sites": hand_sites,
        "authored_counts": authored_counts,
        "route_lengths": {
            "feed_fert": [len(feed_main), len(feed_hand)],
            "skip_feed_fert_harvest": [len(skip_main), len(skip_hand)],
            "feed_fert_harvest": [len(full_main), len(full_hand)],
        },
    }


def _inventory_total(private: Any, item: str) -> int:
    shed = private["shed"].get(item, 0)
    carried = sum(inv.get(item, 0) for inv in private["inventories"])
    return int(shed + carried)


def default_feed_days() -> set[int]:
    # Feeding is required only before a real future EOD starvation refresh.
    # Official execution ends at callback 718 (day 29 hour 22), so day 29 has
    # no EOD and feeding there is pure terminal dead work.
    return set(range(FIRST_SERVICE_DAY, LAST_EOD_DAY + 1, 2))


def run_composite(*, feed_days: set[int] | None = None) -> dict[str, Any]:
    """Execute exact interpreter state through official final callback step 718."""
    gander, starve, engine, source_ids = _canonical_sources()
    contract = _route_contract(gander)
    state, env = starve._make_state_env(engine)
    # STARVEORACLE intentionally uses a huge episode for generic cadence probes.
    # This composite instead binds the reviewed official episode horizon so the
    # interpreter itself, not merely this loop, transitions both players DONE at
    # the exact final executable callback.
    env.configuration.episodeSteps = EPISODE_STEPS
    farm = state[0].observation.farms[0]
    private = state[0].observation.private

    # Recreate the certified frontier at the exact post-EOD0 semantic boundary.
    sites = contract["main_sites"] + contract["hand_sites"]
    for x, y in sites:
        if farm["tiles"][y][x] is not None:
            raise GanderStarveError(f"GANDER site not empty at initialization: {(x, y)}")
        farm["tiles"][y][x] = engine._new_animal("GOOSE", 0)
    engine._daily_refresh_animals(farm, 0)
    if any(farm["tiles"][y][x].get("consecutive_unfed") != 1 for x, y in sites):
        raise GanderStarveError("post-EOD0 unfed boundary drift")
    if any(not farm["tiles"][y][x].get("fertilizer_available") for x, y in sites):
        raise GanderStarveError("post-EOD0 fertilizer boundary drift")

    # Preserve GANDER's actual $299 post-Day0 liquidity; daily first HIRE is $1.
    farm["money"] = 299.0
    private["shed"]["WHEAT"] = INITIAL_WHEAT

    selected_feed_days = default_feed_days() if feed_days is None else set(feed_days)
    counts = {
        "hire_orders": 0,
        "feed_attempts": 0,
        "fertilizer_collect_attempts": 0,
        "harvest_attempts": 0,
        "care_attempts": 0,
    }
    max_yield_units = 0
    max_consecutive_unfed = 1
    max_route_actions = 0
    escaped_day: int | None = None
    last_step_executed: int | None = None

    for day in range(FIRST_SERVICE_DAY, LAST_SERVICE_DAY + 1):
        feed = day in selected_feed_days
        harvest = (not feed) and day >= 4
        main_route = worker_route(
            start=(4, 4), sites=contract["main_sites"], feed=feed, harvest=harvest
        )
        hand_route = worker_route(
            start=(5, 4), sites=contract["hand_sites"], feed=feed, harvest=harvest
        )
        allowed_slots = (
            TERMINAL_POST_HIRE_UNIT_SLOTS if day == LAST_SERVICE_DAY
            else REGULAR_POST_HIRE_UNIT_SLOTS
        )
        max_route_actions = max(max_route_actions, len(main_route), len(hand_route))
        if max(len(main_route), len(hand_route)) > allowed_slots:
            raise GanderStarveError(
                f"day {day} route exceeds post-HIRE action window {allowed_slots}"
            )

        counts["hire_orders"] += 1
        counts["feed_attempts"] += GOOSE_COUNT if feed else 0
        counts["fertilizer_collect_attempts"] += GOOSE_COUNT
        counts["harvest_attempts"] += GOOSE_COUNT if harvest else 0

        for hour in range(24):
            step = day * 24 + hour
            if step > FINAL_EXECUTABLE_STEP:
                break
            last_step_executed = step
            state[0].observation.step = step
            farmer_action = ["PASS"] if hour == 0 else (
                main_route[hour - 1] if hour - 1 < len(main_route) else ["PASS"]
            )
            hand_action = ["PASS"] if hour == 0 else (
                hand_route[hour - 1] if hour - 1 < len(hand_route) else ["PASS"]
            )
            market = [["HIRE"]] if hour == 0 else []
            state[0].action = {
                "farmer": farmer_action,
                "hands": [hand_action],
                "market": market,
            }
            state[1].action = {"farmer": ["PASS"], "hands": [], "market": []}
            engine.interpreter(state, env)

            living = 0
            for x, y in sites:
                tile = farm["tiles"][y][x]
                if isinstance(tile, dict) and tile.get("animal") == "GOOSE":
                    living += 1
                    max_yield_units = max(max_yield_units, int(tile.get("yield_units", 0)))
                    max_consecutive_unfed = max(
                        max_consecutive_unfed, int(tile.get("consecutive_unfed", 0))
                    )
            if living != GOOSE_COUNT:
                escaped_day = day
                break
        if escaped_day is not None:
            break

    living_tiles = [
        farm["tiles"][y][x]
        for x, y in sites
        if isinstance(farm["tiles"][y][x], dict)
        and farm["tiles"][y][x].get("animal") == "GOOSE"
    ]
    final_held_egg = sum(int(tile.get("yield_units", 0)) for tile in living_tiles)
    final_pending_fertilizer = sum(
        1 for tile in living_tiles if tile.get("fertilizer_available")
    )
    egg_total = _inventory_total(private, "EGG") + final_held_egg
    fertilizer_total = _inventory_total(private, "FERTILIZER") + final_pending_fertilizer
    wheat_remaining = _inventory_total(private, "WHEAT")
    wheat_consumed = INITIAL_WHEAT - wheat_remaining

    # Fair baseline: feed every day followed by an actual EOD refresh. Feeding
    # day 29 would itself be terminal dead work and is excluded from baseline.
    full_daily_feed_through_last_eod = LAST_EOD_DAY * GOOSE_COUNT
    terminal_statuses = [getattr(player, "status", None) for player in state]
    return {
        "schema": "titan.v4.gander-starve-composite/v4",
        "engine_git_blob": source_ids["engine_git_blob"],
        "engine_sha256": source_ids["engine_sha256"],
        "engine_metadata_git_blob": source_ids["engine_metadata_git_blob"],
        "engine_metadata_sha256": source_ids["engine_metadata_sha256"],
        "episode_steps": EPISODE_STEPS,
        "final_executable_step": FINAL_EXECUTABLE_STEP,
        "last_step_executed": last_step_executed,
        "terminal_statuses": terminal_statuses,
        "days": [FIRST_SERVICE_DAY, LAST_SERVICE_DAY],
        "last_eod_day": LAST_EOD_DAY,
        "feed_days": sorted(selected_feed_days),
        "skip_days": [
            day for day in range(FIRST_SERVICE_DAY, LAST_SERVICE_DAY + 1)
            if day not in selected_feed_days
        ],
        "terminal_day_feed_is_dead_work": LAST_SERVICE_DAY not in selected_feed_days,
        "survived": escaped_day is None and len(living_tiles) == GOOSE_COUNT,
        "escaped_day": escaped_day,
        "living_geese": len(living_tiles),
        "egg_total": egg_total,
        "fertilizer_total": fertilizer_total,
        "wheat_consumed": wheat_consumed,
        "wheat_saved_vs_feed_daily_through_last_eod": full_daily_feed_through_last_eod - wheat_consumed,
        "feed_actions_saved_vs_feed_daily_through_last_eod": full_daily_feed_through_last_eod - counts["feed_attempts"],
        "max_goose_yield_units_seen": max_yield_units,
        "max_consecutive_unfed_seen": max_consecutive_unfed,
        "final_held_egg": final_held_egg,
        "final_pending_fertilizer": final_pending_fertilizer,
        "max_route_actions_after_hire": max_route_actions,
        "action_attempts": counts,
        "source_contract": {
            "gander_frontier_geese": GOOSE_COUNT,
            "gander_helper_git_blob": source_ids["gander_helper_git_blob"],
            "starve_helper_git_blob": source_ids["starve_helper_git_blob"],
            "engine_metadata_git_blob": source_ids["engine_metadata_git_blob"],
            "engine_metadata_sha256": source_ids["engine_metadata_sha256"],
            "engine_metadata_bytes": source_ids["engine_metadata_bytes"],
            "gander_day1_service_counts": contract["authored_counts"],
            "starve_engine_git_blob": getattr(starve, "ENGINE_GIT_BLOB"),
            "immutable_source_snapshots": True,
            "engine_executed_from_authenticated_snapshot": True,
            "engine_metadata_served_from_authenticated_snapshot": True,
            "official_episode_horizon_bound": True,
            "regular_post_hire_unit_slots": REGULAR_POST_HIRE_UNIT_SLOTS,
            "terminal_post_hire_unit_slots": TERMINAL_POST_HIRE_UNIT_SLOTS,
            "route_lengths": contract["route_lengths"],
            "all_nine_feed_fert_harvest_fits_two_workers": (
                max(contract["route_lengths"]["feed_fert_harvest"])
                <= REGULAR_POST_HIRE_UNIT_SLOTS
            ),
            "terminal_skip_feed_fert_harvest_fits_two_workers": (
                max(contract["route_lengths"]["skip_feed_fert_harvest"])
                <= TERMINAL_POST_HIRE_UNIT_SLOTS
            ),
            "care_used": False,
            "economics_claim": False,
            "runtime_change": False,
            "default_change": False,
        },
    }


def build_report() -> dict[str, Any]:
    safe = run_composite()
    # Historical literal mistake killer: post-EOD0 geese already carry one miss,
    # so skipping day 1 causes the second miss and immediate escape.
    unsafe_feed_days = set(range(3, LAST_EOD_DAY + 1, 2))
    unsafe = run_composite(feed_days=unsafe_feed_days)
    if not safe["survived"]:
        raise GanderStarveError("safe composite cadence did not survive")
    if safe["last_step_executed"] != FINAL_EXECUTABLE_STEP:
        raise GanderStarveError("episode boundary drift")
    if safe["terminal_statuses"] != ["DONE", "DONE"]:
        raise GanderStarveError(
            f"interpreter did not terminate at official horizon: {safe['terminal_statuses']}"
        )
    if unsafe["escaped_day"] != 1:
        raise GanderStarveError("day-1 mandatory-feed boundary disappeared")
    return {
        "schema": "titan.v4.gander-starve-report/v4",
        "safe_composite": safe,
        "mandatory_day1_feed_predecessor": {
            "escaped_day": unsafe["escaped_day"],
            "survived": unsafe["survived"],
        },
        "interpretation": {
            "mechanism": (
                "after mandatory day-1 feed, alternate feed/skip through the last real EOD; "
                "on mature skip days replace FEED with HARVEST while retaining daily FERT; "
                "skip terminal day-29 feed because no EOD starvation check follows callback 718"
            ),
            "capacity_theorem": (
                "canonical two-worker all-nine FEED+FERT+HARVEST requires 25 actions "
                "per worker and exceeds 23 regular post-HIRE slots; skip-feed FERT+HARVEST "
                "uses 19/20 and also fits the 22-slot terminal day"
            ),
            "wheat_savings_are_units_not_cash": True,
            "care_value_modeled": False,
            "market_prices_modeled": False,
            "opponent_modeled": False,
            "promotion_decision": "NOT_ASSESSED",
        },
        "next_gate": (
            "Consume this cadence only through the existing opener/native scheduler. "
            "Run both seats versus current opponents with exact WHEAT acquisition, CARE "
            "opportunity cost, shed capacity, EGG/FERT sale timing and feed-deadline fallback."
        ),
    }


def main() -> int:
    try:
        report = build_report()
    except (OSError, UnicodeError, ValueError, GanderStarveError) as exc:
        print(f"GANDER_STARVE BLOCKED: {exc}")
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

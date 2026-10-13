#!/usr/bin/env python3
"""Source-bound census of pre-purchase staging in future locked quadrants.

Research/custody only. This tool proves engine ordering and movement semantics,
then inventories authored BUY_LAND/HIRE route rows. It does not claim market
fills, cash feasibility, EV, activation, or promotion.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import zlib

ENGINE_REL = Path("reference/engine/kaggriculture.py")
ARLENE_REL = Path("reference/next-panel/vendor/arlene.py")
ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
ARLENE_GIT_BLOB = "bdb9cf58148a3c7961c085f4902759537decabf6"
BOARD = 10
MAX_MARKET_ORDERS = 10


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tree(text: str) -> ast.Module:
    return ast.parse(text)


def _function(text: str, name: str) -> ast.FunctionDef:
    for node in _tree(text).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise ValueError(f"missing function {name}")


def _constant(text: str, name: str):
    for node in _tree(text).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                return ast.literal_eval(node.value)
    raise ValueError(f"missing constant {name}")


def _call_lines(text: str, function_name: str, callee: str) -> list[int]:
    node = _function(text, function_name)
    out = []
    for part in ast.walk(node):
        if not isinstance(part, ast.Call):
            continue
        fn = part.func
        if isinstance(fn, ast.Name) and fn.id == callee:
            out.append(part.lineno)
    return sorted(out)


def _compile_subset(text: str, names: list[str], globals_dict: dict):
    wanted = set(names)
    nodes = [
        node
        for node in _tree(text).body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    found = {node.name for node in nodes}
    missing = sorted(wanted - found)
    if missing:
        raise ValueError(f"missing functions: {missing}")
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    env = dict(globals_dict)
    exec(compile(module, "<landstage-source>", "exec"), env, env)
    return env


def quadrant_of(x: int, y: int, board: int = BOARD) -> str:
    half = board // 2
    return ("N" if y < half else "S") + ("W" if x < half else "E")


def shed_access_tiles(board: int = BOARD) -> list[tuple[int, int]]:
    half = board // 2
    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]


def spawn_position(positions: list[tuple[int, int]], board: int = BOARD) -> tuple[int, int]:
    tiles = shed_access_tiles(board)
    counts = {p: 0 for p in tiles}
    for pos in positions:
        if tuple(pos) in counts:
            counts[tuple(pos)] += 1
    return min(tiles, key=lambda p: (counts[p], tiles.index(p)))


def _distance_to_quadrant(pos: tuple[int, int], quadrant: str, board: int = BOARD) -> int:
    points = [
        (x, y)
        for y in range(board)
        for x in range(board)
        if quadrant_of(x, y, board) == quadrant
    ]
    return min(abs(pos[0] - x) + abs(pos[1] - y) for x, y in points)


def geometry(board: int = BOARD) -> dict:
    default = shed_access_tiles(board)[0]
    future = ("NE", "SW", "SE")
    distances = {}
    for q in future:
        vals = [
            abs(default[0] - x) + abs(default[1] - y)
            for y in range(board)
            for x in range(board)
            if quadrant_of(x, y, board) == q
        ]
        distances[q] = {
            "min_moves_from_default_spawn": min(vals),
            "max_moves_from_default_spawn": max(vals),
            "best_case_post_purchase_callbacks_to_first_tile_op": min(vals) + 1,
            "best_case_callbacks_saved_if_already_staged": min(vals),
        }
    positions = [default]
    hires = []
    for index in range(1, 4):
        pos = spawn_position(positions, board)
        positions.append(pos)
        hires.append(
            {
                "hire_number": index,
                "position": list(pos),
                "quadrant": quadrant_of(*pos, board),
            }
        )
    return {
        "board": board,
        "default_spawn": list(default),
        "future_quadrant_distances": distances,
        "first_three_zero_occupancy_hire_spawns": hires,
    }


def prove_engine(engine_text: str) -> dict:
    unit_lines = _call_lines(engine_text, "interpreter", "_apply_unit_action")
    market_lines = _call_lines(engine_text, "interpreter", "_process_market")
    if not unit_lines or len(market_lines) != 1 or max(unit_lines) >= market_lines[0]:
        raise ValueError("engine no longer proves unit-before-market ordering")

    moves = _constant(engine_text, "FARMER_MOVES")
    land_order = _constant(engine_text, "LAND_ORDER")
    land_prices = _constant(engine_text, "LAND_PRICES")
    if land_order != ["NE", "SW", "SE"] or land_prices != [1000, 2000, 4000]:
        raise ValueError("unexpected land order/prices")

    move_env = _compile_subset(
        engine_text,
        ["_farmer_position", "_set_farmer_position", "_farmer_inventory", "_apply_unit_action"],
        {"FARMER_MOVES": moves},
    )
    farm = {
        "farmer": [4, 4],
        "hands": [],
        "tiles": [["LOCKED" for _ in range(BOARD)] for _ in range(BOARD)],
    }
    private = {"shed": {}, "seeds": {}, "inventories": [{}]}
    move_env["_apply_unit_action"](farm, private, 0, ["EAST"], BOARD, 0, 24, 100)
    if farm["farmer"] != [5, 4]:
        raise ValueError("LOCKED-transit probe failed")

    geom_env = _compile_subset(
        engine_text,
        ["_quadrant_of", "_shed_access_tiles", "_default_spawn", "_spawn_hand", "_do_buy_land"],
        {"LAND_ORDER": land_order, "LAND_PRICES": land_prices},
    )
    spawn_farm = {
        "farmer": list(geom_env["_default_spawn"](BOARD)),
        "hands": [],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
        "money": 10000.0,
    }
    spawned = []
    for _ in range(3):
        pos = geom_env["_spawn_hand"](spawn_farm, BOARD)
        spawn_farm["hands"].append(pos)
        spawned.append(list(pos))
    expected_spawns = [[5, 4], [4, 5], [5, 5]]
    if spawned != expected_spawns:
        raise ValueError(f"unexpected first-three spawn geometry: {spawned}")

    land_farm = {
        "money": 10000.0,
        "unlocked_quadrants": ["NW"],
        "tiles": [
            [None if quadrant_of(x, y, BOARD) == "NW" else "LOCKED" for x in range(BOARD)]
            for y in range(BOARD)
        ],
    }
    geom_env["_do_buy_land"](land_farm, BOARD)
    if land_farm["unlocked_quadrants"] != ["NW", "NE"]:
        raise ValueError("first BUY_LAND did not unlock NE")
    for y in range(BOARD):
        for x in range(BOARD):
            q = quadrant_of(x, y, BOARD)
            tile = land_farm["tiles"][y][x]
            if q in ("NW", "NE") and tile == "LOCKED":
                raise ValueError("BUY_LAND left target quadrant locked")
            if q in ("SW", "SE") and tile != "LOCKED":
                raise ValueError("BUY_LAND mutated a later quadrant")

    return {
        "unit_action_call_lines": unit_lines,
        "market_call_line": market_lines[0],
        "unit_before_market": True,
        "locked_transit_probe": {"start": [4, 4], "action": ["EAST"], "end": farm["farmer"]},
        "first_three_hire_spawns": spawned,
        "land_order": land_order,
        "land_prices": land_prices,
    }


def decode_arlene_routes(text: str) -> dict[str, list[dict]]:
    blob = _constant(text, "_BLOB")
    payload = json.loads(zlib.decompress(base64.b64decode(blob)).decode())
    main_id = payload["main"]
    routes = {main_id: payload["full"]}
    pending = list(payload["tails"])
    while pending:
        progress = False
        rest = []
        for row in pending:
            parent = row["parent"]
            if parent not in routes:
                rest.append(row)
                continue
            at = int(row["at"])
            routes[row["h"]] = routes[parent][:at] + row["suffix"]
            progress = True
        if not progress:
            unresolved = sorted(str(row.get("h")) for row in rest)
            raise ValueError(f"unresolved/cyclic Arlene route parents: {unresolved}")
        pending = rest
    if not routes or any(not isinstance(route, list) for route in routes.values()):
        raise ValueError("malformed Arlene routes")
    return routes


def _move(pos: tuple[int, int], action, moves: dict, board: int) -> tuple[int, int]:
    if not isinstance(action, list) or not action:
        return pos
    delta = moves.get(action[0])
    if delta is None:
        return pos
    q = (pos[0] + delta[0], pos[1] + delta[1])
    return q if 0 <= q[0] < board and 0 <= q[1] < board else pos


def census_route(
    route_id: str,
    route: list[dict],
    moves: dict,
    land_order: list[str],
    board: int = BOARD,
) -> dict:
    default = shed_access_tiles(board)[0]
    actors = [{"id": 0, "position": default, "created_step": -1, "created_slot": None}]
    unlocked = ["NW"]
    events = []
    hire_events = 0

    for step, row in enumerate(route):
        row = row if isinstance(row, dict) else {}
        unit_rows = [row.get("farmer", ["PASS"]), *(row.get("hands", []) or [])]
        for actor, action in zip(actors, unit_rows):
            actor["position"] = _move(actor["position"], action, moves, board)

        market = row.get("market", [])
        market = market if isinstance(market, list) else []
        for slot, order in enumerate(market[:MAX_MARKET_ORDERS]):
            if not isinstance(order, list) or not order:
                continue
            op = order[0]
            if op == "HIRE":
                pos = spawn_position([a["position"] for a in actors], board)
                actor = {
                    "id": len(actors),
                    "position": pos,
                    "created_step": step,
                    "created_slot": slot,
                }
                actors.append(actor)
                hire_events += 1
                continue
            if op != "BUY_LAND":
                continue

            land_index = len(unlocked) - 1
            if land_index >= len(land_order):
                continue
            target = land_order[land_index]
            staged = [
                a
                for a in actors
                if quadrant_of(*a["position"], board) == target
            ]
            prior_hire = [
                a
                for a in staged
                if a["created_step"] == step
                and a["created_slot"] is not None
                and a["created_slot"] < slot
            ]
            eod_reset = (step + 1) % 24 == 0
            surviving = [] if eod_reset else staged
            min_moves = min(
                _distance_to_quadrant(a["position"], target, board) for a in actors
            )
            events.append(
                {
                    "step": step,
                    "market_slot": slot,
                    "target_quadrant": target,
                    "actor_positions_at_commit": [
                        {
                            "id": a["id"],
                            "position": list(a["position"]),
                            "quadrant": quadrant_of(*a["position"], board),
                            "created_step": a["created_step"],
                            "created_slot": a["created_slot"],
                        }
                        for a in actors
                    ],
                    "staged_actor_ids": [a["id"] for a in staged],
                    "same_callback_prior_hire_actor_ids": [a["id"] for a in prior_hire],
                    "eod_reset_after_market": eod_reset,
                    "staged_actor_ids_surviving_to_next_callback": [a["id"] for a in surviving],
                    "min_moves_from_any_actor_to_target_at_commit": min_moves,
                    "lower_bound_callbacks_to_first_target_tile_op_without_prior_stage":
                        min_moves + 1,
                }
            )
            unlocked.append(target)

        if (step + 1) % 24 == 0:
            actors = [{"id": 0, "position": default, "created_step": -1, "created_slot": None}]

    return {
        "route_id": route_id,
        "steps": len(route),
        "authored_hire_rows": hire_events,
        "authored_buy_land_events": len(events),
        "events": events,
    }


def build_report(root: Path) -> dict:
    root = root.resolve()
    engine_path = root / ENGINE_REL
    arlene_path = root / ARLENE_REL
    if not engine_path.is_file() or not arlene_path.is_file():
        raise ValueError("expected cloud-execution-lab root with engine and Arlene sources")
    engine_raw = engine_path.read_bytes()
    arlene_raw = arlene_path.read_bytes()
    observed_engine = git_blob(engine_raw)
    observed_arlene = git_blob(arlene_raw)
    if observed_engine != ENGINE_GIT_BLOB:
        raise ValueError(
            f"official engine drift: expected {ENGINE_GIT_BLOB}, observed {observed_engine}"
        )
    if observed_arlene != ARLENE_GIT_BLOB:
        raise ValueError(
            f"Arlene drift: expected {ARLENE_GIT_BLOB}, observed {observed_arlene}"
        )

    engine_text = engine_raw.decode("utf-8")
    arlene_text = arlene_raw.decode("utf-8")
    proof = prove_engine(engine_text)
    routes = decode_arlene_routes(arlene_text)
    moves = _constant(engine_text, "FARMER_MOVES")
    land_order = _constant(engine_text, "LAND_ORDER")
    route_rows = [
        census_route(route_id, route, moves, land_order)
        for route_id, route in sorted(routes.items())
    ]
    events = [event for route in route_rows for event in route["events"]]
    staged = [e for e in events if e["staged_actor_ids"]]
    surviving = [e for e in events if e["staged_actor_ids_surviving_to_next_callback"]]
    prior_hire = [e for e in events if e["same_callback_prior_hire_actor_ids"]]

    return {
        "schema": "titan-v4-land-staging-census/v1",
        "scope": "research/source/authored-route census only; no fill, EV, activation, or policy claim",
        "sources": {
            "engine": {
                "path": str(ENGINE_REL),
                "git_blob": observed_engine,
                "sha256": sha256(engine_raw),
                "bytes": len(engine_raw),
            },
            "arlene": {
                "path": str(ARLENE_REL),
                "git_blob": observed_arlene,
                "sha256": sha256(arlene_raw),
                "bytes": len(arlene_raw),
            },
        },
        "engine_proof": proof,
        "geometry": geometry(),
        "route_summary": {
            "routes": len(route_rows),
            "authored_buy_land_events": len(events),
            "events_with_worker_already_in_target_quadrant": len(staged),
            "events_with_staged_worker_surviving_to_next_callback": len(surviving),
            "events_with_same_callback_prior_hire_in_target_quadrant": len(prior_hire),
            "assumption": (
                "Authored census assumes each HIRE/BUY_LAND row is reached and succeeds; "
                "cash, fills, runtime selection, and economics are not inferred."
            ),
        },
        "routes": route_rows,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", type=Path, help="cloud-execution-lab root")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args(argv)
    try:
        report = build_report(args.root)
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError, zlib.error, json.JSONDecodeError) as exc:
        ap.exit(2, f"land-staging: {exc}\n")
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

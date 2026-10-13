#!/usr/bin/env python3
"""Source-bound census for main-farmer motion candidates in TITAN V4 tapes.

This module is research-only. It does not mutate tapes or runtime policy. Only
true out-of-bounds movement rows are engine-level PASS-equivalent. Closed motion
loops are open-loop candidates: their intermediate farmer positions are public
and can affect observation-conditioned agents before the route returns home.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import types
from pathlib import Path
from typing import Any

TURNS_PER_DAY = 24
ROUTE_STEP = 144
FINAL_PLAN_STEP = 648
LAST_STEP = 718
TAPE_COUNT = 13
TAPE_STEPS = LAST_STEP + 1
BOARD_SIZE = 10

EXPECTED_ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
EXPECTED_ENGINE_SPEC_BLOB = "b354d06b742fe48402513792253f1a5c29366b20"
EXPECTED_TAPES_BLOB = "a43289b9cc5e34a2481fddf652762a7d92f427ef"
EXPECTED_ROUTER_BLOB = "a3e2fe87c717d128e43c9b65bae2265f40d1d76d"

ENGINE_MARKERS = (
    'FARMER_MOVES = {',
    'if op in FARMER_MOVES:',
    '_set_farmer_position(farm, idx, (nx, ny))',
    'obs0.farms = farms',
    'state[i].observation.farms = farms',
    'if op == "HIRE":',
    '_do_hire(farms[player_id], privates[player_id], board_size, hire_mult)',
    'farm["hands"].append(_spawn_hand(farm, board_size))',
    'farm["farmer"] = list(_default_spawn(board_size))',
    'farm["hands"] = []',
    '_apply_unit_action(obs0.farms[i], s.observation.private, 0, _allowed(farmer_action),',
    '_process_market(state, env)',
)
ROUTER_MARKERS = (
    "ROUTE_STEP = 144",
    "FINAL_PLAN_STEP = 648",
    "LAST_STEP = 718",
    "state.plan = SHOP_PLANS.get(tuple(shops[:2]), 0)",
    "state.plan = 2",
    "tape = self.tapes[state.plan]",
    "action = copy.deepcopy(tape[step])",
)

MOVES = {
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
    "EAST": (1, 0),
    "WEST": (-1, 0),
}
PASSIVE = frozenset({"PASS", *MOVES})

HERE = Path(__file__).resolve()
V4_ROOT = HERE.parents[2]
TAPES_PATH = V4_ROOT / "donor" / "overlay" / "r01_tapes.py"
ROUTER_PATH = V4_ROOT / "donor" / "overlay" / "r04_full_router.py"
ENGINE_PATH = V4_ROOT.parent.parent / "reference" / "engine" / "kaggriculture.py"
ENGINE_SPEC_PATH = V4_ROOT.parent.parent / "reference" / "engine" / "kaggriculture.json"


class MotionCensusError(RuntimeError):
    pass


class VerifiedSources:
    __slots__ = ("source_blobs", "standard_configuration", "tapes_snapshot")

    def __init__(
        self,
        *,
        source_blobs: dict[str, str],
        standard_configuration: dict[str, int],
        tapes_snapshot: bytes,
    ) -> None:
        self.source_blobs = dict(source_blobs)
        self.standard_configuration = dict(standard_configuration)
        self.tapes_snapshot = tapes_snapshot


def _read_snapshot(path: Path) -> bytes:
    """Capture one immutable authority snapshot; callers must not reopen *path*."""
    return path.read_bytes()


def _git_blob_bytes(data: bytes) -> str:
    if not isinstance(data, bytes):
        raise TypeError("Git blob input must be bytes")
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def git_blob(path: Path) -> str:
    """Compatibility helper for diagnostics; source verification uses captured bytes."""
    return _git_blob_bytes(_read_snapshot(path))


def _decode_utf8(data: bytes, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MotionCensusError(f"{label} is not UTF-8") from exc


def _require_markers(text: str, markers: tuple[str, ...], label: str) -> None:
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise MotionCensusError(f"{label} semantics drifted; missing {missing!r}")


def _standard_configuration(spec_snapshot: bytes) -> dict[str, int]:
    try:
        doc = json.loads(_decode_utf8(spec_snapshot, "engine spec"))
    except json.JSONDecodeError as exc:
        raise MotionCensusError(f"engine spec is invalid JSON: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("configuration"), dict):
        raise MotionCensusError("engine spec configuration missing")
    cfg = doc["configuration"]
    expected = {"boardSize": BOARD_SIZE, "turnsPerDay": TURNS_PER_DAY}
    observed: dict[str, int] = {}
    for name, want in expected.items():
        entry = cfg.get(name)
        if not isinstance(entry, dict):
            raise MotionCensusError(f"engine spec {name} contract missing")
        value = entry.get("default")
        if type(value) is not int or value != want:
            raise MotionCensusError(
                f"engine spec {name} default drift: expected {want}, got {value!r}"
            )
        if entry.get("type") != "integer":
            raise MotionCensusError(f"engine spec {name} type drift")
        minimum = entry.get("minimum")
        if type(minimum) is not int or minimum <= 0:
            raise MotionCensusError(f"engine spec {name} minimum contract drift")
        observed[name] = value
    return observed


def verify_sources(
    *,
    engine_path: Path = ENGINE_PATH,
    engine_spec_path: Path = ENGINE_SPEC_PATH,
    tapes_path: Path = TAPES_PATH,
    router_path: Path = ROUTER_PATH,
) -> VerifiedSources:
    # Capture every authority once. All identity and semantic checks below are
    # derived from these exact bytes, never from a second pathname read.
    snapshots = {
        "engine_blob": _read_snapshot(engine_path),
        "engine_spec_blob": _read_snapshot(engine_spec_path),
        "r01_tapes_blob": _read_snapshot(tapes_path),
        "r04_full_router_blob": _read_snapshot(router_path),
    }
    actual = {key: _git_blob_bytes(data) for key, data in snapshots.items()}
    expected = {
        "engine_blob": EXPECTED_ENGINE_BLOB,
        "engine_spec_blob": EXPECTED_ENGINE_SPEC_BLOB,
        "r01_tapes_blob": EXPECTED_TAPES_BLOB,
        "r04_full_router_blob": EXPECTED_ROUTER_BLOB,
    }
    for key, want in expected.items():
        if actual[key] != want:
            raise MotionCensusError(
                f"{key} drift: expected {want}, got {actual[key]}"
            )

    _require_markers(
        _decode_utf8(snapshots["engine_blob"], "engine"),
        ENGINE_MARKERS,
        "engine",
    )
    _require_markers(
        _decode_utf8(snapshots["r04_full_router_blob"], "router"),
        ROUTER_MARKERS,
        "router",
    )
    standard = _standard_configuration(snapshots["engine_spec_blob"])
    return VerifiedSources(
        source_blobs=actual,
        standard_configuration=standard,
        tapes_snapshot=snapshots["r01_tapes_blob"],
    )


def _load_module_snapshot(source: bytes, source_path: Path):
    if not isinstance(source, bytes):
        raise TypeError("module snapshot must be bytes")
    module = types.ModuleType("_titan_v4_motion_tapes")
    module.__file__ = str(source_path)
    module.__package__ = None
    code = compile(source, str(source_path), "exec")
    exec(code, module.__dict__)
    return module


def load_tapes(
    path: Path = TAPES_PATH,
    *,
    snapshot: bytes | None = None,
) -> list[list[dict[str, Any]]]:
    # Authoritative callers pass verify_sources().tapes_snapshot so path drift
    # after authentication cannot change the executed tape bank.
    source = _read_snapshot(path) if snapshot is None else snapshot
    tapes = _load_module_snapshot(source, path).load_tapes()
    if len(tapes) != TAPE_COUNT or any(len(tape) != TAPE_STEPS for tape in tapes):
        raise MotionCensusError(
            f"expected {TAPE_COUNT}x{TAPE_STEPS} tapes, got "
            f"{len(tapes)} / {[len(t) for t in tapes[:3]]}"
        )
    return tapes


def effective_route(tapes: list[list[dict[str, Any]]], plan: int) -> list[dict[str, Any]]:
    if not 0 <= plan < TAPE_COUNT:
        raise MotionCensusError(f"plan out of range: {plan}")
    if len(tapes) != TAPE_COUNT or any(len(tape) != TAPE_STEPS for tape in tapes):
        raise MotionCensusError("malformed tape bank")
    return (
        tapes[0][:ROUTE_STEP]
        + tapes[plan][ROUTE_STEP:FINAL_PLAN_STEP]
        + tapes[2][FINAL_PLAN_STEP:]
    )


def _default_spawn(board_size: int = BOARD_SIZE) -> tuple[int, int]:
    half = board_size // 2
    candidates = (
        (half - 1, half - 1),
        (half, half - 1),
        (half - 1, half),
        (half, half),
    )
    for x, y in candidates:
        if x < half and y < half:
            return x, y
    return 0, 0


def _farmer_row(action: Any) -> list[Any]:
    if not isinstance(action, dict):
        return ["PASS"]
    row = action.get("farmer") or ["PASS"]
    return row if isinstance(row, list) and row else ["PASS"]


def _op(action: Any) -> str:
    row = _farmer_row(action)
    return str(row[0]) if row else "PASS"


def _has_hire(action: Any) -> bool:
    if not isinstance(action, dict):
        return False
    market = action.get("market") or []
    if not isinstance(market, list):
        return False
    return any(
        isinstance(row, list) and row and row[0] == "HIRE"
        for row in market
    )


def _move(pos: tuple[int, int], op: str, board_size: int) -> tuple[tuple[int, int], bool]:
    delta = MOVES.get(op)
    if delta is None:
        return pos, False
    nx, ny = pos[0] + delta[0], pos[1] + delta[1]
    if not (0 <= nx < board_size and 0 <= ny < board_size):
        return pos, False
    return (nx, ny), True


def census_route(
    route: list[dict[str, Any]],
    *,
    plan: int = -1,
    board_size: int = BOARD_SIZE,
    turns_per_day: int = TURNS_PER_DAY,
) -> dict[str, Any]:
    """Find boundary no-ops and open-loop position-restoring motion candidates.

    Boundary movement no-ops are individually engine-level PASS-equivalent.
    Closed MOVE/PASS-only, HIRE-free intervals are only *candidate groups*: the
    fixed authored route returns actor 0 to the same tile, but intermediate
    farmer positions are public observations. Observation-conditioned wrappers
    or opponents may react before the loop closes, so this census grants no
    closed-loop rewrite authority. Such groups require current-native replay.
    """
    if type(board_size) is not int or type(turns_per_day) is not int:
        raise MotionCensusError("plain-integer board_size/turns_per_day required")
    if board_size <= 0 or turns_per_day <= 0:
        raise MotionCensusError("positive board_size/turns_per_day required")

    pos = _default_spawn(board_size)
    seen: dict[tuple[int, int], int] = {pos: 0}
    move_prefix = [0]
    intervals: list[dict[str, Any]] = []
    boundary_noops: list[int] = []
    movement_rows = 0
    hire_rows = 0

    for step, action in enumerate(route):
        if step > 0 and step % turns_per_day == 0:
            pos = _default_spawn(board_size)
            seen = {pos: step}

        op = _op(action)
        has_hire = _has_hire(action)
        if has_hire:
            hire_rows += 1

        after, executed = _move(pos, op, board_size)
        if op in MOVES:
            movement_rows += 1
            if not executed:
                boundary_noops.append(step)
        pos = after
        move_prefix.append(move_prefix[-1] + int(executed))

        if op not in PASSIVE or has_hire:
            seen = {pos: step + 1}
            continue

        prior_boundary = seen.get(pos)
        if prior_boundary is not None:
            executed_moves = move_prefix[step + 1] - move_prefix[prior_boundary]
            if executed_moves > 0:
                interval_moves = [
                    idx
                    for idx in range(prior_boundary, step + 1)
                    if _op(route[idx]) in MOVES
                ]
                intervals.append(
                    {
                        "start_step": prior_boundary,
                        "end_step": step,
                        "day": step // turns_per_day,
                        "position": [pos[0], pos[1]],
                        "movement_rows": interval_moves,
                        "movement_row_count": len(interval_moves),
                        "executed_move_count": executed_moves,
                        "classification": "OPEN_LOOP_REPLAY_REQUIRED",
                    }
                )
                seen = {pos: step + 1}
                continue

        seen[pos] = step + 1

    loop_rows = sorted(
        {idx for interval in intervals for idx in interval["movement_rows"]}
    )
    return {
        "plan": plan,
        "steps": len(route),
        "movement_rows": movement_rows,
        "hire_market_rows": hire_rows,
        "boundary_noop_rows": boundary_noops,
        "open_loop_closed_motion_candidates": intervals,
        "open_loop_candidate_count": len(intervals),
        "open_loop_candidate_movement_rows": loop_rows,
        "open_loop_candidate_movement_count": len(loop_rows),
        "individually_pass_equivalent_movement_rows": boundary_noops,
        "individually_pass_equivalent_count": len(boundary_noops),
    }


def build_report(
    tapes: list[list[dict[str, Any]]],
    sources: VerifiedSources,
) -> dict[str, Any]:
    board_size = sources.standard_configuration["boardSize"]
    turns_per_day = sources.standard_configuration["turnsPerDay"]
    routes = [
        census_route(
            effective_route(tapes, plan),
            plan=plan,
            board_size=board_size,
            turns_per_day=turns_per_day,
        )
        for plan in range(TAPE_COUNT)
    ]
    return {
        "schema": "titan.v4.route-motion-census.v3",
        "status": "SOURCE_BOUND_RESEARCH_ONLY",
        "sources": sources.source_blobs,
        "standard_configuration": dict(sources.standard_configuration),
        "theorem": {
            "scope": "main farmer actor 0 only; fixed effective routes",
            "safe_rewrite": (
                "only out-of-bounds movement rows are individually engine-level "
                "PASS-equivalent"
            ),
            "closed_loop_status": (
                "OPEN_LOOP_REPLAY_REQUIRED: returning to the same tile does not "
                "authorize a rewrite because intermediate farmer positions are "
                "shared public observations visible to both agents"
            ),
            "guards": [
                "authenticated standard boardSize=10 and turnsPerDay=24",
                "same day only for closed-loop candidate grouping",
                "no substantive main-farmer unit action inside candidate loop",
                "no HIRE market row inside candidate loop",
                "exact actor-0 position returns to candidate-loop start",
                "out-of-bounds movement is already a unit no-op",
                "both players share the public farms object in observation state",
            ],
        },
        "route_splice": {
            "opening": [0, ROUTE_STEP - 1, 0],
            "midgame": [ROUTE_STEP, FINAL_PLAN_STEP - 1, "plan"],
            "endgame": [FINAL_PLAN_STEP, LAST_STEP, 2],
        },
        "routes": routes,
        "totals": {
            "movement_rows": sum(r["movement_rows"] for r in routes),
            "open_loop_candidate_count": sum(
                r["open_loop_candidate_count"] for r in routes
            ),
            "individually_pass_equivalent_count": sum(
                r["individually_pass_equivalent_count"] for r in routes
            ),
            "open_loop_candidate_movement_count": sum(
                r["open_loop_candidate_movement_count"] for r in routes
            ),
            "routes_with_boundary_noop_rewrites": sum(
                bool(r["individually_pass_equivalent_count"]) for r in routes
            ),
            "routes_with_open_loop_candidates": sum(
                bool(r["open_loop_candidate_count"]) for r in routes
            ),
        },
        "not_claimed": [
            "closed-loop PASS equivalence under observation-conditioned agents or opponents",
            "closed-loop rewrite authority before current-native replay",
            "hand/worker motion optimality",
            "natural current-native incidence after all runtime repairs",
            "economic uplift",
            "runtime activation",
            "default promotion",
            "archive or Kaggle mutation",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    sources = verify_sources()
    tapes = load_tapes(snapshot=sources.tapes_snapshot)
    report = build_report(tapes, sources)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

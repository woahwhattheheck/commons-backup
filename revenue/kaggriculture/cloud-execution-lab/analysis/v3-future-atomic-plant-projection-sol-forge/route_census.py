#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound census of repeated same-crop PLANT packets in current Arlene routes.

The census is static reachability evidence only.  A repeated same-crop packet is a
necessary route precondition for the future sequential/atomic mismatch, not proof
that live seed stock is insufficient or that a returned action changes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
DEFAULT_SOURCE = LAB / "reference" / "next-panel" / "vendor" / "arlene.py"
ARLENE_GIT_BLOB = "bdb9cf58148a3c7961c085f4902759537decabf6"
VERIFIED_MAIN = "2e2e7e52fd2d5c62117ac49c7f1eabb505078ffb"
SCHEMA = "titan-v3-future-atomic-plant-route-census-v1"


class CensusError(RuntimeError):
    """The source or route bank is malformed or detached from the bound bytes."""


def git_blob(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CensusError(f"route row is not strict JSON: {exc}") from exc


def unit_actions(row: Mapping[str, Any]) -> list[Any]:
    """Mirror the official interpreter's farmer+hands packet extraction."""
    farmer = row.get("farmer", ["PASS"])
    hands = row.get("hands", [])
    if not isinstance(hands, list):
        hands = []
    return [farmer, *hands]


def census_routes(routes: Mapping[Any, Sequence[Any]]) -> dict[str, Any]:
    if not isinstance(routes, Mapping) or not routes:
        raise CensusError("route bank is absent or not a nonempty mapping")

    rows: list[dict[str, Any]] = []
    lengths: dict[str, int] = {}
    crop_rows: Counter[str] = Counter()
    packet_demands: Counter[int] = Counter()

    for route_id, route in sorted(routes.items(), key=lambda item: str(item[0])):
        route_name = str(route_id)
        if not isinstance(route, (list, tuple)):
            raise CensusError(f"route {route_name!r} is not a sequence")
        lengths[route_name] = len(route)
        for step, row in enumerate(route):
            if not isinstance(row, Mapping):
                raise CensusError(
                    f"route {route_name!r} step {step} is not a mapping"
                )
            counts: Counter[str] = Counter()
            actors: dict[str, list[int]] = {}
            for actor, action in enumerate(unit_actions(row)):
                if (
                    isinstance(action, list)
                    and len(action) >= 2
                    and action[0] == "PLANT"
                    and isinstance(action[1], str)
                ):
                    crop = action[1]
                    counts[crop] += 1
                    actors.setdefault(crop, []).append(actor)
            for crop, demand in sorted(counts.items()):
                if demand < 2:
                    continue
                crop_rows[crop] += 1
                packet_demands[demand] += 1
                rows.append(
                    {
                        "route_id": route_name,
                        "step": step,
                        "crop": crop,
                        "demand": demand,
                        "actors": actors[crop],
                        "row_sha256": sha256(canonical_json(row)),
                    }
                )

    rows.sort(key=lambda item: (item["route_id"], item["step"], item["crop"]))
    disposition = "ROUTE_RISK" if rows else "DORMANT"
    return {
        "route_count": len(routes),
        "route_lengths": lengths,
        "repeated_same_crop_plant_rows": rows,
        "repeated_row_count": len(rows),
        "rows_by_crop": dict(sorted(crop_rows.items())),
        "rows_by_packet_demand": {
            str(demand): count for demand, count in sorted(packet_demands.items())
        },
        "disposition": disposition,
        "interpretation": (
            "necessary route precondition exists; live observation/seed-state and "
            "returned-action activation remain unmeasured"
            if rows
            else "current route bank contains no repeated same-crop PLANT packet"
        ),
    }


def load_routes(source: Path) -> Mapping[Any, Sequence[Any]]:
    source = Path(source)
    raw = source.read_bytes()
    actual = git_blob(raw)
    if actual != ARLENE_GIT_BLOB:
        raise CensusError(
            f"Arlene source drift: expected {ARLENE_GIT_BLOB}, got {actual}"
        )
    name = "_sol_forge_bound_arlene"
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise CensusError(f"cannot load source: {source}")
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(name)
    try:
        sys.modules[name] = module
        spec.loader.exec_module(module)
        agent_type = getattr(module, "Agent", None)
        if not callable(agent_type):
            raise CensusError("bound Arlene source has no callable Agent")
        routes = getattr(agent_type(), "R", None)
        if not isinstance(routes, Mapping):
            raise CensusError("bound Arlene Agent has no route mapping R")
        return routes
    except CensusError:
        raise
    except BaseException as exc:
        raise CensusError(
            f"bound Arlene construction failed: {type(exc).__name__}: {exc}"
        ) from exc
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def build_report(source: Path) -> dict[str, Any]:
    source = Path(source)
    raw = source.read_bytes()
    census = census_routes(load_routes(source))
    return {
        "schema": SCHEMA,
        "operation": "TITAN-V3-FUTURE-ATOMIC-PLANT-PROJECTION-20260910-01",
        "verified_main": VERIFIED_MAIN,
        "source": {
            "path": str(source),
            "bytes": len(raw),
            "git_blob": git_blob(raw),
            "sha256": sha256(raw),
        },
        "route_census": census,
        "disposition": census["disposition"],
        "score_claim": False,
        "canonical_mutation_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_report(args.source)
    except (CensusError, OSError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

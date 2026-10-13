#!/usr/bin/env python3
"""TITAN V5 P04: reduce step-144 route-matrix rows using observation-only features.

This is deliberately *not* a route-forcing harness and *not* a runtime selector.
It consumes immutable R00..R12 rows emitted by the shared route-matrix carrier,
checks that every forced-plan comparison shares the same pre-selection public
snapshot, and emits source-grounded discovery diagnostics. Any runtime selector
still requires fresh held-out native games.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "titan-v5-p04-route-ranker/v1"
PRODUCTION_ARCHIVE_SHA256 = "20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239"
ROUTER_SOURCE_SHA256 = "41ea55c5f20c43cd58c5099fbadb212de62ec95a95dfc2e6e1e19c3d4d55b39a"
SOURCE_CENSUS_COMMIT = "93c9fefa83868d108139e8367d4b99ba6e39dd73"
ROUTE_STEP = 144
FINAL_PLAN_STEP = 648
ALL_PLANS = tuple(range(13))
NATURAL_STEP144_PLANS = (0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)

SHOP_PLANS = {
    ("BAKERY", "YARN_STORE"): 3,
    ("BRUNCH_SPOT", "YARN_STORE"): 4,
    ("FARMERS_MARKET", "YARN_STORE"): 5,
    ("ICE_CREAM_SHOP", "YARN_STORE"): 6,
    ("PET_CAFE", "YARN_STORE"): 5,
    ("PIZZA_SHOP", "YARN_STORE"): 7,
    ("SMOOTHIE_SHOP", "YARN_STORE"): 8,
    ("YARN_STORE", "BAKERY"): 9,
    ("YARN_STORE", "BRUNCH_SPOT"): 9,
    ("YARN_STORE", "FARMERS_MARKET"): 1,
    ("YARN_STORE", "ICE_CREAM_SHOP"): 9,
    ("YARN_STORE", "PET_CAFE"): 10,
    ("YARN_STORE", "PIZZA_SHOP"): 6,
    ("YARN_STORE", "SMOOTHIE_SHOP"): 11,
    ("YARN_STORE", "YARN_STORE"): 12,
}

PLAN_ARCHETYPES = {
    0: {"crop": "W146-C31-S29", "animal": "COW4-SHEEP4-GOOSE3"},
    1: {"crop": "W146-C31-S29", "animal": "COW2-SHEEP8"},
    2: {"crop": "TERMINAL-DIAGNOSTIC", "animal": "TERMINAL-DIAGNOSTIC"},
    3: {"crop": "W146-C31-S29", "animal": "COW2-SHEEP9"},
    4: {"crop": "W146-C31-S29", "animal": "COW2-SHEEP8"},
    5: {"crop": "W146-C31-S29", "animal": "COW2-SHEEP8"},
    6: {"crop": "W146-C31-S29", "animal": "COW2-SHEEP9"},
    7: {"crop": "W146-C31-S29", "animal": "COW2-SHEEP9"},
    8: {"crop": "W146-C31-S29", "animal": "COW2-SHEEP9"},
    9: {"crop": "W148-C28-S29", "animal": "COW2-SHEEP9"},
    10: {"crop": "W146-C31-S29", "animal": "COW2-SHEEP9"},
    11: {"crop": "W146-C31-S29", "animal": "COW2-SHEEP9"},
    12: {"crop": "W148-C28-S29", "animal": "SHEEP12"},
}

_SNAPSHOT_KEYS = {"first_two_shops", "market", "own", "rival", "incumbent_plan"}
_MARKET_KEYS = {"prices", "inventory"}
_OWN_KEYS = {"cash", "worker_count", "animal_counts", "crop_counts"}
_RIVAL_KEYS = {"animal_counts", "crop_counts"}
_FORBIDDEN_TOP_LEVEL = {
    "rng_state", "future_rng", "future_town", "future_shops", "future_observation",
    "rival_shed", "rival_inventory", "rival_private_inventory", "opponent_inventory",
}


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _count_map(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    out: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{label} keys must be nonempty strings")
        out[key] = _nonnegative_int(count, f"{label}.{key}")
    return dict(sorted(out.items()))


def _number_map(value: Any, label: str, *, integer: bool) -> dict[str, float | int]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    out: dict[str, float | int] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{label} keys must be nonempty strings")
        if integer:
            out[key] = _nonnegative_int(raw, f"{label}.{key}")
        else:
            number = _finite_number(raw, f"{label}.{key}")
            if number < 0:
                raise ValueError(f"{label}.{key} must be nonnegative")
            out[key] = number
    return dict(sorted(out.items()))


def expected_incumbent_plan(first_two_shops: Iterable[str]) -> int:
    pair = tuple(first_two_shops)
    if len(pair) != 2 or not all(isinstance(x, str) and x for x in pair):
        raise ValueError("first_two_shops must contain exactly two shop names")
    return SHOP_PLANS.get(pair, 0)


def canonical_public_snapshot(snapshot: Any) -> dict[str, Any]:
    """Strictly normalize the P04 public snapshot and reject hidden/future fields."""
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be an object")
    if set(snapshot) != _SNAPSHOT_KEYS:
        missing = sorted(_SNAPSHOT_KEYS - set(snapshot))
        extra = sorted(set(snapshot) - _SNAPSHOT_KEYS)
        raise ValueError(f"snapshot keys mismatch: missing={missing} extra={extra}")

    shops = snapshot["first_two_shops"]
    if not isinstance(shops, (list, tuple)) or len(shops) != 2:
        raise ValueError("snapshot.first_two_shops must have exactly two entries")
    if not all(isinstance(x, str) and x for x in shops):
        raise ValueError("snapshot.first_two_shops entries must be nonempty strings")

    market = snapshot["market"]
    own = snapshot["own"]
    rival = snapshot["rival"]
    if not isinstance(market, dict) or set(market) != _MARKET_KEYS:
        raise ValueError("snapshot.market must contain only prices and inventory")
    if not isinstance(own, dict) or set(own) != _OWN_KEYS:
        raise ValueError("snapshot.own contains non-public or missing fields")
    if not isinstance(rival, dict) or set(rival) != _RIVAL_KEYS:
        raise ValueError("snapshot.rival contains non-public or missing fields")

    incumbent = snapshot["incumbent_plan"]
    if isinstance(incumbent, bool) or not isinstance(incumbent, int) or incumbent not in ALL_PLANS:
        raise ValueError("snapshot.incumbent_plan must be an integer plan index 0..12")
    expected = expected_incumbent_plan(shops)
    if incumbent != expected:
        raise ValueError(f"incumbent plan mismatch: snapshot={incumbent} source={expected}")

    cash = _finite_number(own["cash"], "snapshot.own.cash")
    workers = _nonnegative_int(own["worker_count"], "snapshot.own.worker_count")
    return {
        "first_two_shops": list(shops),
        "market": {
            "prices": _number_map(market["prices"], "snapshot.market.prices", integer=False),
            "inventory": _number_map(market["inventory"], "snapshot.market.inventory", integer=True),
        },
        "own": {
            "cash": cash,
            "worker_count": workers,
            "animal_counts": _count_map(own["animal_counts"], "snapshot.own.animal_counts"),
            "crop_counts": _count_map(own["crop_counts"], "snapshot.own.crop_counts"),
        },
        "rival": {
            "animal_counts": _count_map(rival["animal_counts"], "snapshot.rival.animal_counts"),
            "crop_counts": _count_map(rival["crop_counts"], "snapshot.rival.crop_counts"),
        },
        "incumbent_plan": incumbent,
    }


def snapshot_sha256(snapshot: Any) -> str:
    canonical = canonical_public_snapshot(snapshot)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _cmp_feature(mapping: dict[str, float | int], left: str, right: str) -> str:
    if left not in mapping or right not in mapping:
        return "MISSING"
    a, b = mapping[left], mapping[right]
    if a > b:
        return f"{left}>{right}"
    if a < b:
        return f"{left}<{right}"
    return f"{left}={right}"


def _leader(counts: dict[str, int]) -> str:
    if not counts:
        return "NONE"
    maximum = max(counts.values())
    leaders = sorted(key for key, value in counts.items() if value == maximum)
    if maximum == 0:
        return "NONE"
    return "+".join(leaders)


def public_feature_signature(snapshot: Any) -> dict[str, Any]:
    s = canonical_public_snapshot(snapshot)
    shops = s["first_two_shops"]
    prices = s["market"]["prices"]
    inventory = s["market"]["inventory"]
    return {
        "shop_pair": "|".join(shops),
        "first_two_yarn_count": sum(shop == "YARN_STORE" for shop in shops),
        "wool_vs_milk_price": _cmp_feature(prices, "WOOL", "MILK"),
        "wool_vs_milk_inventory": _cmp_feature(inventory, "WOOL", "MILK"),
        "wheat_vs_carrot_price": _cmp_feature(prices, "WHEAT", "CARROT"),
        "rival_livestock_leader": _leader(s["rival"]["animal_counts"]),
        "rival_crop_leader": _leader(s["rival"]["crop_counts"]),
    }


def source_archetype(plan: int) -> dict[str, Any]:
    if isinstance(plan, bool) or not isinstance(plan, int) or plan not in ALL_PLANS:
        raise ValueError("plan must be 0..12")
    return {
        "plan": plan,
        **PLAN_ARCHETYPES[plan],
        "natural_step144": plan in NATURAL_STEP144_PLANS,
    }


def normalize_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("matrix row must be an object")
    bad = sorted(_FORBIDDEN_TOP_LEVEL & set(row))
    if bad:
        raise ValueError(f"forbidden hidden/future fields present: {bad}")
    required = {
        "seed", "opponent", "seat", "forced_plan", "snapshot", "snapshot_sha256",
        "terminal_own", "terminal_rival", "terminal_margin", "failures",
    }
    missing = sorted(required - set(row))
    if missing:
        raise ValueError(f"matrix row missing fields: {missing}")

    seed = row["seed"]
    seat = row["seat"]
    plan = row["forced_plan"]
    opponent = row["opponent"]
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if seat not in (0, 1) or isinstance(seat, bool):
        raise ValueError("seat must be literal 0 or 1")
    if isinstance(plan, bool) or not isinstance(plan, int) or plan not in ALL_PLANS:
        raise ValueError("forced_plan must be 0..12")
    if not isinstance(opponent, str) or not opponent:
        raise ValueError("opponent must be a nonempty string")

    snapshot = canonical_public_snapshot(row["snapshot"])
    digest = snapshot_sha256(snapshot)
    if row["snapshot_sha256"] != digest:
        raise ValueError("snapshot_sha256 does not bind canonical public snapshot")

    own = _finite_number(row["terminal_own"], "terminal_own")
    rival = _finite_number(row["terminal_rival"], "terminal_rival")
    margin = _finite_number(row["terminal_margin"], "terminal_margin")
    if not math.isclose(margin, own - rival, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("terminal_margin must equal terminal_own - terminal_rival")

    failures = row["failures"]
    if failures is None:
        failures = []
    if not isinstance(failures, list) or not all(isinstance(x, str) for x in failures):
        raise ValueError("failures must be a list of strings")

    return {
        "seed": seed,
        "opponent": opponent,
        "seat": seat,
        "forced_plan": plan,
        "snapshot": snapshot,
        "snapshot_sha256": digest,
        "terminal_own": own,
        "terminal_rival": rival,
        "terminal_margin": margin,
        "failures": list(failures),
    }


def _outcome_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (bool(row["failures"]), -row["terminal_margin"], -row["terminal_own"], row["forced_plan"])


def reduce_matrix(rows: Iterable[Any]) -> dict[str, Any]:
    normalized = [normalize_row(row) for row in rows]
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        key = (row["seed"], row["opponent"], row["seat"], row["snapshot_sha256"])
        groups[key].append(row)

    reduced_groups = []
    for key in sorted(groups):
        group = groups[key]
        plans = [row["forced_plan"] for row in group]
        if len(plans) != len(set(plans)):
            raise ValueError(f"duplicate forced plan in group {key[:3]}")
        if set(plans) != set(ALL_PLANS):
            missing = sorted(set(ALL_PLANS) - set(plans))
            extra = sorted(set(plans) - set(ALL_PLANS))
            raise ValueError(f"incomplete route matrix group {key[:3]}: missing={missing} extra={extra}")
        snapshots = {json.dumps(row["snapshot"], sort_keys=True, separators=(",", ":")) for row in group}
        if len(snapshots) != 1:
            raise ValueError(f"forced plans do not share one pre-step144 snapshot in group {key[:3]}")

        by_plan = {row["forced_plan"]: row for row in group}
        incumbent_plan = group[0]["snapshot"]["incumbent_plan"]
        incumbent = by_plan[incumbent_plan]
        ranking = sorted(group, key=_outcome_sort_key)
        best = ranking[0]
        plan_rows = []
        for row in sorted(group, key=lambda x: x["forced_plan"]):
            plan_rows.append({
                "plan": row["forced_plan"],
                "archetype": source_archetype(row["forced_plan"]),
                "terminal_own": row["terminal_own"],
                "terminal_rival": row["terminal_rival"],
                "terminal_margin": row["terminal_margin"],
                "delta_own_vs_incumbent": row["terminal_own"] - incumbent["terminal_own"],
                "delta_margin_vs_incumbent": row["terminal_margin"] - incumbent["terminal_margin"],
                "failures": row["failures"],
            })
        reduced_groups.append({
            "seed": key[0],
            "opponent": key[1],
            "seat": key[2],
            "snapshot_sha256": key[3],
            "features": public_feature_signature(group[0]["snapshot"]),
            "incumbent_plan": incumbent_plan,
            "best_plan": best["forced_plan"],
            "best_is_natural_step144": best["forced_plan"] in NATURAL_STEP144_PLANS,
            "incumbent_regret_margin": best["terminal_margin"] - incumbent["terminal_margin"],
            "incumbent_regret_own": best["terminal_own"] - incumbent["terminal_own"],
            "plans": plan_rows,
        })

    per_plan: dict[int, dict[str, list[float] | int]] = {
        plan: {"dm": [], "do": [], "failures": 0} for plan in ALL_PLANS
    }
    for group in reduced_groups:
        for row in group["plans"]:
            state = per_plan[row["plan"]]
            state["dm"].append(row["delta_margin_vs_incumbent"])
            state["do"].append(row["delta_own_vs_incumbent"])
            state["failures"] += int(bool(row["failures"]))

    aggregate = []
    for plan in ALL_PLANS:
        dm = list(per_plan[plan]["dm"])
        do = list(per_plan[plan]["do"])
        if not dm:
            continue
        aggregate.append({
            "plan": plan,
            "archetype": source_archetype(plan),
            "groups": len(dm),
            "mean_delta_margin_vs_incumbent": statistics.fmean(dm),
            "median_delta_margin_vs_incumbent": statistics.median(dm),
            "min_delta_margin_vs_incumbent": min(dm),
            "max_delta_margin_vs_incumbent": max(dm),
            "mean_delta_own_vs_incumbent": statistics.fmean(do),
            "min_delta_own_vs_incumbent": min(do),
            "failure_groups": per_plan[plan]["failures"],
            "margin_better_groups": sum(x > 0 for x in dm),
            "margin_tied_groups": sum(x == 0 for x in dm),
            "margin_worse_groups": sum(x < 0 for x in dm),
        })

    feature_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for group in reduced_groups:
        signature = json.dumps(group["features"], sort_keys=True, separators=(",", ":"))
        feature_groups[signature].append(group)
    strata = []
    for signature, stratum_groups in sorted(feature_groups.items()):
        winner_counts: dict[int, int] = defaultdict(int)
        regrets = []
        for group in stratum_groups:
            winner_counts[group["best_plan"]] += 1
            regrets.append(group["incumbent_regret_margin"])
        strata.append({
            "features": json.loads(signature),
            "groups": len(stratum_groups),
            "best_plan_counts": {str(k): v for k, v in sorted(winner_counts.items())},
            "mean_incumbent_regret_margin": statistics.fmean(regrets),
        })

    return {
        "schema": SCHEMA,
        "authority": {
            "production_archive_sha256": PRODUCTION_ARCHIVE_SHA256,
            "router_source_sha256": ROUTER_SOURCE_SHA256,
            "source_census_commit": SOURCE_CENSUS_COMMIT,
            "route_step": ROUTE_STEP,
            "forced_terminal_plan_step": FINAL_PLAN_STEP,
        },
        "complete_snapshot_groups": len(reduced_groups),
        "groups": reduced_groups,
        "aggregate_by_plan": aggregate,
        "observable_feature_strata": strata,
        "policy_ready": False,
        "policy_hold_reason": (
            "R00-R12 is a discovery matrix. A runtime selector requires a predeclared low-complexity "
            "rule derived from these observation-only features plus fresh held-out native games; no "
            "training-matrix fit can authorize activation by itself."
        ),
    }


def load_jsonl(path: Path) -> list[Any]:
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on line {lineno}: {exc}") from exc
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path, help="Shared route-matrix JSONL rows")
    parser.add_argument("--output", type=Path, help="Write canonical report JSON; stdout otherwise")
    args = parser.parse_args()
    report = reduce_matrix(load_jsonl(args.jsonl))
    payload = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            parser.error("refusing to overwrite an existing output")
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()

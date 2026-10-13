#!/usr/bin/env python3
"""Reproduce the TITAN V4 S5 PET_CAFE-first carrot residual from the V3.1 leader ledger.

Input is the `ledger_v31_vs_leaders.json` file from the 2026-09-11
"Kaggriculture leaders pull v3 (adds V3.1 vs leaders)" bundle.

This script is analysis-only. It does not modify a policy or run the game engine.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from statistics import mean
from typing import Callable, Iterable

SEED_COST = {
    "WHEAT": 10.0,
    "CARROT": 20.0,
    "TOMATO": 50.0,
    "STRAWBERRY": 100.0,
    "MELON": 80.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path, help="path to ledger_v31_vs_leaders.json")
    parser.add_argument(
        "--min-cells-per-arm",
        type=int,
        default=2,
        help="minimum PET/non-PET (or PIZZA/non-PIZZA) cells per leader for within-leader controls",
    )
    return parser.parse_args()


def load_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        rows = json.load(fh)
    if not isinstance(rows, list):
        raise SystemExit("ledger root must be a JSON list")
    required = {"leader", "leader_seat", "cand_seat", "shops", "seats"}
    for i, row in enumerate(rows):
        missing = required - row.keys()
        if missing:
            raise SystemExit(f"row {i} missing keys: {sorted(missing)}")
    return rows


def seat(row: dict, leader: bool) -> dict:
    index = row["leader_seat"] if leader else row["cand_seat"]
    return row["seats"][index]


def seed_units(seat_data: dict, crop: str) -> float:
    spend = float(seat_data.get("spend", {}).get(f"BUY_SEED {crop}", 0.0))
    return spend / SEED_COST[crop]


def revenue(seat_data: dict, crop: str) -> float:
    return float(seat_data.get("coins", {}).get(crop, 0.0))


def produced_units(seat_data: dict, crop: str) -> float:
    return float(seat_data.get("units", {}).get(crop, 0.0))


def final_score(seat_data: dict) -> float:
    return float(seat_data["final"])


def delta(row: dict, metric: Callable[[dict], float]) -> float:
    return metric(seat(row, True)) - metric(seat(row, False))


def leader_margin(row: dict) -> float:
    return delta(row, final_score)


def candidate_lost(row: dict) -> bool:
    return leader_margin(row) > 0.0


def avg(values: Iterable[float]) -> float:
    values = list(values)
    return mean(values) if values else float("nan")


def summary(rows: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {
        "n": len(rows),
        "candidate_losses": sum(candidate_lost(row) for row in rows),
        "loss_rate": avg(float(candidate_lost(row)) for row in rows),
        "leader_margin": avg(leader_margin(row) for row in rows),
    }
    for crop in SEED_COST:
        out[f"seed_gap_{crop}"] = avg(
            delta(row, lambda s, crop=crop: seed_units(s, crop)) for row in rows
        )
        out[f"revenue_gap_{crop}"] = avg(
            delta(row, lambda s, crop=crop: revenue(s, crop)) for row in rows
        )
        out[f"unit_gap_{crop}"] = avg(
            delta(row, lambda s, crop=crop: produced_units(s, crop)) for row in rows
        )
    return out


def first_shop(row: dict) -> str | None:
    shops = row.get("shops") or []
    return shops[0] if shops else None


def within_leader_control(
    rows: list[dict],
    target_shop: str,
    crop: str,
    min_cells_per_arm: int,
) -> tuple[list[dict], dict[str, float]]:
    grouped: dict[str, tuple[list[dict], list[dict]]] = collections.defaultdict(
        lambda: ([], [])
    )
    for row in rows:
        target, other = grouped[row["leader"]]
        (target if first_shop(row) == target_shop else other).append(row)

    leader_rows: list[dict] = []
    for leader, (target, other) in grouped.items():
        if len(target) < min_cells_per_arm or len(other) < min_cells_per_arm:
            continue
        leader_rows.append(
            {
                "leader": leader,
                "target_cells": len(target),
                "other_cells": len(other),
                "margin_shift": avg(leader_margin(r) for r in target)
                - avg(leader_margin(r) for r in other),
                "seed_gap_shift": avg(
                    delta(r, lambda s: seed_units(s, crop)) for r in target
                )
                - avg(delta(r, lambda s: seed_units(s, crop)) for r in other),
                "revenue_gap_shift": avg(
                    delta(r, lambda s: revenue(s, crop)) for r in target
                )
                - avg(delta(r, lambda s: revenue(s, crop)) for r in other),
            }
        )

    aggregate = {
        "eligible_leaders": len(leader_rows),
        "mean_margin_shift": avg(row["margin_shift"] for row in leader_rows),
        "mean_seed_gap_shift": avg(row["seed_gap_shift"] for row in leader_rows),
        "mean_revenue_gap_shift": avg(row["revenue_gap_shift"] for row in leader_rows),
    }
    return leader_rows, aggregate


def print_group(label: str, stats: dict[str, float], crops: tuple[str, ...]) -> None:
    print(f"\n[{label}]")
    print(
        f"n={int(stats['n'])} candidate_losses={int(stats['candidate_losses'])} "
        f"loss_rate={stats['loss_rate']:.3f} leader_margin={stats['leader_margin']:+.1f}"
    )
    for crop in crops:
        print(
            f"{crop}: seed_gap={stats[f'seed_gap_{crop}']:+.2f} "
            f"unit_gap={stats[f'unit_gap_{crop}']:+.2f} "
            f"revenue_gap={stats[f'revenue_gap_{crop}']:+.1f}"
        )


def print_control(label: str, rows: list[dict], aggregate: dict[str, float]) -> None:
    print(f"\n[{label}]")
    print(
        f"eligible_leaders={aggregate['eligible_leaders']} "
        f"mean_margin_shift={aggregate['mean_margin_shift']:+.1f} "
        f"mean_seed_gap_shift={aggregate['mean_seed_gap_shift']:+.2f} "
        f"mean_revenue_gap_shift={aggregate['mean_revenue_gap_shift']:+.1f}"
    )
    for row in sorted(rows, key=lambda item: item["leader"]):
        print(
            f"  {row['leader']}: target={row['target_cells']} other={row['other_cells']} "
            f"margin={row['margin_shift']:+.1f} seed={row['seed_gap_shift']:+.2f} "
            f"revenue={row['revenue_gap_shift']:+.1f}"
        )


def main() -> int:
    args = parse_args()
    rows = load_rows(args.ledger)
    losses = [row for row in rows if candidate_lost(row)]
    pet = [row for row in rows if first_shop(row) == "PET_CAFE"]
    pet_losses = [row for row in pet if candidate_lost(row)]
    non_pet_losses = [
        row for row in rows if first_shop(row) != "PET_CAFE" and candidate_lost(row)
    ]
    pizza = [row for row in rows if first_shop(row) == "PIZZA_SHOP"]

    print(f"ledger={args.ledger}")
    print_group("all cells", summary(rows), ("WHEAT", "CARROT", "TOMATO"))
    print_group("all V3.1 losses", summary(losses), ("WHEAT", "CARROT", "TOMATO"))
    print_group("PET_CAFE first", summary(pet), ("WHEAT", "CARROT"))
    print_group("PET_CAFE first, V3.1 losses", summary(pet_losses), ("WHEAT", "CARROT"))
    print_group("non-PET first, V3.1 losses", summary(non_pet_losses), ("WHEAT", "CARROT"))

    pet_rows, pet_agg = within_leader_control(
        rows, "PET_CAFE", "CARROT", args.min_cells_per_arm
    )
    print_control("within-leader PET_CAFE vs non-PET / CARROT", pet_rows, pet_agg)

    print_group("PIZZA_SHOP first negative control", summary(pizza), ("TOMATO",))
    pizza_rows, pizza_agg = within_leader_control(
        rows, "PIZZA_SHOP", "TOMATO", args.min_cells_per_arm
    )
    print_control("within-leader PIZZA vs non-PIZZA / TOMATO", pizza_rows, pizza_agg)

    print("\nInterpretation:")
    print(
        "PET_CAFE-first is the surviving composition residual: leaders shift sharply toward "
        "CARROT there, and the effect survives a same-leader control. PIZZA/TOMATO does not "
        "show the same robust direction and is retained only as a negative control."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

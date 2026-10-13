#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Source-bound oracle for Apex V7 anti-clone market counterplay.

This is research evidence only. It does not mutate TITAN actions, install a
controller, enable a feature, or authorize promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ENGINE_REL = Path("revenue/kaggriculture/cloud-execution-lab/reference/engine/kaggriculture.py")
APEX_REL = Path("revenue/kaggriculture/cloud-frontier-policy/next-panel/vendor/apex/main.py")
REFERENCE_REL = Path(
    "revenue/kaggriculture/cloud-execution-lab/candidates/v4/"
    "research/reference-policy-bank/REFERENCE-POLICIES.json"
)

EXPECTED_ENGINE_GIT_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
EXPECTED_APEX_SHA256 = "1f7cd5fb8a16585936d2562a3667f85bb6661688718ef58f73006de66148354a"

PRICE_FLOOR = 1
MARKET_PARAMS = {
    "STRAWBERRY": {
        "base": 120, "I0": 10000, "T": 100,
        "below_func": "sqrt", "below_target": 0.70,
        "above_func": "linear", "above_target": 1.60,
    },
    "FERTILIZER": {
        "base": 100, "I0": 10000, "T": 200,
        "below_func": "linear", "below_target": 0.40,
        "above_func": "linear", "above_target": 0.40,
    },
}

# Exact behavior of the authenticated Apex main.py above.
APEX_ANTI_CLONE = {
    "clone_window": [2, 10],
    "clone_min_opponent_hands": 3,
    "clone_min_opponent_structures": 1,
    "events": [
        {"steps": [249], "item": "MELON", "min_shed": 6, "max_sell": 12},
        {"steps": [381], "item": "STRAWBERRY", "min_shed": 6, "max_sell": 8},
        {"steps": [403], "item": "STRAWBERRY", "min_shed": 6, "max_sell": 8},
        {"steps": [499, 500, 501], "item": "STRAWBERRY", "min_shed": 8, "max_sell": 8},
        {
            "steps": [522],
            "item": "FERTILIZER",
            "min_shed": 18,
            "max_sell": 4,
            "quantity_rule": "min(fert - 16, 4)",
        },
    ],
}


class OracleError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_bytes(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise OracleError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise OracleError(f"non-finite JSON constant: {value}")


def verify_sources(repo_root: Path) -> dict[str, str]:
    repo_root = repo_root.resolve(strict=True)
    engine = (repo_root / ENGINE_REL).read_bytes()
    apex = (repo_root / APEX_REL).read_bytes()
    manifest_raw = (repo_root / REFERENCE_REL).read_text(encoding="utf-8")
    manifest = json.loads(
        manifest_raw,
        object_pairs_hook=_no_dupes,
        parse_constant=_reject_constant,
    )

    engine_blob = git_blob_bytes(engine)
    apex_sha = sha256_bytes(apex)
    declared_apex = (
        manifest.get("policies", {})
        .get("apex_v7", {})
        .get("files", {})
        .get("main.py")
    )
    if engine_blob != EXPECTED_ENGINE_GIT_BLOB:
        raise OracleError(
            f"official engine drift: expected {EXPECTED_ENGINE_GIT_BLOB}, got {engine_blob}"
        )
    if apex_sha != EXPECTED_APEX_SHA256:
        raise OracleError(
            f"Apex source drift: expected {EXPECTED_APEX_SHA256}, got {apex_sha}"
        )
    if declared_apex != EXPECTED_APEX_SHA256:
        raise OracleError(
            "reference-policy-bank Apex declaration drift: "
            f"expected {EXPECTED_APEX_SHA256}, got {declared_apex!r}"
        )
    return {
        "engine_git_blob": engine_blob,
        "apex_main_sha256": apex_sha,
        "reference_declared_apex_sha256": declared_apex,
    }


def _shape(kind: str, x: float, T: float) -> float:
    x = max(0.0, x)
    if kind == "linear":
        return x
    if kind == "sqrt":
        return math.sqrt(x)
    raise OracleError(f"unsupported shape in bounded oracle: {kind}")


def market_price(item: str, inventory: int) -> int:
    p = MARKET_PARAMS[item]
    base = p["base"]
    I0 = p["I0"]
    T = p["T"]
    if inventory < I0:
        kind = p["below_func"]
        amp = p["below_target"] * base / _shape(kind, T, T)
        value = base + amp * _shape(kind, I0 - inventory, T)
    else:
        kind = p["above_func"]
        amp = p["above_target"] * base / _shape(kind, T, T)
        value = base - amp * _shape(kind, inventory - I0, T)
    return max(PRICE_FLOOR, int(round(value)))


def sell_block(item: str, inventory: int, quantity: int) -> dict[str, int]:
    """Exact market-side effect for a successful isolated SELL block.

    At PRICE_FLOOR the official engine pays $1 and removes seller stock, but
    deliberately does not add that unit to market inventory.
    """
    if quantity < 0:
        raise OracleError("negative sell quantity")
    start = inventory
    cash = 0
    added = 0
    for _ in range(quantity):
        quoted = market_price(item, inventory)
        cash += quoted
        if quoted > PRICE_FLOOR:
            inventory += 1
            added += 1
    return {
        "start_inventory": start,
        "end_inventory": inventory,
        "quantity": quantity,
        "cash": cash,
        "market_units_added": added,
    }


def buy_product_block(item: str, inventory: int, quantity: int) -> dict[str, int]:
    """Exact quote rule for an isolated successful BUY_PRODUCT block.

    The official engine only allows WHEAT/FERTILIZER; this oracle uses
    FERTILIZER. Each unit quotes at post-buy inventory (inventory-1).
    Money/shed-capacity are deliberately preconditions, not invented here.
    """
    if item not in {"FERTILIZER"}:
        raise OracleError("bounded oracle only models FERTILIZER BUY_PRODUCT")
    if quantity < 0 or quantity > inventory:
        raise OracleError("invalid buy quantity")
    start = inventory
    cost = 0
    for _ in range(quantity):
        cost += market_price(item, inventory - 1)
        inventory -= 1
    return {
        "start_inventory": start,
        "end_inventory": inventory,
        "quantity": quantity,
        "cost": cost,
    }


def strawberry_cut(start_inventory: int, ours: int = 8, apex: int = 8) -> dict[str, int]:
    """Cash redistribution from selling our block one callback before Apex."""
    ours_first = sell_block("STRAWBERRY", start_inventory, ours)
    apex_after = sell_block("STRAWBERRY", ours_first["end_inventory"], apex)

    apex_first = sell_block("STRAWBERRY", start_inventory, apex)
    ours_after = sell_block("STRAWBERRY", apex_first["end_inventory"], ours)

    return {
        "start_inventory": start_inventory,
        "our_front_run_cash": ours_first["cash"],
        "our_after_cash": ours_after["cash"],
        "our_cash_gain": ours_first["cash"] - ours_after["cash"],
        "apex_cash_change": apex_after["cash"] - apex_first["cash"],
        "front_run_end_inventory": apex_after["end_inventory"],
        "late_end_inventory": ours_after["end_inventory"],
    }


def fertilizer_sponge(start_inventory: int, buy_quantity: int = 4) -> dict[str, int]:
    """Direct quote benefit attributable to Apex's exact max-four unit SELL."""
    if buy_quantity < 0:
        raise OracleError("negative buy quantity")
    before = buy_product_block("FERTILIZER", start_inventory, buy_quantity)
    apex = sell_block("FERTILIZER", start_inventory, 4)
    after = buy_product_block("FERTILIZER", apex["end_inventory"], buy_quantity)
    released = apex["market_units_added"]
    return {
        "start_inventory": start_inventory,
        "apex_sell_cash": apex["cash"],
        "apex_market_units_added": released,
        "buy_quantity": buy_quantity,
        "opponent_attributable_units": min(buy_quantity, released),
        "non_attributable_units": max(0, buy_quantity - released),
        "buy_cost_before_apex_sell": before["cost"],
        "buy_cost_after_apex_sell": after["cost"],
        "direct_quote_savings": before["cost"] - after["cost"],
    }


def build_report() -> dict[str, Any]:
    strawberry_rows = [strawberry_cut(inv) for inv in range(9800, 10081)]
    fertilizer_rows = [fertilizer_sponge(inv) for inv in range(9000, 10601)]

    sb_best = max(strawberry_rows, key=lambda row: row["our_cash_gain"])
    fert_best = max(fertilizer_rows, key=lambda row: row["direct_quote_savings"])
    sb_i0 = strawberry_cut(10000)
    fert_i0 = fertilizer_sponge(10000)
    fert_floor = fertilizer_sponge(10493)

    return {
        "schema": "titan.v4.apex-counter-ambush.v1",
        "sources": {
            "engine_git_blob": EXPECTED_ENGINE_GIT_BLOB,
            "apex_main_sha256": EXPECTED_APEX_SHA256,
        },
        "apex_contract": APEX_ANTI_CLONE,
        "engine_contract": {
            "market_rows_per_callback_default": 10,
            "sell_buy_product_execution": "per-unit lockstep",
            "quote_rule": "both players quote from the same pre-commit inventory for each unit",
            "buy_product_quote": "post-buy inventory",
            "sell_at_price_floor_adds_market_inventory": False,
        },
        "strawberry_380_402_cut": {
            "verdict": "mechanically_real_cash_transfer_policy_unproven",
            "sweep_start_inventory": [9800, 10080],
            "our_quantity": 8,
            "apex_quantity": 8,
            "at_I0": sb_i0,
            "max_observed_gross_cash_transfer_to_us": sb_best["our_cash_gain"],
            "max_transfer_start_inventory": sb_best["start_inventory"],
            "floor_example": strawberry_cut(10062),
            "boundary": (
                "This measures only ordering of two isolated eight-unit SELL blocks. "
                "It does not price TITAN's crop/shop shadow value, displaced authored "
                "orders, later rebound, or natural stock at steps 380/402."
            ),
        },
        "fertilizer_523_sponge": {
            "verdict": "falsified_as_massive_opponent_subsidy",
            "sweep_start_inventory": [9000, 10600],
            "apex_max_sell_units": 4,
            "buy_quantity_attributed": 4,
            "at_I0": fert_i0,
            "max_observed_direct_quote_savings": fert_best["direct_quote_savings"],
            "max_savings_start_inventory": fert_best["start_inventory"],
            "floor_example": fert_floor,
            "boundary": (
                "Only up to Apex's market_units_added can be attributed to the ambush. "
                "Buying more is an independent fertilizer policy and requires its own "
                "capacity, cash, crop-yield, and terminal-value economics."
            ),
        },
        "promotion": {
            "runtime_change": False,
            "default_change": False,
            "recommended_next_gate": (
                "Run current-native both seats versus authenticated Apex and compare "
                "BASE vs opponent-conditioned strawberry-only 380/402 candidate. "
                "Do not field the fertilizer sponge as an Apex-specific response."
            ),
        },
    }


def default_repo_root() -> Path:
    here = Path(__file__).resolve().parent
    return here.parents[6]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = args.repo_root or default_repo_root()
    try:
        identities = verify_sources(root)
        report = build_report()
        report["verified_sources"] = identities
    except (OSError, UnicodeError, json.JSONDecodeError, OracleError) as exc:
        print(f"COUNTERAMBUSH BLOCKED: {exc}")
        return 2
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        print(json.dumps({
            "strawberry": report["strawberry_380_402_cut"]["verdict"],
            "fertilizer": report["fertilizer_523_sponge"]["verdict"],
            "fertilizer_max_direct_savings": report["fertilizer_523_sponge"]["max_observed_direct_quote_savings"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

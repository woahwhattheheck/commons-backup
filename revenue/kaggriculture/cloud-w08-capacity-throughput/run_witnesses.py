# SPDX-License-Identifier: Apache-2.0
"""Emit deterministic W08 shed-capacity witnesses as JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import capacity_ledger as ledger


def event(event_id: str, step: int, phase: str, op: str, **kwargs: Any) -> dict[str, Any]:
    payload = {"id": event_id, "step": step, "phase": phase, "op": op, **kwargs}
    if op == "PLACE" and payload.get("destination") is None:
        payload["destination"] = "shed"
    return payload


def build_witnesses() -> dict[str, Any]:
    safe_baseline = [
        event("retained-place", 62, "unit", "PLACE", actor=0,
              item="WHEAT", quantity=1),
        event("guaranteed-sale", 62, "market", "SELL",
              item="WHEAT", quantity=1),
    ]
    new_job = [
        event("new-harvest", 59, "unit", "HARVEST", actor=1,
              item="WHEAT", quantity=1),
        event("new-drop", 64, "unit", "DROP", actor=1),
    ]
    safe = ledger.admit_additive_events(
        capacity=100,
        initial_shed={"WHEAT": 99},
        initial_carried={0: {"WHEAT": 1}, 1: {}},
        baseline_events=safe_baseline,
        additive_events=new_job,
        required_complete=["new-harvest", "new-drop"],
    )

    no_sale = ledger.admit_additive_events(
        capacity=100,
        initial_shed={"WHEAT": 99},
        initial_carried={0: {"WHEAT": 1}, 1: {}},
        baseline_events=safe_baseline[:1],
        additive_events=new_job,
        required_complete=["new-harvest", "new-drop"],
    )

    buy_refill = ledger.admit_additive_events(
        capacity=100,
        initial_shed={"WHEAT": 100},
        initial_carried={1: {}},
        baseline_events=[
            event("guaranteed-sale", 62, "market", "SELL",
                  item="WHEAT", quantity=1, sequence=0),
            event("intervening-buy", 62, "market", "BUY_PRODUCT",
                  item="MILK", quantity=1, sequence=1),
        ],
        additive_events=new_job,
        required_complete=["new-harvest", "new-drop"],
    )

    protected_place = ledger.admit_additive_events(
        capacity=100,
        initial_shed={"WHEAT": 99},
        initial_carried={0: {"MILK": 1}, 1: {}},
        baseline_events=[
            event("retained-place", 64, "unit", "PLACE", actor=0,
                  item="MILK", quantity=1, sequence=1),
        ],
        additive_events=[
            event("new-harvest", 59, "unit", "HARVEST", actor=1,
                  item="WHEAT", quantity=1),
            event("new-drop", 64, "unit", "DROP", actor=1, sequence=0),
        ],
        required_complete=["new-harvest", "new-drop"],
    )

    eod_sale = ledger.admit_additive_events(
        capacity=100,
        initial_shed={"WHEAT": 100},
        initial_carried={0: {}, 1: {}},
        baseline_events=[
            event("late-sale", 23, "market", "SELL",
                  item="WHEAT", quantity=2),
        ],
        additive_events=[
            event("late-harvest", 22, "unit", "HARVEST", actor=1,
                  item="MILK", quantity=2),
            event("eod-drop", 23, "eod", "EOD_DROP"),
        ],
        required_complete=["late-harvest", "eod-drop"],
    )

    full_cases = {
        "intervening_sale_admits_later_deposit": safe,
        "missing_sale_rejects_real_discard": no_sale,
        "buy_refills_sale_room_and_rejects": buy_refill,
        "candidate_cannot_reduce_retained_place": protected_place,
        "eod_drop_uses_post_market_room": eod_sale,
    }

    def compact(report: dict[str, Any]) -> dict[str, Any]:
        def trace(value: dict[str, Any]) -> dict[str, Any]:
            return {
                "receipts": value["receipts"],
                "final": value["final"],
                "summary": value["summary"],
                "conservation_errors": value["conservation_errors"],
            }
        return {
            "admitted": report["admitted"],
            "reason": report["reason"],
            "baseline_regressions": report["baseline_regressions"],
            "required_incomplete": report["required_incomplete"],
            "increased_discard": report["increased_discard"],
            "baseline": trace(report["baseline"]),
            "candidate": trace(report["candidate"]),
        }

    cases = {name: compact(report) for name, report in full_cases.items()}
    expected = {
        "intervening_sale_admits_later_deposit": True,
        "missing_sale_rejects_real_discard": False,
        "buy_refills_sale_room_and_rejects": False,
        "candidate_cannot_reduce_retained_place": False,
        "eod_drop_uses_post_market_room": True,
    }
    observed = {name: report["admitted"] for name, report in cases.items()}
    if observed != expected:
        raise AssertionError({"expected": expected, "observed": observed})
    return {
        "schema": "titan.w08.capacity-throughput-witnesses.v1",
        "scope": "deterministic own-event physical inventory; no games or score claim",
        "expected_admission": expected,
        "observed_admission": observed,
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_witnesses()
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

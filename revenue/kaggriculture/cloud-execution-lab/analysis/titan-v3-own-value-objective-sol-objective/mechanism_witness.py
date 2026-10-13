# SPDX-License-Identifier: Apache-2.0
"""Deterministic witness for the rival-subtraction objective inversion."""
from __future__ import annotations

import json
from pathlib import Path

from own_value_objective import own_value_tuple


CASES = [
    {
        "name": "objective_inversion",
        "plans": {
            "rival_suppression": {
                "score": (100.0, 100, 0, 0),
                "meaning": "100 own value; no rival receipts",
            },
            "leaderboard_cash": {
                "score": (82.0, 112, 30, 0),
                "meaning": "112 own value; 30 rival receipts",
            },
        },
    },
    {
        "name": "objective_agreement",
        "plans": {
            "low_cash": {"score": (75.0, 90, 15, 0)},
            "high_cash": {"score": (95.0, 110, 15, 0)},
        },
    },
]


def select(plans, transform):
    ranked = [
        (transform(tuple(data["score"]))[0], name)
        for name, data in plans.items()
    ]
    return max(ranked)[1]


def build_report():
    rows = []
    for case in CASES:
        plans = case["plans"]
        incumbent = select(plans, lambda score: score)
        candidate = select(plans, own_value_tuple)
        incumbent_own = own_value_tuple(tuple(plans[incumbent]["score"]))[0]
        candidate_own = own_value_tuple(tuple(plans[candidate]["score"]))[0]
        rows.append(
            {
                "name": case["name"],
                "incumbent_selection": incumbent,
                "candidate_selection": candidate,
                "selection_changed": incumbent != candidate,
                "incumbent_selected_own_value": incumbent_own,
                "candidate_selected_own_value": candidate_own,
                "own_value_delta": candidate_own - incumbent_own,
            }
        )
    return {
        "schema_version": 1,
        "hypothesis": "removing rival receipts from score[0] prevents own-cash sacrifice",
        "one_factor": "MarketPath.score[0]",
        "identity": "own_cash + carry = relative_value + rival_cash",
        "cases": rows,
    }


def main():
    report = build_report()
    inversion = next(row for row in report["cases"] if row["name"] == "objective_inversion")
    if inversion["incumbent_selection"] != "rival_suppression":
        raise SystemExit("incumbent witness no longer demonstrates the inversion")
    if inversion["candidate_selection"] != "leaderboard_cash":
        raise SystemExit("candidate objective did not recover the higher-own-value plan")
    if inversion["own_value_delta"] <= 0:
        raise SystemExit("candidate witness lacks own-value upside")
    output = Path(__file__).with_name("MECHANISM-WITNESS.json")
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

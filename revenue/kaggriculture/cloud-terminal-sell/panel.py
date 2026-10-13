# SPDX-License-Identifier: MIT
"""Summarize completed paired official-engine runs without promoting failures."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from statistics import mean
from typing import Any

from measure import compare, outcome


def receipt_totals(row: dict[str, Any], player: int) -> dict[str, dict[str, int]]:
    totals: dict[str, dict[str, int]] = {}
    for receipt in row.get("final_day_receipts", []):
        if receipt["player"] != player or receipt["op"] != "SELL":
            continue
        item = totals.setdefault(receipt["item"], {"units": 0, "cash": 0})
        item["units"] += 1
        item["cash"] += receipt["cash"]
    return totals


def describe(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [r for r in rows if r["status"] == "complete"]
    counts = Counter(outcome(r["scores"][r["candidate_seat"]]
                             - r["scores"][1-r["candidate_seat"]])
                     for r in completed)
    timings = [r["actors"][r["candidate_seat"]]["max_call_seconds"]
               for r in completed]
    return {
        "attempted": len(rows),
        "completed": len(completed),
        "failed": len(rows)-len(completed),
        "WTL": {label: counts[label] for label in ("W", "T", "L")},
        "max_candidate_call_seconds": max(timings, default=None),
        "mean_own_cash": mean(r["scores"][r["candidate_seat"]]
                              for r in completed) if completed else None,
        "mean_margin": mean(r["scores"][r["candidate_seat"]]
                            - r["scores"][1-r["candidate_seat"]]
                            for r in completed) if completed else None,
    }


def summarize(directory: Path, comparisons: list[tuple[str, str]]) -> dict[str, Any]:
    arms: dict[str, list[dict[str, Any]]] = defaultdict(list)
    records = []
    for path in sorted(directory.glob("*.json")):
        raw = path.read_bytes()
        row = json.loads(raw)
        if not all(key in row for key in ("arm", "seed", "candidate_seat", "status")):
            continue
        arms[row["arm"]].append(row)
        seat = row["candidate_seat"]
        private = row.get("terminal", {}).get("private", [])
        own_private = private[seat] if len(private) > seat else {}
        records.append({
            "file": path.name, "sha256": hashlib.sha256(raw).hexdigest(),
            "arm": row["arm"], "seed": row["seed"],
            "opponent": row["opponent"], "candidate_seat": seat,
            "status": row["status"], "failure": row.get("failure"),
            "scores": row.get("scores"), "steps": row.get("steps"),
            "pre698_sha256": row.get("pre698_sha256"),
            "final_day_own_sales": receipt_totals(row, seat),
            "final_day_rival_sales": receipt_totals(row, 1-seat),
            "terminal_own_shed": own_private.get("shed"),
            "terminal_own_carried": own_private.get("inventories"),
            "provenance": row.get("provenance"),
        })
    paired = {}
    for left, right in comparisons:
        # A misspelled or missing arm cannot silently become an empty win bank.
        if left not in arms or right not in arms:
            raise ValueError(f"Comparison needs both present arms: {left}, {right}")
        comparison = compare(arms[left], arms[right])
        pairs = comparison["pairs"]
        comparison.update({
            "mean_own_cash_delta": mean(p["own_cash_delta"] for p in pairs) if pairs else None,
            "mean_rival_cash_delta": mean(p["rival_cash_delta"] for p in pairs) if pairs else None,
            "mean_margin_delta": mean(p["margin_delta"] for p in pairs) if pairs else None,
            "all_pre698_equal": bool(pairs) and not comparison["unresolved"]
                and all(p["same_pre698_observations_and_actions"] for p in pairs),
        })
        paired[f"{left}_to_{right}"] = comparison
    return {
        "method": "Full official-engine games in isolated cloud processes. Local outcomes, not hosted ratings.",
        "arms": {name: describe(rows) for name, rows in sorted(arms.items())},
        "by_opponent": {name: {opp: describe([r for r in rows if r['opponent'] == opp])
                                for opp in sorted({r['opponent'] for r in rows})}
                        for name, rows in sorted(arms.items())},
        "comparisons": paired, "records": records,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--compare", nargs=2, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = summarize(args.directory, [tuple(x) for x in args.compare])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n")
    print(json.dumps(summary["arms"], indent=2))


if __name__ == "__main__":
    main()

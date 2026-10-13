#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from profile_arc3_runs import discover, profile_trace
from validate_arc3_trace import TraceError, digest, load_jsonl


def load(root: pathlib.Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in discover([root]):
        row = profile_trace(path)
        episode_id = row["episode_id"]
        if episode_id in out:
            raise TraceError(f"duplicate episode_id {episode_id!r}")
        records = load_jsonl(path)
        row["initial_state_digest"] = digest(records[1]["state"])
        out[episode_id] = row
    return out


def pct(new: int, old: int) -> float | None:
    return None if old == 0 else round((new - old) * 100.0 / old, 6)


def compare(base: dict[str, dict[str, Any]], cand: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if set(base) != set(cand):
        raise TraceError(
            f"episode set mismatch: missing={sorted(set(base)-set(cand))}, "
            f"extra={sorted(set(cand)-set(base))}"
        )
    rows = []
    improved = regressed = 0
    for episode_id in sorted(base):
        b, c = base[episode_id], cand[episode_id]
        if b["max_actions"] != c["max_actions"] or b["max_wall_ms"] != c["max_wall_ms"]:
            raise TraceError(f"{episode_id}: declared budgets differ")
        if b["initial_state_digest"] != c["initial_state_digest"]:
            raise TraceError(f"{episode_id}: initial state differs")
        change = "same"
        if not b["success"] and c["success"]:
            change = "improved"; improved += 1
        elif b["success"] and not c["success"]:
            change = "regressed"; regressed += 1
        rows.append({
            "episode_id": episode_id,
            "success_change": change,
            "failure_class": {"baseline": b["failure_class"], "candidate": c["failure_class"]},
            "actions": {"baseline": b["actions"], "candidate": c["actions"], "delta": c["actions"]-b["actions"]},
            "wall_ms": {"baseline": b["wall_ms"], "candidate": c["wall_ms"], "delta": c["wall_ms"]-b["wall_ms"]},
        })

    ba, ca = sum(x["actions"] for x in base.values()), sum(x["actions"] for x in cand.values())
    bw, cw = sum(x["wall_ms"] for x in base.values()), sum(x["wall_ms"] for x in cand.values())
    bs, cs = sum(x["success"] for x in base.values()), sum(x["success"] for x in cand.values())
    return {
        "schema": "tj-arc3-comparison/v1",
        "aggregate": {
            "episodes": len(rows),
            "successes": {"baseline": bs, "candidate": cs, "delta": cs-bs, "improvements": improved, "regressions": regressed},
            "actions": {"baseline": ba, "candidate": ca, "delta": ca-ba, "pct_delta": pct(ca, ba)},
            "wall_ms": {"baseline": bw, "candidate": cw, "delta": cw-bw, "pct_delta": pct(cw, bw)},
        },
        "episodes": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare two validated ARC-AGI-3 trace suites.")
    ap.add_argument("baseline", type=pathlib.Path)
    ap.add_argument("candidate", type=pathlib.Path)
    ap.add_argument("--fail-on-success-regression", action="store_true")
    ap.add_argument("--max-action-regression-pct", type=float)
    ap.add_argument("--max-wall-regression-pct", type=float)
    args = ap.parse_args()
    try:
        report = compare(load(args.baseline), load(args.candidate))
    except (OSError, KeyError, TraceError, ValueError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr); return 2

    failures = []
    a = report["aggregate"]
    if args.fail_on_success_regression and a["successes"]["regressions"]:
        failures.append(f"success regressions={a['successes']['regressions']}")
    for key, limit in (("actions", args.max_action_regression_pct), ("wall_ms", args.max_wall_regression_pct)):
        delta = a[key]["pct_delta"]
        if limit is not None and delta is not None and delta > limit:
            failures.append(f"{key} regression={delta}% > {limit}%")
    report["gate"] = {"passed": not failures, "failures": failures}
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if not failures else 3


if __name__ == "__main__":
    raise SystemExit(main())

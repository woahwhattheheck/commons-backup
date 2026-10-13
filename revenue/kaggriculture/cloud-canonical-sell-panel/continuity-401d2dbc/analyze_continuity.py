#!/usr/bin/env python3
"""Bind current games to retained PR10156 rows and compute exact continuity."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import statistics


def load(path):
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    return json.loads(data)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, nargs=2, required=True)
    parser.add_argument("--ancestor-panel", type=Path, required=True)
    parser.add_argument("--ancestor-seat1-trace", type=Path, required=True)
    parser.add_argument("--funding-probe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ancestor-output", type=Path, required=True)
    args = parser.parse_args()

    current = sorted((load(path) for path in args.current), key=lambda row: row["candidate_seat"])
    panel = load(args.ancestor_panel)
    ancestor = sorted((row for row in panel["games"] if row["seed"] == 9922023),
                      key=lambda row: row["candidate_seat"])
    assert len(current) == len(ancestor) == 2
    retained_trace = load(args.ancestor_seat1_trace)
    funding = load(args.funding_probe)
    direct_action_diffs = sum(a["actions"] != b["actions"] for a, b in
                              zip(current[1]["trace"], retained_trace["trace"]))
    direct_bank_diffs = sum(a["bank"] != b["bank"] for a, b in
                            zip(current[1]["trace"], retained_trace["trace"]))

    timing = {}
    for row in current:
        seat = row["candidate_seat"]
        calls = [step["calls"][seat] for step in row["trace"]]
        actor = row["actors"][seat]
        timing[str(seat)] = {
            "worker_source_startup_seconds": actor["startup_seconds"],
            "first_action_child_seconds": calls[0]["child_seconds"],
            "first_action_rpc_seconds": calls[0]["rpc_seconds"],
            "max_action_child_seconds": max(item["child_seconds"] for item in calls),
            "max_action_rpc_seconds": max(item["rpc_seconds"] for item in calls),
            "mean_action_child_seconds": statistics.mean(item["child_seconds"] for item in calls),
            "mean_action_rpc_seconds": statistics.mean(item["rpc_seconds"] for item in calls),
            "peak_rss_kib": actor["peak_rss_kib"],
        }

    compact_ancestor = {
        "source": "PR10156/1c5a87de retained raw stage-12 report; no ancestor game rerun",
        "report_sha256": sha(args.ancestor_panel),
        "rows": [{key: row[key] for key in ("seed", "candidate_seat", "scores", "trace_sha256",
                                               "status", "failure", "steps")} for row in ancestor],
    }
    args.ancestor_output.write_text(json.dumps(compact_ancestor, indent=2) + "\n")

    summary = {
        "scope": "changed-source continuity only; not fresh strength or held evidence",
        "current": {
            "merge": "60669387c45678c00be3a200eb2a23763c7d75f7",
            "archive_sha256": "401d2dbcaf2a089386a145bd0237b79070dfda730d4cf582ad814a59a778a86d",
            "archive_bytes": 275290,
            "source_manifest_sha256": "051a5eddac522986c5b43f972b1597ef96415c9669f65b17c66c172844c50ca1",
        },
        "ancestor": {"merge": "1c5a87de8d6947f82f2e47ab8875100240d0cf85",
                     "archive_sha256": "70554dc01f8e84336ede169cf109f3d61152e169dce8ad5265b9625216fe52cb"},
        "seed": 9922023,
        "games": [{"candidate_seat": now["candidate_seat"], "scores": now["scores"],
                   "trace_sha256": now["trace_sha256"],
                   "ancestor_scores": old["scores"], "ancestor_trace_sha256": old["trace_sha256"],
                   "same_scores": now["scores"] == old["scores"],
                   "same_full_trace_sha256": now["trace_sha256"] == old["trace_sha256"]}
                  for now, old in zip(current, ancestor)],
        "divergence": {
            "full_trace_hash_mismatches": sum(now["trace_sha256"] != old["trace_sha256"]
                                               for now, old in zip(current, ancestor)),
            "terminal_score_mismatches": sum(now["scores"] != old["scores"]
                                               for now, old in zip(current, ancestor)),
            "seat1_direct_action_round_diffs": direct_action_diffs,
            "seat1_direct_bank_transition_diffs": direct_bank_diffs,
            "seat0_comparison": "exact retained evaluator trace digest and terminal row",
        },
        "funding": {
            "hook_calls_this_entry": funding["reached"]["hook_calls_this_entry"],
            "step": funding["reached"]["step"],
            "selected": funding["reached"]["selected"],
            "returned": funding["reached"]["returned"],
            "diagnostics": funding["reached"]["diagnostics"],
        },
        "timing": timing,
        "external_failures_or_timeouts": 0,
        "internal_deadline_fallbacks": "not asserted; direct evaluator entry does not export per-call diagnostics",
        "inputs": {
            "current_trace_files": [{"path": str(path), "sha256": sha(path)} for path in args.current],
            "funding_probe_sha256": sha(args.funding_probe),
            "ancestor_seat1_trace_sha256": sha(args.ancestor_seat1_trace),
        },
    }
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    assert all(row["same_scores"] and row["same_full_trace_sha256"] for row in summary["games"])
    assert direct_action_diffs == direct_bank_diffs == 0
    assert summary["funding"]["hook_calls_this_entry"] == 1


if __name__ == "__main__":
    main()

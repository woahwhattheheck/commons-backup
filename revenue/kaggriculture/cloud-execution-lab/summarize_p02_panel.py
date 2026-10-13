#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarize opt-in P02 public-action traces emitted by isolated candidates."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", required=True)
    parser.add_argument("--games", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    trace_dir = Path(args.trace_dir)
    game_rows = [json.loads(line) for line in Path(args.games).read_text().splitlines() if line.strip()]
    traces = []
    process_rows = {}
    for path in sorted(trace_dir.glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        process_rows[path.name] = len(rows)
        traces.extend(rows)
    reasons = Counter(row.get("reason", "missing") for row in traces)
    events = Counter(event.get("kind", "missing")
                     for row in traces for event in row.get("events", []))
    changed = [row for row in traces if row.get("before_market") != row.get("after_market")]
    complete = [row for row in game_rows if row.get("status") == "complete"]
    summary = {
        "schema": "titan-p02-live-telemetry-v1",
        "scheduled_games": len(game_rows),
        "complete_games": len(complete),
        "candidate_processes_with_p02_events": len(process_rows),
        "trace_rows": len(traces),
        "changed_action_rows": len(changed),
        "reasons": dict(sorted(reasons.items())),
        "events": dict(sorted(events.items())),
        "per_process_trace_rows": process_rows,
        "changed_steps": sorted({int(row["step"]) for row in changed}),
        "changed_players": dict(sorted(Counter(str(row["player"]) for row in changed).items())),
    }
    Path(args.output).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print("P02_TELEMETRY=" + json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()

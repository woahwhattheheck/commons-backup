# SPDX-License-Identifier: Apache-2.0
"""Classify retained action traces for P07 current-HIRE window eligibility.

Input is JSONL.  Each row must contain ``observation``, ``selected``, and
``route``.  This utility never executes an agent, producer, interpreter, game,
provider, or network request; it only evaluates the deterministic window proof.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, TextIO

from current_hire_window import prove_window


def scan(lines: Iterable[str]) -> dict:
    reasons: Counter[str] = Counter()
    total = 0
    current_hire_rows = 0
    eligible_current_hire_rows = 0
    malformed_rows = 0
    examples = []

    for line_number, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        total += 1
        try:
            row = json.loads(raw)
            observation = row["observation"]
            selected = row["selected"]
            route = row["route"]
            now = observation["step"]
            proof = prove_window(observation, selected, route, now)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            malformed_rows += 1
            reasons["malformed_trace_row"] += 1
            continue

        reasons[proof.reason] += 1
        if proof.current_hires:
            current_hire_rows += 1
            if proof.accepted:
                eligible_current_hire_rows += 1
                if len(examples) < 16:
                    examples.append(
                        {
                            "line": line_number,
                            "step": now,
                            "end": proof.end,
                            "existing_actors": proof.existing_actors,
                            "current_hires": proof.current_hires,
                        }
                    )

    return {
        "schema": "titan.p07.current_hire_window_scan.v1",
        "trace_rows": total,
        "current_hire_rows": current_hire_rows,
        "eligible_current_hire_rows": eligible_current_hire_rows,
        "malformed_rows": malformed_rows,
        "reasons": dict(sorted(reasons.items())),
        "eligible_examples": examples,
        "boundary": "window eligibility only; not accepted swap, game, score, or promotion evidence",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    with args.jsonl.open("r", encoding="utf-8") as handle:
        report = scan(handle)
    rendered = json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

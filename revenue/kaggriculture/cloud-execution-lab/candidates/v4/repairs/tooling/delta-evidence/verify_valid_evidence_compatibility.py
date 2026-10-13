#!/usr/bin/env python3
"""Replay the #12646 deterministic valid-input compatibility experiment.

This compares the adjacent reporter with the preserved historical donor for
2,000 generated valid documents. It is not a full-game test, a malformed-input
suite, or a requirement to retain bugs in future intentional schema changes.
No network, output-file writes, workflow changes, or production imports occur.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import sys
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
SEED = 12646
CASES = 2000


def load_reporter(name: str, path: Path) -> tuple[ModuleType, str]:
    # Compile exactly the bytes whose hash is printed in the execution receipt.
    data = path.read_bytes()
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(data, str(path), "exec"), module.__dict__)
    return module, hashlib.sha256(data).hexdigest()


def documents() -> Any:
    rng = random.Random(SEED)
    for case in range(CASES):
        rows = []
        for j in range(rng.randint(1, 12)):
            seat = j % 2
            values = [rng.randint(0, 200000) for _ in range(4)]
            if case % 2:
                baseline = {"own": values[0], "rival": values[1]}
                candidate = {"own": values[2], "rival": values[3]}
            else:
                baseline = {"scores": values[:2] if seat == 0 else values[:2][::-1]}
                candidate = {"scores": values[2:] if seat == 0 else values[2:][::-1]}
            row = {"opponent": "agent-" + str(j % 3), "seed": case * 20 + j,
                   "candidate_seat": seat, "baseline": baseline, "candidate": candidate}
            if j % 3 != 0:
                row["activations"] = {"x": rng.randint(0, 3), "y": bool(j % 2)}
            rows.append(row)
        if case % 3 == 0:
            document: Any = {"baseline": [], "candidate": []}
            for row in rows:
                key = {k: row[k] for k in ("opponent", "seed", "candidate_seat")}
                document["baseline"].append(dict(key, **row["baseline"]))
                arm = dict(key, **row["candidate"])
                if "activations" in row:
                    arm["activations"] = row["activations"]
                document["candidate"].append(arm)
        else:
            document = {"cells": rows, "games": rows} if case % 3 == 1 else rows
        yield case, document


def main() -> int:
    try:
        donor, donor_sha = load_reporter("compat_donor", HERE / "donor/v31_delta_distribution_report.py")
        current, current_sha = load_reporter("compat_current", HERE / "v31_delta_distribution_report.py")
        for case, document in documents():
            expected = donor.analyze(donor.load_records(document))
            actual = current.analyze(current.load_records(document))
            if actual != expected:
                print(f"FAIL: valid-evidence report differs at case {case}, seed {SEED}", file=sys.stderr)
                return 1
            json.dumps(actual, allow_nan=False)
    except (OSError, ValueError, TypeError, OverflowError, SyntaxError, AttributeError) as exc:
        print(f"ERROR: compatibility experiment could not complete: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"result": "PASS", "cases": CASES, "seed": SEED,
                      "donor_sha256": donor_sha, "current_sha256": current_sha,
                      "scope": "generated valid evidence only; exact normalized-report equality"},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

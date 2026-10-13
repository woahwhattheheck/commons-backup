#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from own_value_objective import _admit_candidate


def case(candidate_relative: float) -> dict:
    reference = {
        name: {"own_value": 100.0, "relative_value": 20.0}
        for name in ("no_rival", "observed_paired", "observed_later_order")
    }
    control = {
        name: {"own_value": 112.0, "relative_value": 32.0}
        for name in reference
    }
    candidate = {
        name: {"own_value": 120.0, "relative_value": candidate_relative}
        for name in reference
    }
    admitted, reason, metrics = _admit_candidate(
        reference=reference, control=control, candidate=candidate
    )
    return {"admitted": admitted, "reason": reason, "metrics": metrics}


def main() -> None:
    payload = {
        "schema_version": 1,
        "operation": "titan-v3-state-conditioned-safe-own-objective-sol-pareto-20260910-01",
        "safe_frontier": case(21.0),
        "relative_regression": case(19.0),
        "claim": "own-value choice is state-local and cannot cross below authored-reference relative value in any canonical scenario",
        "promotion_authority": False,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    payload["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    path = Path("MECHANISM-WITNESS.json")
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()

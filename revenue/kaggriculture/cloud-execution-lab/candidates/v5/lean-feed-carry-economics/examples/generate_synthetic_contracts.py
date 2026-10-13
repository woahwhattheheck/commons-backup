#!/usr/bin/env python3
"""Generate the README-named synthetic lean-feed evidence fixtures.

These fixtures exercise the contract and promotion fence only. They are not
official-engine evidence and deliberately carry no trusted authority root.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lean_feed_core import canonical_json_bytes  # noqa: E402
from test_feed_carry_oracle import document  # noqa: E402


def main() -> int:
    target = Path(__file__).resolve().parent
    fixtures = {
        "synthetic_positive_contract.json": document(),
        "synthetic_no_redeployment.json": document(cash_use=False),
    }
    for name, payload in fixtures.items():
        (target / name).write_bytes(canonical_json_bytes(payload))
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
